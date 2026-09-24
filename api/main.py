from contextlib import asynccontextmanager
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent

from api.routers.agent_routes import router as agent_router
from api.routers.approval_routes import router as approval_router
from api.routers.auth_routes import router as auth_router
from api.routers.balitower_routes import router as balitower_router
from api.routers.stream_routes import router as stream_router
from core.config import settings
from core.security import TokenData, get_current_user
from mcp_server.server import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ensures storage directories and versioned DuckDB schema migrations are run safely.
    """
    STORAGE_DIR = WORKSPACE_DIR / "storage"
    DOCS_DIR = STORAGE_DIR / "documents"
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from database.migrations import run_migrations
        run_migrations()
    except Exception:
        logger.exception("Database startup migration failed")
        raise
    yield


app = FastAPI(
    title="AutoRestock-Agent API",
    description="Autonomous Multi-Agent Inventory Replenishment & Procurement System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Enable CORS for frontend dashboard (restricted to configured origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(settings, "ALLOWED_ORIGINS", ["http://localhost:8060", "http://127.0.0.1:8060"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static and storage directories
STATIC_DIR = WORKSPACE_DIR / "web" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

STORAGE_DIR = WORKSPACE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
# Generated documents contain tenant data and are served only by guarded API routes.



# Include API routers
app.include_router(balitower_router)
app.include_router(agent_router)
app.include_router(stream_router)
app.include_router(approval_router)
app.include_router(auth_router)

# Mount MCP Server SSE Endpoint
if settings.ENABLE_MCP:
    app.mount("/mcp", mcp.sse_app())

@app.get("/api/workflows/help-catalog", tags=["Workflows"])
async def workflows_help_catalog_alias(
    tenant: str | None = None,
    current_user: TokenData = Depends(get_current_user)
):
    from api.routers.auth_routes import get_help_catalog
    return await get_help_catalog(tenant, current_user=current_user)


@app.post("/api/workflows/request", tags=["Workflows"])
async def workflows_request_alias(
    req: dict, 
    current_user: TokenData = Depends(get_current_user)
):
    from api.routers.auth_routes import submit_workflow_request, WorkflowRequestPayload
    payload = WorkflowRequestPayload(
        prompt=req.get("prompt", ""),
        title=req.get("title"),
        notes=req.get("notes"),
        tenant_id=req.get("tenant_id")
    )
    return await submit_workflow_request(payload, current_user=current_user)




@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    icon_path = WORKSPACE_DIR / "web" / "static" / "images" / "balitower_mark.svg"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/svg+xml")
    return Response(status_code=204)


@app.get("/admin", tags=["Admin Portal"])
def admin_portal():
    admin_file = WORKSPACE_DIR / "web" / "static" / "admin.html"
    if admin_file.exists():
        return FileResponse(admin_file)
    index_file = WORKSPACE_DIR / "web" / "templates" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return Response(content="Admin Portal", media_type="text/html")


@app.get("/", tags=["Dashboard UI & Health"])
def root(request: Request):
    accept = request.headers.get("accept", "")
    index_file = WORKSPACE_DIR / "web" / "templates" / "index.html"
    
    # If a browser requests HTML
    if "text/html" in accept and index_file.exists() and not request.query_params.get("json"):
        return FileResponse(index_file)

    # API JSON response
    return {
        "service": "AutoRestock-Agent API",
        "status": "online",
        "version": "1.0.0",
        "supported_models": [settings.MODEL_NAME or "qwen-38"],
        "modules": [
            "Live Inventory & Dynamic Safety Stock",
            "Multi-Agent Procurement Orchestration",
            "Human-in-the-Loop Approval & Typst DocGen"
        ],
        "endpoints": {
            "inventory_items": "GET  /api/inventory/items",
            "inventory_summary": "GET  /api/stream/inventory-summary",
            "run_cycle":       "POST /api/agent/run-cycle",
            "stream_agent":    "GET  /api/stream/agent-run",
            "download_pr":     "GET  /api/documents/pr/{pr_number}/download",
            "approve_pr":      "POST /api/agent/approve",
            "approval_list":   "GET  /api/approval/list",
            "approval_action": "POST /api/approval/action",
            "docs":            "GET  /docs"
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Decoupled health check. Returns local service and DB status without failing
    liveness if external LLM services are temporarily degraded or disconnected.
    """
    import httpx
    from database.db import get_db_connection

    # 1. Local Database health check
    db_connected = False
    try:
        conn = get_db_connection(read_only=True)
        conn.execute("SELECT 1;").fetchone()
        conn.close()
        db_connected = True
    except Exception as e:
        logger.warning(f"Database health check failed: {e!s}")

    # 2. External LLM connectivity check (bounded timeout)
    llm_connected = False
    llm_error = None
    try:
        base_url = (settings.MODEL_URL or "").rstrip("/")
        if base_url:
            models_endpoint = base_url if base_url.endswith("/models") else f"{base_url}/models"
            async with httpx.AsyncClient(timeout=3.0) as client:
                headers = {}
                if settings.MODEL_API_KEY and settings.MODEL_API_KEY.strip():
                    headers["Authorization"] = f"Bearer {settings.MODEL_API_KEY.strip()}"
                res = await client.get(models_endpoint, headers=headers)
                llm_connected = (res.status_code == 200)
    except Exception as e:
        llm_error = str(e)
        logger.debug(f"LLM health check note for {settings.MODEL_URL}: {e!s}")

    return {
        "status": "healthy" if db_connected else "degraded",
        "local_service": "online",
        "database": "connected" if db_connected else "error",
        "llm_connected": llm_connected,
        "llm_error": llm_error
    }


@app.get("/health/live", tags=["Health"])
def liveness_check():
    """Liveness probe: verifies only that the local server process is responsive."""
    return {"status": "alive", "service": "AutoRestock-Agent"}


@app.get("/health/ready", tags=["Health"])
def readiness_check():
    """Readiness probe: verifies that internal database connectivity is active."""
    from database.db import get_db_connection
    try:
        conn = get_db_connection(read_only=True)
        conn.execute("SELECT 1;").fetchone()
        conn.close()
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unready: {e!s}")



if __name__ == "__main__":
    import uvicorn
    host = settings.API_HOST or "0.0.0.0"
    uvicorn.run("api.main:app", host=host, port=settings.API_PORT, reload=settings.DEBUG)

