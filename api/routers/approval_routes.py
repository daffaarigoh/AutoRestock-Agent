from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from bot.telegram_bot import telegram_bot
from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc

router = APIRouter(prefix="/api/approval", tags=["Human-in-the-Loop Approval"])

# In-memory PR storage (can be synced with DuckDB)
PR_STORE: dict[str, PurchaseRequisitionDoc] = {
    "PR-2026-0819-001": PurchaseRequisitionDoc(
        pr_number="PR-2026-0819-001",
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=[
            PurchaseItemRequest(
                item_id="ITEM-BAUT-M8",
                name="Baut Baja Hitam M8 x 50mm",
                reorder_qty=500,
                unit="pcs",
                vendor_id="VEND-001",
                vendor_name="PT. Sumber Makmur Fastener",
                unit_price=2500.0,
                total_price=1250000.0,
                reason="Stok fisik tersisa 12 pcs (di bawah threshold 100 pcs). Burn rate 25 pcs/hari."
            ),
            PurchaseItemRequest(
                item_id="ITEM-OLI-68",
                name="Oli Hidrolik ISO VG 68 20L",
                reorder_qty=4,
                unit="pail",
                vendor_id="VEND-002",
                vendor_name="PT. Pelumas Nusantara Jaya",
                unit_price=875000.0,
                total_price=3500000.0,
                reason="Stok tersisa 1 pail. Lead time supplier 3 hari kerja."
            )
        ],
        total_budget=4750000.0,
        auditor_status="PASSED",
        auditor_notes="Compliance check: Total PR Rp 4.750.000 tidak melebihi alokasi budget pengadaan Q3 (Rp 20.000.000).",
        pdf_path="/storage/documents/PR_2026_0819_001.pdf",
        status="PENDING_APPROVAL"
    )
}


class ApprovalActionPayload(BaseModel):
    pr_number: str
    action: str = "APPROVE"  # APPROVE | REJECT
    manager_name: Optional[str] = "Warehouse Manager"
    notes: Optional[str] = None


@router.get("/list", response_model=List[PurchaseRequisitionDoc])
async def get_all_requisitions():
    """
    Returns list of all active purchase requisitions and their approval statuses.
    """
    return list(PR_STORE.values())


@router.get("/{pr_number}", response_model=PurchaseRequisitionDoc)
async def get_requisition_by_number(pr_number: str):
    """
    Returns a single purchase requisition by PR Number.
    """
    pr = PR_STORE.get(pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail="Purchase Requisition not found.")
    return pr


@router.post("/action")
async def execute_approval_action(payload: ApprovalActionPayload):
    """
    Executes Human-In-The-Loop action (Approve or Reject) for a Purchase Requisition.
    """
    pr = PR_STORE.get(payload.pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail="Purchase Requisition not found.")

    if payload.action.upper() == "APPROVE":
        pr.status = "APPROVED"
        message = f"Dokumen {payload.pr_number} telah DISETUJUI oleh {payload.manager_name}. Status diteruskan ke Purchasing."
    else:
        pr.status = "REJECTED"
        message = f"Dokumen {payload.pr_number} telah DITOLAK oleh {payload.manager_name}."

    return {
        "status": "success",
        "pr_number": pr.pr_number,
        "new_status": pr.status,
        "message": message,
        "updated_at": datetime.now().isoformat()
    }


@router.post("/telegram-webhook")
async def telegram_webhook_handler(request: Request):
    """
    Handles incoming interactive callbacks from Telegram Bot inline buttons.
    """
    try:
        data = await request.json()
    except Exception:
        return {"status": "ignored"}

    callback = data.get("callback_query")
    if callback:
        callback_data = callback.get("data", "")
        # Format: "approve:PR-2026-0819-001" or "reject:PR-2026-0819-001"
        parts = callback_data.split(":")
        if len(parts) == 2:
            action, pr_num = parts[0], parts[1]
            if pr_num in PR_STORE:
                PR_STORE[pr_num].status = "APPROVED" if action == "approve" else "REJECTED"
                return {"status": "processed", "pr_number": pr_num, "action": action}

    return {"status": "ok"}
