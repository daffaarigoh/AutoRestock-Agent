"""
Ingestion API Router
Handles document upload (Surat Jalan, Kartu Stok, Faktur), runs OCR, visualizer, and autonomous workflow.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
import shutil
from datetime import datetime

from core.config import settings
from agents.workflow import workflow
from database.db import db

router = APIRouter(prefix="/api/ingest", tags=["Document Ingestion"])


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Uploads a warehouse document and triggers autonomous extraction and auditing."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename missing")

    ext = Path(file.filename).suffix.lower()
    if ext not in [".jpg", ".jpeg", ".png", ".pdf", ".bmp", ".tiff"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload JPG, PNG, or PDF.")

    # Save to storage/uploads
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename.replace(' ', '_')}"
    save_path = settings.STORAGE_DIR / "uploads" / safe_filename

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Execute workflow
    result = await workflow.execute_document_ingest(str(save_path))

    return {
        "status": result.get("status", "completed"),
        "filename": safe_filename,
        "extracted_doc": result.get("extracted_doc"),
        "discrepancy_report": result.get("discrepancy_report"),
        "annotated_image": Path(result.get("annotated_image_path", "")).name if result.get("annotated_image_path") else None,
        "generated_prs": result.get("generated_prs", []),
        "requires_approval": result.get("requires_approval", False)
    }
