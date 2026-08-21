"""
API Routers Package for AutoRestock-V2.
"""
from api.routers.inventory_router import router as inventory_router
from api.routers.ingest_router import router as ingest_router
from api.routers.agent_router import router as agent_router
from api.routers.approval_router import router as approval_router
from api.routers.stream_router import router as stream_router

__all__ = [
    "inventory_router",
    "ingest_router",
    "agent_router",
    "approval_router",
    "stream_router"
]
