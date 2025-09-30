from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websocket_service import websocket_manager
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/global")
async def websocket_global(websocket: WebSocket):
    await websocket_manager.connect(websocket, "global")

    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
        logger.info("📡 Global connection disconnected")


@router.websocket("/ws/poll/{poll_id}")
async def websocket_poll(websocket: WebSocket, poll_id: int):
    await websocket_manager.connect(websocket, "polls", poll_id)

    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)
        logger.info(f"📡 Poll {poll_id} connection disconnected")


# Usage in your poll voting endpoint:
# After successful vote, add this:
# await websocket_manager.send_to_poll(poll_id, {
#     "type": "vote_update",
#     "poll_id": poll_id,
#     "total_votes": new_total
# })
