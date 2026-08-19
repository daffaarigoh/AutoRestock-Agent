from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from bot.telegram_bot import telegram_bot
from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc

router = APIRouter(prefix="/api/approval", tags=["Human-in-the-Loop Approval"])

# Real 5 Critical Items PR Document matching DuckDB
PR_STORE: dict[str, PurchaseRequisitionDoc] = {
    "PR-2026-0819-001": PurchaseRequisitionDoc(
        pr_number="PR-2026-0819-001",
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=[
            PurchaseItemRequest(
                item_id="ITM-001",
                name="Microcontroller STM32F401",
                reorder_qty=76,
                unit="pcs",
                vendor_id="VND-001",
                vendor_name="PT. Elektronika Jaya Prima",
                unit_price=65000.0,
                total_price=4940000.0,
                reason="Stok fisik 12 pcs di bawah safety threshold (50 pcs). Burn rate 8.5/hari."
            ),
            PurchaseItemRequest(
                item_id="ITM-002",
                name="ESP32-WROOM-32D Module",
                reorder_qty=52,
                unit="pcs",
                vendor_id="VND-002",
                vendor_name="CV. Komponen Nusantara",
                unit_price=39500.0,
                total_price=2054000.0,
                reason="Stok fisik 8 pcs di bawah safety threshold (40 pcs). Burn rate 6.0/hari."
            ),
            PurchaseItemRequest(
                item_id="ITM-003",
                name="Thermal Paste Arctic MX-4 4g",
                reorder_qty=33,
                unit="tube",
                vendor_id="VND-003",
                vendor_name="PT. Sumber Makmur Fastener",
                unit_price=48000.0,
                total_price=1584000.0,
                reason="Stok fisik 5 tube di bawah safety threshold (25 tube). Burn rate 3.2/hari."
            ),
            PurchaseItemRequest(
                item_id="ITM-004",
                name="Cardboard Box 30x20x15cm",
                reorder_qty=190,
                unit="pcs",
                vendor_id="VND-004",
                vendor_name="PT. Kemasan Indah Perkasa",
                unit_price=4200.0,
                total_price=798000.0,
                reason="Stok fisik 35 pcs di bawah safety threshold (150 pcs). Burn rate 25/hari."
            ),
            PurchaseItemRequest(
                item_id="ITM-005",
                name="Bubble Wrap Roll 50m x 50cm",
                reorder_qty=17,
                unit="roll",
                vendor_id="VND-004",
                vendor_name="PT. Kemasan Indah Perkasa",
                unit_price=72000.0,
                total_price=1224000.0,
                reason="Stok fisik 4 roll di bawah safety threshold (15 roll). Burn rate 2.0/hari."
            )
        ],
        total_budget=10600000.0,
        auditor_status="PASSED",
        auditor_notes="Compliance check: Total PR Rp 10.600.000 sesuai alokasi pengadaan inventaris Q3.",
        pdf_path="/storage/documents/PR_2026_0819_001.pdf",
        status="PENDING"
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
    Automatically regenerates the formal Typst PDF document with the updated status.
    """
    pr = PR_STORE.get(payload.pr_number)
    if not pr:
        raise HTTPException(status_code=404, detail="Purchase Requisition not found.")

    if payload.action.upper() == "APPROVE":
        pr.status = "APPROVED"
        message = f"Dokumen {payload.pr_number} telah disetujui oleh {payload.manager_name}. Status diteruskan ke Purchasing."
        
        # Persist updated stock into DuckDB
        try:
            from database.db import get_db_connection
            conn = get_db_connection()
            for item in pr.items:
                conn.execute("""
                    UPDATE items
                    SET current_stock = current_stock + ?
                    WHERE item_id = ? OR name = ?;
                """, [item.reorder_qty, item.item_id, item.name])
            conn.execute("""
                UPDATE orders
                SET status = 'APPROVED'
                WHERE pr_number = ?;
            """, [pr.pr_number])
            conn.close()
        except Exception as e:
            print(f"[APPROVAL] Warning updating DuckDB stock: {e}")
    else:
        pr.status = "REJECTED"
        message = f"Dokumen {payload.pr_number} telah ditolak oleh {payload.manager_name}."
        try:
            from database.db import get_db_connection
            conn = get_db_connection()
            conn.execute("""
                UPDATE orders
                SET status = 'REJECTED'
                WHERE pr_number = ?;
            """, [pr.pr_number])
            conn.close()
        except Exception as e:
            pass

    # Regenerate Typst PDF with new status
    try:
        from docgen.pdf_generator import pdf_generator
        clean_filename = f"{pr.pr_number.replace('-', '_')}.pdf"
        pdf_generator.generate_purchase_requisition_pdf(pr, output_filename=clean_filename)
        pr.pdf_path = f"/storage/documents/{clean_filename}"
    except Exception as e:
        pass

    return {
        "status": "success",
        "pr_number": pr.pr_number,
        "new_status": pr.status,
        "message": message,
        "updated_at": datetime.now().isoformat()
    }




@router.post("/reset")
async def reset_sample_data():
    """
    Resets PR_STORE to clean initial PENDING state, resets DuckDB stock to initial state, and regenerates the clean initial PDF.
    """
    try:
        from database.seed_data import init_db, seed_data
        conn = init_db()
        seed_data(conn)
        conn.close()
    except Exception as e:
        print(f"[RESET] Warning re-seeding DuckDB: {e}")

    PR_STORE["PR-2026-0819-001"] = PurchaseRequisitionDoc(
        pr_number="PR-2026-0819-001",
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=[
            PurchaseItemRequest(
                item_id="ITM-001",
                name="Microcontroller STM32F401",
                reorder_qty=76,
                unit="pcs",
                vendor_id="VND-001",
                vendor_name="PT. Elektronika Jaya Prima",
                unit_price=65000.0,
                total_price=4940000.0,
                reason="Stok fisik 12 pcs di bawah safety threshold (50 pcs). Burn rate 8.5/hari."
            ),
            PurchaseItemRequest(
                item_id="ITM-002",
                name="ESP32-WROOM-32D Module",
                reorder_qty=52,
                unit="pcs",
                vendor_id="VND-002",
                vendor_name="CV. Komponen Nusantara",
                unit_price=39500.0,
                total_price=2054000.0,
                reason="Stok fisik 8 pcs di bawah safety threshold (40 pcs). Burn rate 6.0/hari."
            ),
            PurchaseItemRequest(
                item_id="ITM-003",
                name="Thermal Paste Arctic MX-4 4g",
                reorder_qty=33,
                unit="tube",
                vendor_id="VND-003",
                vendor_name="PT. Sumber Makmur Fastener",
                unit_price=48000.0,
                total_price=1584000.0,
                reason="Stok fisik 5 tube di bawah safety threshold (25 tube). Burn rate 3.2/hari."
            ),
            PurchaseItemRequest(
                item_id="ITM-004",
                name="Cardboard Box 30x20x15cm",
                reorder_qty=190,
                unit="pcs",
                vendor_id="VND-004",
                vendor_name="PT. Kemasan Indah Perkasa",
                unit_price=4200.0,
                total_price=798000.0,
                reason="Stok fisik 35 pcs di bawah safety threshold (150 pcs). Burn rate 25/hari."
            ),
            PurchaseItemRequest(
                item_id="ITM-005",
                name="Bubble Wrap Roll 50m x 50cm",
                reorder_qty=17,
                unit="roll",
                vendor_id="VND-004",
                vendor_name="PT. Kemasan Indah Perkasa",
                unit_price=72000.0,
                total_price=1224000.0,
                reason="Stok fisik 4 roll di bawah safety threshold (15 roll). Burn rate 2.0/hari."
            )
        ],
        total_budget=10600000.0,
        auditor_status="PASSED",
        auditor_notes="Compliance check: Total PR Rp 10.600.000 sesuai alokasi pengadaan inventaris Q3.",
        pdf_path="/storage/documents/PR_2026_0819_001.pdf",
        status="PENDING"
    )
    try:
        from docgen.pdf_generator import pdf_generator
        pdf_generator.generate_purchase_requisition_pdf(PR_STORE["PR-2026-0819-001"], output_filename="PR_2026_0819_001.pdf")
    except Exception:
        pass

    return {"status": "reset", "message": "PR-2026-0819-001 reset to PENDING status with all 5 DuckDB critical items."}



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
                try:
                    from docgen.pdf_generator import pdf_generator
                    clean_filename = f"{pr_num.replace('-', '_')}.pdf"
                    pdf_generator.generate_purchase_requisition_pdf(PR_STORE[pr_num], output_filename=clean_filename)
                except Exception:
                    pass
                return {"status": "processed", "pr_number": pr_num, "action": action}

    return {"status": "ok"}

