"""
Real-Time Stream Router
WebSocket and Server-Sent Events (SSE) endpoints for live agent execution broadcasting.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import asyncio
import json
from core.observability import broadcaster

router = APIRouter(tags=["Live Streaming"])


@router.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket):
    await broadcaster.connect(websocket)
    try:
        while True:
            # Keep-alive heartbeat & listen for client messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)
    except Exception:
        broadcaster.disconnect(websocket)


@router.get("/api/stream/events")
async def sse_events_endpoint():
    """Fallback SSE endpoint for browsers without WebSocket support."""
    async def event_generator():
        # Emit recent history
        for event in broadcaster.history[-20:]:
            yield f"data: {json.dumps(event.model_dump())}\n\n"
        while True:
            await asyncio.sleep(2)
            yield f": keep-alive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
