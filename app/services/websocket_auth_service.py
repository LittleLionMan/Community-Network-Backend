import asyncio
import json
import time
from fastapi import WebSocket
from sqlalchemy import select
from typing import cast

from ..core.auth import verify_token
from ..models.user import User
from ..database import AsyncSessionLocal


class WebSocketAuthManager:
    def __init__(self):
        self.authenticated_connections: dict[WebSocket, dict[str, object]] = {}
        self.last_heartbeat: dict[WebSocket, float] = {}
        self._cleanup_task: asyncio.Task[None] | None = None

    async def authenticate_connection(
        self,
        websocket: WebSocket,
        token: str,
        connection_type: str,
        item_id: int | None = None,
    ) -> int | None:
        try:
            payload = verify_token(token, token_type="access")
            if not payload:
                await websocket.close(code=4001, reason="Invalid token")
                return None

            user_id_value = payload.get("sub")
            if not user_id_value:
                raise ValueError("No user ID in token payload")

            try:
                user_id: int = int(cast(str, user_id_value))
            except (ValueError, TypeError):
                raise ValueError("Invalid user ID format in token")

            if not user_id:
                await websocket.close(code=4001, reason="Invalid token payload")
                return None

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(User).where(User.id == int(user_id), User.is_active)
                )
                user = result.scalar_one_or_none()

                if not user:
                    await websocket.close(
                        code=4002, reason="User not found or inactive"
                    )
                    return None

            self.authenticated_connections[websocket] = {
                "user_id": int(user_id),
                "connection_type": connection_type,
                "item_id": item_id,
                "connected_at": time.time(),
                "last_token_refresh": time.time(),
                "token": token,
            }

            self.last_heartbeat[websocket] = time.time()

            if not self._cleanup_task or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

            return int(user_id)

        except Exception as e:
            await websocket.close(code=4003, reason=f"Authentication error: {str(e)}")
            return None

    async def handle_websocket_message(
        self, websocket: WebSocket, message_data: dict[str, object]
    ) -> bool:
        message_type = message_data.get("type")

        if message_type == "heartbeat":
            self.last_heartbeat[websocket] = time.time()
            await websocket.send_text(
                json.dumps({"type": "heartbeat_ack", "timestamp": time.time()})
            )
            return True

        elif message_type == "refresh_token":
            new_token = message_data.get("token")
            if not new_token or not isinstance(new_token, str):
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "token_refreshed",
                            "success": True,
                            "error": "Invalid token provided",
                        }
                    )
                )
                return True

            if await self._refresh_connection_token(websocket, new_token):
                await websocket.send_text(
                    json.dumps({"type": "token_refreshed", "success": True})
                )
            else:
                await websocket.send_text(
                    json.dumps({"type": "token_refresh_failed", "success": False})
                )
            return True

        elif message_type == "ping":
            await websocket.send_text(json.dumps({"type": "pong"}))
            return True

        return False

    async def _refresh_connection_token(
        self, websocket: WebSocket, new_token: str
    ) -> bool:
        try:
            conn_info = self.authenticated_connections.get(websocket)
            if not conn_info:
                return False

            payload = verify_token(new_token, token_type="access")
            if not payload:
                return False

            token_user_id_value = payload.get("sub")
            if not token_user_id_value:
                raise ValueError("No user ID in token payload")

            try:
                token_user_id: int = int(cast(str, token_user_id_value))
            except (ValueError, TypeError):
                raise ValueError("Invalid user ID format in token")

            if not token_user_id or int(token_user_id) != conn_info["user_id"]:
                return False

            conn_info["token"] = new_token
            conn_info["last_token_refresh"] = time.time()

            return True

        except Exception as e:
            print(f"Token refresh failed: {e}")
            return False

    async def _periodic_cleanup(self):
        while True:
            try:
                await asyncio.sleep(30)
                current_time = time.time()
                stale_connections: list[WebSocket] = []

                for websocket, conn_info in self.authenticated_connections.items():
                    last_heartbeat = self.last_heartbeat.get(websocket, 0)
                    if current_time - last_heartbeat > 120:
                        stale_connections.append(websocket)
                        continue

                    last_refresh = conn_info.get("last_token_refresh", 0)
                    if (
                        isinstance(last_refresh, (int, float))
                        and current_time - last_refresh > 1500
                    ):
                        try:
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "token_expiring",
                                        "expires_in": 300,
                                        "message": "Please refresh your authentication token",
                                    }
                                )
                            )
                        except:
                            stale_connections.append(websocket)

                for websocket in stale_connections:
                    await self.disconnect(websocket, reason="Connection timeout")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Cleanup task error: {e}")
                await asyncio.sleep(60)

    async def disconnect(self, websocket: WebSocket, reason: str = "Disconnected"):
        try:
            await websocket.close(code=1000, reason=reason)
        except:
            pass

        _ = self.authenticated_connections.pop(websocket, None)
        _ = self.last_heartbeat.pop(websocket, None)

    def get_connection_info(self, websocket: WebSocket) -> dict[str, object] | None:
        return self.authenticated_connections.get(websocket)

    def get_user_connections(self, user_id: int) -> set[WebSocket]:
        return {
            websocket
            for websocket, info in self.authenticated_connections.items()
            if info["user_id"] == user_id
        }


websocket_auth_manager = WebSocketAuthManager()
