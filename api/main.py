"""
FastAPI Server Entrypoint for AutoRestock-V2
Provides unified REST, WebSocket, Static Web Dashboard, and Storage endpoints.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os

from core.config import settings, ensure_directories
from database.db import db
from database.seed_data import seed_database
from api.routers import (
    inventory_router,
    ingest_router,
    agent_router,
    approval_router,
    stream_router
)

# Initialize app
app = FastAPI(
    title="AutoRestock-V2 Enterprise Multi-Agent System",
    description="Autonomous inventory restocking, document OCR auditing, and purchase requisition lifecycle management.",
    version="2.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure directories
ensure_directories()

# Mount Static and Storage directories
web_dir = Path(__file__).resolve().parent.parent / "web"
static_dir = web_dir / "static"
storage_dir = settings.STORAGE_DIR

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

if storage_dir.exists():
    app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")

# Include API Routers
app.include_router(inventory_router)
app.include_router(ingest_router)
app.include_router(agent_router)
app.include_router(approval_router)
app.include_router(stream_router)


@app.on_event("startup")
async def startup_event():
    """Seed initial catalog data if inventory is empty."""
    items = db.get_items()
    if not items:
        seed_database()


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the primary enterprise web dashboard."""
    index_file = web_dir / "templates" / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>AutoRestock-V2 Backend Online</h1><p>Web dashboard template is loading...</p>")


@app.get("/health")
async def healthcheck():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": "2.0.0",
        "mock_mode": settings.MOCK_MODELS
    }
