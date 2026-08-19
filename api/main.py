from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routers.approval_routes import router as approval_router
from api.routers.ingest_routes import router as ingest_router
from api.routers.stream_routes import router as stream_router
from core.config import settings
from docgen.pdf_generator import pdf_generator
from api.routers.approval_routes import PR_STORE

app = FastAPI(
    title="AutoRestock-Agent API",
    description="Autonomous Multi-Agent Inventory Restock & Procurement System with LightOn OCR & Typst Typesetting",
    version="1.0.0",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(ingest_router)
app.include_router(stream_router)
app.include_router(approval_router)

# Mount Static Directories
STATIC_DIR = settings.BASE_DIR / "web" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.mount("/storage", StaticFiles(directory=str(settings.STORAGE_DIR)), name="storage")


@app.on_event("startup")
async def startup_event():
    """
    Ensures storage directories and initial sample PDF documents are generated.
    """
    settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    sample_pr = PR_STORE.get("PR-2026-0819-001")
    if sample_pr:
        pdf_generator.generate_purchase_requisition_pdf(sample_pr, output_filename="PR_2026_0819_001.pdf")


@app.get("/", tags=["Dashboard UI"])
async def serve_dashboard():
    """
    Serves the main interactive dashboard interface.
    """
    index_file = settings.BASE_DIR / "web" / "templates" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "AutoRestock-Agent API Online", "docs": "/docs"}


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}
