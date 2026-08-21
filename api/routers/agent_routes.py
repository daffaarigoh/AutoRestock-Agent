import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from agents.state import PurchaseRequisition
from agents.workflow import run_autorestock_cycle, resume_approval
from mcp_server.tools import get_all_inventory_items
from database.db import get_db_connection

router = APIRouter(tags=["AutoRestock Agent"])

STORAGE_DIR = WORKSPACE_DIR / "storage"


class ApprovalRequest(BaseModel):
    pr_number: str = Field(..., description="Purchase Requisition number to approve or reject")
    action: str = Field("APPROVE", description="Decision action: 'APPROVE' or 'REJECT'")
    approver_name: Optional[str] = Field("Warehouse Operations Manager", description="Name/Role of approver")
    notes: Optional[str] = Field("Approved for vendor procurement", description="Manager review notes")


class ApprovalResponse(BaseModel):
    pr_number: str
    status: str
    approver: str
    message: str
    pr_document: Optional[PurchaseRequisition] = None


@router.get("/api/inventory/items", response_model=List[Dict[str, Any]])
def get_inventory_items():
    """
    Retrieve all inventory items from DuckDB.
    """
    try:
        items = get_all_inventory_items()
        return items
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch inventory items: {str(e)}"
        )


@router.post("/api/agent/run-cycle", response_model=PurchaseRequisition)
def run_agent_cycle():
    """
    Triggers the LangGraph multi-agent workflow:
    1. Scan items below safety threshold.
    2. Planner (qwen-35b) matches optimal vendors & calculates budget.
    3. Auditor (nemotron-35) enforces compliance guardrails.
    4. Typst compiles the formal Purchase Requisition PDF.
    5. Graph pauses before Wait Approval Node (HITL).
    """
    try:
        pr_document = run_autorestock_cycle()
        if pr_document:
            from api.routers.approval_routes import PR_STORE
            from core.schemas import PurchaseRequisitionDoc, PurchaseItemRequest
            from docgen.pdf_generator import pdf_generator
            
            items_req = [
                PurchaseItemRequest(
                    item_id=it.item_id,
                    name=it.name,
                    reorder_qty=it.reorder_qty,
                    unit=it.unit,
                    vendor_id=it.vendor_id,
                    vendor_name=it.vendor_name,
                    unit_price=it.unit_price,
                    total_price=it.total_price,
                    reason=it.reason
                )
                for it in pr_document.items
            ]
            clean_filename = f"{pr_document.pr_number.replace('-', '_')}.pdf"
            PR_STORE[pr_document.pr_number] = PurchaseRequisitionDoc(
                pr_number=pr_document.pr_number,
                created_at=pr_document.created_at,
                items=items_req,
                total_budget=pr_document.total_budget,
                auditor_status=pr_document.auditor_status or "PASSED",
                auditor_notes=pr_document.auditor_notes or "Audit passed.",
                pdf_path=f"/storage/documents/{clean_filename}",
                status=pr_document.status or "PENDING"
            )
            pdf_generator.generate_purchase_requisition_pdf(PR_STORE[pr_document.pr_number], output_filename=clean_filename)
        return pr_document
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AutoRestock agent cycle failed: {str(e)}"
        )



@router.get("/api/documents/pr/{pr_number}/download")
def download_pr_document(pr_number: str):
    """
    Downloads the generated Typst Purchase Requisition PDF for a given pr_number.
    Checks approved/, rejected/, and pending/ folders in priority order.
    """
    clean_pr_num = pr_number.replace("/", "_").replace("\\", "_")
    
    # Priority search locations
    candidate_paths = [
        STORAGE_DIR / "approved" / f"{clean_pr_num}.pdf",
        STORAGE_DIR / "rejected" / f"{clean_pr_num}.pdf",
        STORAGE_DIR / "pending" / f"{clean_pr_num}.pdf",
        STORAGE_DIR / f"{clean_pr_num}.pdf"
    ]
    
    found_path = None
    for path in candidate_paths:
        if path.exists():
            found_path = path
            break
            
    # Recursive wildcard search fallback
    if found_path is None:
        matches = list(STORAGE_DIR.rglob(f"*{clean_pr_num}*.pdf"))
        if matches:
            found_path = matches[0]

    if found_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase Requisition PDF '{pr_number}' not found in storage (checked approved, rejected, and pending folders)."
        )
            
    return FileResponse(
        path=str(found_path),
        media_type="application/pdf",
        filename=f"{clean_pr_num}.pdf"
    )


