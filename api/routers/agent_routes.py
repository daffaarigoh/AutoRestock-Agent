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
