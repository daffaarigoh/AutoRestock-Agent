"""
Observability and Event Broadcasting Module
Provides structured logging and real-time WebSocket/SSE broadcast capabilities for agent reasoning steps.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.schemas import AgentLogEvent

# Setup standard logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("AutoRestock-V2")


class EventBroadcaster:
    """
    Manages active WebSocket/SSE connections and in-memory event logs.
    """
    def __init__(self, max_history: int = 200):
        self.active_connections: List[Any] = []
        self.history: List[AgentLogEvent] = []
        self.max_history = max_history

    async def connect(self, websocket: Any):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected to event stream. Total clients: {len(self.active_connections)}")
        
        # Send recent history to newly connected client
        for event in self.history[-30:]:
            try:
                await websocket.send_text(json.dumps(event.model_dump()))
            except Exception:
                pass

    def disconnect(self, websocket: Any):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Remaining clients: {len(self.active_connections)}")

    async def broadcast(self, event: AgentLogEvent):
        # Store in history
        self.history.append(event)
        if len(self.history) > self.max_history:
            self.history.pop(0)

        # Broadcast to all live listeners
        dead_connections = []
        payload = json.dumps(event.model_dump())
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect(dead)

    def log_event_sync(
        self,
        step_name: str,
        agent_name: str,
        status: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ) -> AgentLogEvent:
        event = AgentLogEvent(
            timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            step_name=step_name,
            agent_name=agent_name,
            status=status,
            message=message,
            details=details
        )
        self.history.append(event)
        if len(self.history) > self.max_history:
            self.history.pop(0)
            
        # Log to server console
        log_level = logging.INFO
        if status == "error":
            log_level = logging.ERROR
        elif status == "warning":
            log_level = logging.WARNING
        logger.log(log_level, f"[{agent_name}] [{step_name}] {message}")
        
        # Non-blocking async broadcast if event loop is running
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.broadcast(event))
        except Exception:
            pass

        return event


# Global broadcaster instance
broadcaster = EventBroadcaster()


def log_agent_step(
    step_name: str,
    agent_name: str,
    status: str,
    message: str,
    details: Optional[Dict[str, Any]] = None
) -> AgentLogEvent:
    """Helper function to log an agent execution event synchronously and broadcast it."""
    return broadcaster.log_event_sync(step_name, agent_name, status, message, details)