@router.post("/api/agent/approve", response_model=ApprovalResponse)
def approve_pr_requisition(request: ApprovalRequest):
    """
    Handles Human-In-The-Loop (HITL) approval for a Purchase Requisition:
    - If APPROVE: Updates DuckDB orders table status to 'APPROVED' and resumes the paused LangGraph workflow.
    - If REJECT: Updates DuckDB orders table status to 'REJECTED'.
    """
    try:
        action = request.action.upper()
        if action not in ["APPROVE", "REJECT"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action must be either 'APPROVE' or 'REJECT'."
            )
            
        updated_pr = resume_approval(
            pr_number=request.pr_number,
            action=action,
            approver_name=request.approver_name or "Manager",
            notes=request.notes or ""
        )
        
        final_status = "APPROVED" if action == "APPROVE" else "REJECTED"
        msg = f"Purchase Requisition {request.pr_number} successfully {final_status} by {request.approver_name}."
        
        return ApprovalResponse(
            pr_number=request.pr_number,
            status=final_status,
            approver=request.approver_name or "Manager",
            message=msg,
            pr_document=updated_pr
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process PR approval: {str(e)}"
        )


class UpdateItemThresholdRequest(BaseModel):
    min_threshold: Optional[int] = Field(None, description="New minimum safety threshold")
    current_stock: Optional[int] = Field(None, description="Optional update to current physical stock")
    avg_daily_usage: Optional[float] = Field(None, description="Optional update to daily usage burn rate")
    lead_time_days: Optional[int] = Field(None, description="Optional update to vendor lead time")


@router.patch("/api/inventory/items/{item_id}")
def update_item_threshold(item_id: str, payload: UpdateItemThresholdRequest):
    """
    Updates threshold and inventory parameters for a specific item in DuckDB.
    """
    conn = get_db_connection()
    try:
        existing = conn.execute("SELECT item_id, name, min_threshold, current_stock FROM items WHERE item_id = ?", [item_id]).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Item with ID '{item_id}' not found in inventory.")

        updates = []
        params = []
        if payload.min_threshold is not None:
            updates.append("min_threshold = ?")
            params.append(payload.min_threshold)
        if payload.current_stock is not None:
            updates.append("current_stock = ?")
            params.append(payload.current_stock)
        if payload.avg_daily_usage is not None:
            updates.append("avg_daily_usage = ?")
            params.append(payload.avg_daily_usage)
        if payload.lead_time_days is not None:
            updates.append("lead_time_days = ?")
            params.append(payload.lead_time_days)

        if not updates:
            return {"status": "no_change", "message": "No parameters provided to update."}

        params.append(item_id)
        sql = f"UPDATE items SET {', '.join(updates)} WHERE item_id = ?;"
        conn.execute(sql, params)

        # Retrieve updated record
        updated_row = conn.execute("""
            SELECT item_id, name, category, current_stock, min_threshold, avg_daily_usage, lead_time_days, unit
            FROM items WHERE item_id = ?;
        """, [item_id]).fetchone()
        columns = [d[0] for d in conn.description]
        updated_item = dict(zip(columns, updated_row))

        return {
            "status": "success",
            "message": f"Berhasil memperbarui {existing[1]} ({item_id}).",
            "item": updated_item
        }
    finally:
        conn.close()


class CustomPromptRequest(BaseModel):
    prompt: str = Field(..., description="Natural language prompt from user describing restock intent or workflow")
    destinations: Optional[List[str]] = Field(None, description="Explicit destinations: ['database', 'email', 'telegram', 'n8n', 'pdf']")
    recipient_email: Optional[str] = Field(None, description="Optional custom recipient email")


@router.post("/api/agent/custom-prompt")
async def execute_custom_prompt_workflow(request: CustomPromptRequest):
    """
    Accepts free-form natural language instructions from non-technical users,
    synthesizes a custom multi-agent workflow, executes actions, and dispatches outputs.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt tidak boleh kosong.")

    from agents.dynamic_workflow import workflow_synthesizer
    try:
        result = await workflow_synthesizer.execute_dynamic_workflow(
            prompt=request.prompt,
            override_destinations=request.destinations,
            override_email=request.recipient_email
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal mengeksekusi dynamic workflow: {str(e)}"
        )


@router.get("/api/agent/prompt-templates")
def get_prompt_templates():
    """
    Returns curated 1-click prompt templates for non-technical users.
    """
    return [
        {
            "id": 1,
            "title": "Restock Darurat Elektronik -> Telegram",
            "prompt": "Tolong cek semua barang kategori Electronics yang stoknya kritis, pilihkan vendor termurah, buatkan dokumen PDF, dan kirim notifikasi ke Telegram."
        },
        {
            "id": 2,
            "title": "Update Threshold STM32 & Simpan DB",
            "prompt": "Ubah threshold barang ITM-001 jadi 80 pcs, lalu hitung ulang kebutuhan restock dan simpan hasilnya di database saja."
        },
        {
            "id": 3,
            "title": "Rekap Stok Kemasan -> Email & n8n",
            "prompt": "Buatkan rekap laporan restock barang Packaging dan kirimkan ke email manager@company.com serta webhook n8n."
        },
        {
            "id": 4,
            "title": "Audit Lengkap Semua Barang Gudang",
            "prompt": "Periksa semua barang di gudang yang di bawah threshold, buatkan draf Purchase Requisition PDF resmi."
        }
    ]

