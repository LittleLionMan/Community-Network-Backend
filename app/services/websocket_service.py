from fastapi import WebSocket
from typing import Dict, List, Set, Optional
import json
import logging

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.poll_connections: Dict[int, Set[WebSocket]] = {}
        self.event_connections: Dict[int, Set[WebSocket]] = {}
        self.global_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, connection_type: str, item_id: Optional[int] = None):
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

    def disconnect(self, websocket: WebSocket):
        self.global_connections.discard(websocket)

        for item_id, connections in self.poll_connections.items():
            connections.discard(websocket)
        self.poll_connections = {k: v for k, v in self.poll_connections.items() if v}

        for item_id, connections in self.event_connections.items():
            connections.discard(websocket)
        self.event_connections = {k: v for k, v in self.event_connections.items() if v}

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
