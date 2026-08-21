"""
Agent API Router
Exposes natural language prompt restock, full catalog autonomous scans, and discrepancy logs.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List, Dict, Any
from core.schemas import PromptRestockRequest, PromptRestockResponse
from agents.workflow import workflow
from database.db import db

router = APIRouter(prefix="/api/agent", tags=["Agent Workflow"])


@router.post("/prompt-restock", response_model=Dict[str, Any])
async def prompt_restock(request: PromptRestockRequest):
    """Parses natural language prompt and runs targeted restocking, catalog updates, or n8n actions."""
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    result = await workflow.execute_prompt_restock(request.prompt, auto_execute=request.auto_execute)

    return {
        "status": result.get("status", "completed"),
        "prompt": request.prompt,
        "parsed_intent": result.get("parsed_intent"),
        "action_type": result.get("action_type", "restock"),
        "affected_items": result.get("affected_items", []),
        "restock_candidates": result.get("restock_candidates", []),
        "generated_prs": result.get("generated_prs", []),
        "message": result.get("message", "Operasi berhasil diselesaikan.")
    }


@router.post("/scan-all")
async def scan_inventory():
    """Runs a full inventory check across all categories and generates PRs for depleted items."""
    result = await workflow.execute_inventory_scan()
    return {
        "status": result.get("status", "completed"),
        "generated_prs": result.get("generated_prs", []),
        "candidates_count": len(result.get("restock_candidates", [])),
        "message": result.get("message", "Catalog scan completed.")
    }


@router.get("/discrepancies")
async def get_discrepancies(status: str = "open"):
    """Fetches logged inventory discrepancies."""
    return db.get_discrepancies(status=status)


@router.post("/upload-media")
async def upload_media_document(
    file: UploadFile = File(...),
    prompt: str = Form(""),
    auto_execute: bool = Form(True)
):
    """
    Ingests media/document attachments (receipt, struk, invoice, csv, photo),
    runs multimodal extraction, and executes user instructions.
    """
    import os
    import shutil
    from pathlib import Path

    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    file_path = upload_dir / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = await workflow.execute_document_ingest(
        file_path=str(file_path),
        prompt=prompt,
        auto_execute=auto_execute
    )
    return result
