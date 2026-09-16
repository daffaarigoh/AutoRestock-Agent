import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from api.routers.agent_routes import router as agent_router
from api.routers.approval_routes import PR_STORE
from api.routers.approval_routes import router as approval_router
from api.routers.auth_routes import router as auth_router
from api.routers.balitower_routes import router as balitower_router
from api.routers.stream_routes import router as stream_router
from core.config import settings
from docgen.compiler import generate_pr_pdf
from mcp_server.server import mcp

app = FastAPI(
    title="AutoRestock-Agent API",
    description="Autonomous Multi-Agent Inventory Replenishment & Procurement System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for frontend dashboard (restricted to configured origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=getattr(settings, "ALLOWED_ORIGINS", ["http://localhost:8050", "http://127.0.0.1:8050"]),
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
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")



# Include API routers
app.include_router(balitower_router)
app.include_router(agent_router)
app.include_router(stream_router)
app.include_router(approval_router)
app.include_router(auth_router)

# Mount MCP Server SSE Endpoint
app.mount("/mcp", mcp.sse_app())

@app.get("/api/workflows/help-catalog", tags=["Workflows"])
async def workflows_help_catalog_alias(tenant: str | None = None):
    from api.routers.auth_routes import get_help_catalog
    return await get_help_catalog(tenant)


@app.on_event("startup")
async def startup_event():
    """
    Ensures storage directories and initial sample PDF documents are generated.
    """
    DOCS_DIR = STORAGE_DIR / "documents"
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    sample_pr = PR_STORE.get("PR-2026-0819-001")
    if sample_pr:
        try:
            generate_pr_pdf(sample_pr, output_path=DOCS_DIR / "PR_2026_0819_001.pdf")
        except Exception:
            pass


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    icon_path = WORKSPACE_DIR / "web" / "static" / "images" / "balitower_mark.svg"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/svg+xml")
    return Response(status_code=204)


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
        "supported_models": ["nemotron-35"],
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
    import httpx
    from fastapi import HTTPException
    try:
        base_url = (settings.MODEL_URL or "").rstrip("/")
        models_endpoint = base_url if base_url.endswith("/models") else f"{base_url}/models"

        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = {}
            if settings.MODEL_API_KEY and settings.MODEL_API_KEY.strip():
                headers["Authorization"] = f"Bearer {settings.MODEL_API_KEY.strip()}"
            res = await client.get(models_endpoint, headers=headers)
            res.raise_for_status()
        return {"status": "healthy", "llm_connected": True, "llm_url": settings.MODEL_URL}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"LLM Disconnected ({settings.MODEL_URL}): {e!s}")


if __name__ == "__main__":
    import uvicorn
    host = settings.API_HOST or "0.0.0.0"
    uvicorn.run("api.main:app", host=host, port=settings.API_PORT, reload=settings.DEBUG)

