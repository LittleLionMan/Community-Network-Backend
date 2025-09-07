from fastapi import WebSocket
from typing import Dict, Set, Optional
import json
import logging
import time

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.poll_connections: Dict[int, Set[WebSocket]] = {}
        self.event_connections: Dict[int, Set[WebSocket]] = {}
        self.global_connections: Set[WebSocket] = set()

        self.user_connections: Dict[int, Set[WebSocket]] = {}
        self.conversation_connections: Dict[int, Set[WebSocket]] = {}
        self.typing_status: Dict[int, Dict[int, float]] = {}

    async def connect(self, websocket: WebSocket, connection_type: str, item_id: Optional[int] = None, user_id: Optional[int] = None):
        await websocket.accept()

        if connection_type == "global":
            self.global_connections.add(websocket)
            logger.info(f"📡 Global connection added (total: {len(self.global_connections)})")
        elif connection_type == "polls":
            if item_id is None:
                    raise ValueError("item_id required for polls connection")
            if item_id not in self.poll_connections:
                self.poll_connections[item_id] = set()
            self.poll_connections[item_id].add(websocket)
            logger.info(f"📡 Poll connection added for ID {item_id}")
        elif connection_type == "events":
            if item_id is None:
                    raise ValueError("item_id required for events connection")
            if item_id not in self.event_connections:
                self.event_connections[item_id] = set()
            self.event_connections[item_id].add(websocket)
            logger.info(f"📡 Event connection added for ID {item_id}")

        elif connection_type == "user":
            if user_id is None:
                raise ValueError("user_id required for user connection")
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(websocket)
            logger.info(f"📡 User connection added for user {user_id}")

        elif connection_type == "conversation":
            if item_id is None:
                raise ValueError("conversation_id required for conversation connection")
            if item_id not in self.conversation_connections:
                self.conversation_connections[item_id] = set()
            self.conversation_connections[item_id].add(websocket)
            logger.info(f"📡 Conversation connection added for conversation {item_id}")

    def disconnect(self, websocket: WebSocket):
        self.global_connections.discard(websocket)

        for item_id, connections in self.poll_connections.items():
            connections.discard(websocket)
        self.poll_connections = {k: v for k, v in self.poll_connections.items() if v}

        for item_id, connections in self.event_connections.items():
            connections.discard(websocket)
        self.event_connections = {k: v for k, v in self.event_connections.items() if v}

        for user_id, connections in self.user_connections.items():
            connections.discard(websocket)
        self.user_connections = {k: v for k, v in self.user_connections.items() if v}

        for conversation_id, connections in self.conversation_connections.items():
            connections.discard(websocket)
        self.conversation_connections = {k: v for k, v in self.conversation_connections.items() if v}

    def is_user_connected(self, user_id: int) -> bool:
        return user_id in self.user_connections and len(self.user_connections[user_id]) > 0

    async def send_to_user(self, user_id: int, message: dict):
        if user_id not in self.user_connections:
            logger.debug(f"No connections found for user {user_id}")
            return

        message_str = json.dumps(message)
        dead_connections = set()

        for websocket in self.user_connections[user_id]:
            try:
                await websocket.send_text(message_str)
                logger.debug(f"📤 Message sent to user {user_id}")
            except Exception as e:
                logger.warning(f"Failed to send message to user {user_id}: {e}")
                dead_connections.add(websocket)

        for websocket in dead_connections:
            self.user_connections[user_id].discard(websocket)

    async def send_to_conversation(self, conversation_id: int, message: dict, exclude_user_id: Optional[int] = None):
        if conversation_id not in self.conversation_connections:
            logger.debug(f"No connections found for conversation {conversation_id}")
            return

        message_str = json.dumps(message)
        dead_connections = set()

        for websocket in self.conversation_connections[conversation_id]:
            try:
                await websocket.send_text(message_str)
                logger.debug(f"📤 Message sent to conversation {conversation_id}")
            except Exception as e:
                logger.warning(f"Failed to send message to conversation {conversation_id}: {e}")
                dead_connections.add(websocket)

        for websocket in dead_connections:
            self.conversation_connections[conversation_id].discard(websocket)

    async def broadcast_typing_status(self, conversation_id: int, user_id: int, is_typing: bool):
        import time

        if conversation_id not in self.typing_status:
            self.typing_status[conversation_id] = {}

        if is_typing:
            self.typing_status[conversation_id][user_id] = time.time()
        else:
            self.typing_status[conversation_id].pop(user_id, None)

        typing_users = list(self.typing_status[conversation_id].keys())
        await self.send_to_conversation(conversation_id, {
            'type': 'typing_status',
            'conversation_id': conversation_id,
            'typing_users': typing_users
        })

    def cleanup_old_typing_status(self, max_age_seconds: int = 10):
        import time
        current_time = time.time()

        for conversation_id in list(self.typing_status.keys()):
            for user_id in list(self.typing_status[conversation_id].keys()):
                if current_time - self.typing_status[conversation_id][user_id] > max_age_seconds:
                    del self.typing_status[conversation_id][user_id]

            if not self.typing_status[conversation_id]:
                del self.typing_status[conversation_id]

    async def send_message_notification(self, recipient_user_id: int, sender_name: str, message_preview: str, conversation_id: int):
        notification = {
            'type': 'message_notification',
            'title': f'Neue Nachricht von {sender_name}',
            'body': message_preview[:100] + ('...' if len(message_preview) > 100 else ''),
            'conversation_id': conversation_id,
            'timestamp': time.time()
        }

        await self.send_to_user(recipient_user_id, notification)

    async def send_unread_count_update(self, user_id: int, total_unread: int):
        await self.send_to_user(user_id, {
            'type': 'unread_count_update',
            'total_unread': total_unread
        })

    async def broadcast_privacy_change(self, user_id: int, messages_enabled: bool):
        privacy_event = {
            'type': 'privacy_settings_changed',
            'user_id': user_id,
            'messages_enabled': messages_enabled,
            'timestamp': time.time()
        }

        await self.send_to_user(user_id, privacy_event)

        logger.info(f"Privacy change broadcasted for user {user_id}")

    def get_connection_stats(self) -> dict:
        return {
            'global_connections': len(self.global_connections),
            'poll_connections': {k: len(v) for k, v in self.poll_connections.items()},
            'event_connections': {k: len(v) for k, v in self.event_connections.items()},
            'user_connections': {k: len(v) for k, v in self.user_connections.items()},
            'conversation_connections': {k: len(v) for k, v in self.conversation_connections.items()},
            'active_typing': {k: len(v) for k, v in self.typing_status.items()}
        }

    async def send_to_poll(self, poll_id: int, message: dict):
        if poll_id not in self.poll_connections:
            return

        message_str = json.dumps(message)
        dead_connections = set()

        for websocket in self.poll_connections[poll_id]:
            try:
                await websocket.send_text(message_str)
            except:
                dead_connections.add(websocket)

        for websocket in dead_connections:
            self.poll_connections[poll_id].discard(websocket)

    async def send_global_announcement(self, message: dict):
        message_str = json.dumps(message)
        dead_connections = set()

        for websocket in self.global_connections:
            try:
                await websocket.send_text(message_str)
            except:
                dead_connections.add(websocket)

        for websocket in dead_connections:
            self.global_connections.discard(websocket)

websocket_manager = WebSocketManager()
