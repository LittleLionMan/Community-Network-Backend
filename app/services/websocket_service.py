from fastapi import WebSocket
from typing import Dict, Set, Optional
import json
import logging
import time
import asyncio
from collections import defaultdict

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.poll_connections: Dict[int, Set[WebSocket]] = defaultdict(set)
        self.event_connections: Dict[int, Set[WebSocket]] = defaultdict(set)
        self.global_connections: Set[WebSocket] = set()
        self.user_connections: Dict[int, Set[WebSocket]] = defaultdict(set)
        self.conversation_connections: Dict[int, Set[WebSocket]] = defaultdict(set)

        self.typing_status: Dict[int, Dict[int, float]] = defaultdict(dict)

        self.connection_metadata: Dict[WebSocket, Dict] = {}

        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        if not self._cleanup_task or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def connect(
        self,
        websocket: WebSocket,
        connection_type: str,
        item_id: Optional[int] = None,
        user_id: Optional[int] = None
    ):
        await websocket.accept()

        self.connection_metadata[websocket] = {
            'type': connection_type,
            'item_id': item_id,
            'user_id': user_id,
            'connected_at': time.time()
        }

        if connection_type == "global":
            self.global_connections.add(websocket)
            logger.info(f"📡 Global connection added (total: {len(self.global_connections)})")

        elif connection_type == "polls":
            if item_id is None:
                raise ValueError("item_id required for polls connection")
            self.poll_connections[item_id].add(websocket)
            logger.info(f"📡 Poll connection added for ID {item_id}")

        elif connection_type == "events":
            if item_id is None:
                raise ValueError("item_id required for events connection")
            self.event_connections[item_id].add(websocket)
            logger.info(f"📡 Event connection added for ID {item_id}")

        elif connection_type == "user":
            if user_id is None:
                raise ValueError("user_id required for user connection")
            self.user_connections[user_id].add(websocket)
            logger.info(f"📡 User connection added for user {user_id}")

        elif connection_type == "conversation":
            if item_id is None:
                raise ValueError("conversation_id required for conversation connection")
            self.conversation_connections[item_id].add(websocket)
            logger.info(f"📡 Conversation connection added for conversation {item_id}")

    def disconnect(self, websocket: WebSocket):
        metadata = self.connection_metadata.pop(websocket, {})

        self.global_connections.discard(websocket)

        self._remove_from_dict_sets(self.poll_connections, websocket)
        self._remove_from_dict_sets(self.event_connections, websocket)
        self._remove_from_dict_sets(self.user_connections, websocket)
        self._remove_from_dict_sets(self.conversation_connections, websocket)

        # ✅ Clean up typing status for this connection
        user_id = metadata.get('user_id')
        connection_type = metadata.get('type')
        if user_id and connection_type == 'conversation':
            item_id = metadata.get('item_id')
            if item_id and item_id in self.typing_status:
                self.typing_status[item_id].pop(user_id, None)
                if not self.typing_status[item_id]:
                    del self.typing_status[item_id]

    def _remove_from_dict_sets(self, dict_sets: Dict[int, Set[WebSocket]], websocket: WebSocket):
        keys_to_remove = []
        for key, connection_set in dict_sets.items():
            connection_set.discard(websocket)
            if not connection_set:  # Remove empty sets
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del dict_sets[key]

    async def _periodic_cleanup(self):
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                current_time = time.time()

                self.cleanup_old_typing_status(30)

                stale_connections = []
                for websocket, metadata in self.connection_metadata.items():
                    if current_time - metadata.get('connected_at', 0) > 86400:  # 24 hours
                        stale_connections.append(websocket)

                for websocket in stale_connections:
                    self.disconnect(websocket)

                if int(current_time) % 3600 == 0:  # Every hour
                    self._log_memory_stats()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup task error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    def cleanup_old_typing_status(self, max_age_seconds: int = 10):
        current_time = time.time()
        conversations_to_clean = []

        for conversation_id in list(self.typing_status.keys()):
            users_to_clean = []

            for user_id, timestamp in list(self.typing_status[conversation_id].items()):
                if current_time - timestamp > max_age_seconds:
                    users_to_clean.append(user_id)

            for user_id in users_to_clean:
                del self.typing_status[conversation_id][user_id]

            if not self.typing_status[conversation_id]:
                conversations_to_clean.append(conversation_id)

        for conversation_id in conversations_to_clean:
            del self.typing_status[conversation_id]

    def _log_memory_stats(self):
        """Log current memory usage for monitoring"""
        stats = {
            'global_connections': len(self.global_connections),
            'poll_connections': sum(len(conns) for conns in self.poll_connections.values()),
            'event_connections': sum(len(conns) for conns in self.event_connections.values()),
            'user_connections': sum(len(conns) for conns in self.user_connections.values()),
            'conversation_connections': sum(len(conns) for conns in self.conversation_connections.values()),
            'active_typing_conversations': len(self.typing_status),
            'connection_metadata_entries': len(self.connection_metadata),
            'total_tracked_connections': len(self.connection_metadata)
        }

        logger.info("WebSocket memory stats", extra=stats)

        total_connections = stats['total_tracked_connections']
        if total_connections > 1000:
            logger.warning(f"High WebSocket connection count: {total_connections}")

    def is_user_connected(self, user_id: int) -> bool:
        return user_id in self.user_connections and len(self.user_connections[user_id]) > 0

    async def send_to_user(self, user_id: int, message: dict):
        if user_id not in self.user_connections:
            logger.debug(f"No connections found for user {user_id}")
            return

        message_str = json.dumps(message)
        dead_connections = set()

        for websocket in self.user_connections[user_id].copy():
            try:
                await websocket.send_text(message_str)
                logger.debug(f"📤 Message sent to user {user_id}")
            except Exception as e:
                logger.warning(f"Failed to send message to user {user_id}: {e}")
                dead_connections.add(websocket)

        for websocket in dead_connections:
            self.disconnect(websocket)

    async def broadcast_typing_status(self, conversation_id: int, user_id: int, is_typing: bool):
        current_time = time.time()

        if is_typing:
            if conversation_id not in self.typing_status:
                self.typing_status[conversation_id] = {}
            self.typing_status[conversation_id][user_id] = current_time
        else:
            if conversation_id in self.typing_status:
                self.typing_status[conversation_id].pop(user_id, None)
                if not self.typing_status[conversation_id]:
                    del self.typing_status[conversation_id]

        active_typing_users = []
        if conversation_id in self.typing_status:
            cutoff_time = current_time - 15  # 15 seconds max typing indicator
            active_typing_users = [
                uid for uid, timestamp in self.typing_status[conversation_id].items()
                if timestamp > cutoff_time
            ]

        await self.send_to_conversation(conversation_id, {
            'type': 'typing_status',
            'conversation_id': conversation_id,
            'typing_users': active_typing_users
        })

    async def broadcast_privacy_change(self, user_id: int, messages_enabled: bool):
        if user_id not in self.user_connections:
            logger.debug(f"No connections found for user {user_id} for privacy change broadcast")
            return

        message = {
            'type': 'privacy_change',
            'user_id': user_id,
            'messages_enabled': messages_enabled,
            'timestamp': time.time()
        }

        message_str = json.dumps(message)
        dead_connections = set()

        for websocket in self.user_connections[user_id].copy():
            try:
                await websocket.send_text(message_str)
                logger.info(f"📤 Privacy change notification sent to user {user_id}")
            except Exception as e:
                logger.warning(f"Failed to send privacy change notification to user {user_id}: {e}")
                dead_connections.add(websocket)

        for websocket in dead_connections:
            self.disconnect(websocket)

        await self.broadcast_global({
            'type': 'user_privacy_update',
            'user_id': user_id,
            'messages_enabled': messages_enabled
        })

    async def broadcast_global(self, message: dict):
        if not self.global_connections:
            return

        message_str = json.dumps(message)
        dead_connections = set()

        for websocket in self.global_connections.copy():
            try:
                await websocket.send_text(message_str)
            except Exception as e:
                logger.warning(f"Failed to send global broadcast: {e}")
                dead_connections.add(websocket)

        for websocket in dead_connections:
            self.disconnect(websocket)


    async def send_to_conversation(self, conversation_id: int, message: dict, exclude_user_id: Optional[int] = None):
        if conversation_id not in self.conversation_connections:
            logger.debug(f"No connections found for conversation {conversation_id}")
            return

        message_str = json.dumps(message)
        dead_connections = set()

        for websocket in self.conversation_connections[conversation_id].copy():
            try:
                metadata = self.connection_metadata.get(websocket, {})
                if exclude_user_id and metadata.get('user_id') == exclude_user_id:
                    continue

                await websocket.send_text(message_str)
                logger.debug(f"📤 Message sent to conversation {conversation_id}")
            except Exception as e:
                logger.warning(f"Failed to send message to conversation {conversation_id}: {e}")
                dead_connections.add(websocket)

        for websocket in dead_connections:
            self.disconnect(websocket)

    def get_connection_stats(self) -> dict:
        return {
            'global_connections': len(self.global_connections),
            'poll_connections': {k: len(v) for k, v in self.poll_connections.items()},
            'event_connections': {k: len(v) for k, v in self.event_connections.items()},
            'user_connections': {k: len(v) for k, v in self.user_connections.items()},
            'conversation_connections': {k: len(v) for k, v in self.conversation_connections.items()},
            'active_typing': {k: len(v) for k, v in self.typing_status.items()},
            'total_connections': len(self.connection_metadata),
            'memory_usage': {
                'typing_conversations': len(self.typing_status),
                'metadata_entries': len(self.connection_metadata),
                'poll_rooms': len(self.poll_connections),
                'conversation_rooms': len(self.conversation_connections)
            }
        }

websocket_manager = WebSocketManager()
