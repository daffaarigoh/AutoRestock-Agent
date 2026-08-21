"""
Approval API Router
Handles PR approval workflow, rejection reasons, and PDF downloads.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import List, Optional
from pathlib import Path
from core.schemas import PurchaseRequisition, ApprovalActionRequest, PRStatus
from database.db import db
from core.observability import log_agent_step

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])


@router.get("/pending", response_model=List[PurchaseRequisition])
async def get_pending_approvals():
    return db.get_purchase_requisitions(status="pending_approval")


@router.get("/all", response_model=List[PurchaseRequisition])
async def get_all_prs(status: Optional[str] = None):
    return db.get_purchase_requisitions(status=status)


@router.get("/detail/{pr_number}", response_model=PurchaseRequisition)
async def get_pr_detail(pr_number: str):
    pr = db.get_pr_by_number(pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")
    return pr


@router.post("/action")
async def handle_approval_action(req: ApprovalActionRequest):
    new_status = PRStatus.APPROVED if req.action.lower() == "approve" else PRStatus.REJECTED
    rejection_reason = req.notes if new_status == PRStatus.REJECTED else None

    updated = db.update_pr_status(
        pr_number=req.pr_number,
        status=new_status,
        approver_name=req.approver_name,
        notes=req.notes,
        rejection_reason=rejection_reason
    )

    if not updated:
        raise HTTPException(status_code=404, detail="PR not found")

    # If approved, replenish catalog stock in database and dispatch PO to n8n
    if new_status == PRStatus.APPROVED:
        for pit in updated.items:
            db.update_stock(
                sku=pit.sku,
                change=pit.quantity,
                transaction_type="pr_approval_replenishment",
                ref_doc=updated.pr_number,
                notes=f"Stok bertambah otomatis saat PR {updated.pr_number} disetujui"
            )
        from core.n8n_client import n8n_client
        import asyncio
        try:
            asyncio.create_task(n8n_client.dispatch_approved_po(updated))
        except Exception:
            pass

    log_agent_step(
        step_name="Human Approval Decision",
        agent_name="ApprovalManager",
        status="success" if new_status == PRStatus.APPROVED else "warning",
        message=f"Purchase Requisition {req.pr_number} was {new_status.value.upper()} by {req.approver_name}."
    )

    return {"status": "success", "pr": updated}


@router.get("/download/{pr_number}")
async def download_pr_pdf(pr_number: str, download: bool = False):
    pr = db.get_pr_by_number(pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail="PR not found")

    # If PDF is missing or not found on disk, dynamically generate it on the fly!
    pdf_file = Path(pr.pdf_path) if pr.pdf_path else None
    if not pdf_file or not pdf_file.exists():
        from docgen.pdf_generator import pdf_generator
        try:
            new_pdf_path = pdf_generator.generate_pr_pdf(pr)
            pr.pdf_path = new_pdf_path
            db.save_purchase_requisition(pr)
            pdf_file = Path(new_pdf_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")

    if not pdf_file or not pdf_file.exists():
        raise HTTPException(status_code=404, detail="PDF file could not be rendered")

    disposition = "attachment" if download else "inline"
    headers = {"Content-Disposition": f'{disposition}; filename="{pr_number}.pdf"'}

    return FileResponse(
        path=str(pdf_file),
        media_type="application/pdf",
        headers=headers
    )
