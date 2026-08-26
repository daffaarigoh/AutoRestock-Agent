from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
from core.security import TokenData, get_current_user

router = APIRouter(prefix="/api/approval", tags=["Human-in-the-Loop Approval"])


# --- Default PR Data Factory (Single Source of Truth) ---

DEFAULT_PR_ITEMS = [
    PurchaseItemRequest(
        item_id="ITM-001", name="Microcontroller STM32F401",
        reorder_qty=76, unit="pcs", vendor_id="VND-001",
        vendor_name="PT. Elektronika Jaya Prima",
        unit_price=65000.0, total_price=4940000.0,
        reason="Stok fisik 12 pcs di bawah safety threshold (50 pcs). Burn rate 8.5/hari."
    ),
    PurchaseItemRequest(
        item_id="ITM-002", name="ESP32-WROOM-32D Module",
        reorder_qty=52, unit="pcs", vendor_id="VND-002",
        vendor_name="CV. Komponen Nusantara",
        unit_price=39500.0, total_price=2054000.0,
        reason="Stok fisik 8 pcs di bawah safety threshold (40 pcs). Burn rate 6.0/hari."
    ),
    PurchaseItemRequest(
        item_id="ITM-003", name="Thermal Paste Arctic MX-4 4g",
        reorder_qty=33, unit="tube", vendor_id="VND-003",
        vendor_name="PT. Sumber Makmur Fastener",
        unit_price=48000.0, total_price=1584000.0,
        reason="Stok fisik 5 tube di bawah safety threshold (25 tube). Burn rate 3.2/hari."
    ),
    PurchaseItemRequest(
        item_id="ITM-004", name="Cardboard Box 30x20x15cm",
        reorder_qty=190, unit="pcs", vendor_id="VND-004",
        vendor_name="PT. Kemasan Indah Perkasa",
        unit_price=4200.0, total_price=798000.0,
        reason="Stok fisik 35 pcs di bawah safety threshold (150 pcs). Burn rate 25/hari."
    ),
    PurchaseItemRequest(
        item_id="ITM-005", name="Bubble Wrap Roll 50m x 50cm",
        reorder_qty=17, unit="roll", vendor_id="VND-004",
        vendor_name="PT. Kemasan Indah Perkasa",
        unit_price=72000.0, total_price=1224000.0,
        reason="Stok fisik 4 roll di bawah safety threshold (15 roll). Burn rate 2.0/hari."
    )
]


def _create_default_pr(pr_number: str = "PR-2026-0819-001", status: str = "PENDING") -> PurchaseRequisitionDoc:
    """Factory function to create a default PR document. Single source of truth."""
    return PurchaseRequisitionDoc(
        pr_number=pr_number,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=DEFAULT_PR_ITEMS,
        total_budget=10600000.0,
        auditor_status="PASSED",
        auditor_notes="Compliance check: Total PR Rp 10.600.000 sesuai alokasi pengadaan inventaris Q3.",
        pdf_path=f"/storage/documents/{pr_number.replace('-', '_')}.pdf",
        status=status
    )


# In-memory PR Store
PR_STORE: dict[str, PurchaseRequisitionDoc] = {
    "PR-2026-0819-001": _create_default_pr()
}


class ApprovalActionPayload(BaseModel):
    pr_number: str
    action: str = "APPROVE"  # APPROVE | REJECT
    manager_name: str | None = "Warehouse Manager"
    notes: str | None = None


# --- Helper: Update DuckDB order status & optionally add stock ---

def _update_db_status(pr_number: str, action: str, pr: PurchaseRequisitionDoc | None = None) -> str:
    """Updates DuckDB orders table and optionally increments stock on APPROVE."""
    try:
        from database.db import get_db_connection
        conn = get_db_connection()
        try:
            if action == "APPROVE" and pr and pr.items:
                for item in pr.items:
                    conn.execute("""
                        UPDATE items
                        SET current_stock = GREATEST(current_stock + ?, min_threshold + 5)
                        WHERE item_id = ? OR name = ?;
                    """, [item.reorder_qty, item.item_id, item.name])

            conn.execute(f"UPDATE orders SET status = '{action}' WHERE pr_number = ?;", [pr_number])
        finally:
            conn.close()

        if action == "APPROVE":
            return "✅ <strong>Stok Fisik Inventaris DuckDB Berhasil Ditambahkan Otomatis!</strong>"
        return "🔒 <strong>Stok Fisik Inventaris Tetap (Tidak Ada Penambahan).</strong>"
    except Exception as e:
        return f"⚠️ Catatan database: {e!s}"


def _regenerate_pdf(pr: PurchaseRequisitionDoc):
    """Regenerates Typst PDF with the current PR status."""
    try:
        from docgen.pdf_generator import pdf_generator
        clean_filename = f"{pr.pr_number.replace('-', '_')}.pdf"
        pdf_generator.generate_purchase_requisition_pdf(pr, output_filename=clean_filename)
        pr.pdf_path = f"/storage/documents/{clean_filename}"
    except Exception:
        pass


def _ensure_pr_in_store(pr_number: str) -> PurchaseRequisitionDoc | None:
    """Gets a PR from store, creating a default fallback if it starts with 'PR-'."""
    pr = PR_STORE.get(pr_number)
    if not pr and pr_number.startswith("PR-"):
        PR_STORE[pr_number] = _create_default_pr(pr_number)
        pr = PR_STORE[pr_number]
    return pr


# --- API Endpoints ---

@router.get("/list", response_model=list[PurchaseRequisitionDoc])
async def get_all_requisitions(current_user: TokenData = Depends(get_current_user)):
    """Returns list of active purchase requisitions filtered by tenant."""
    if current_user.role == "ADMIN":
        return list(PR_STORE.values())
    
    return [pr for pr in PR_STORE.values() if pr.tenant_id == current_user.tenant_id or pr.tenant_id == "ALL"]


@router.get("/quick-action", response_class=HTMLResponse)
async def quick_approval_action(
    pr_number: str,
    action: str = "APPROVE",
    manager_name: str = "Manager (Email / Telegram)",
    notes: str | None = None
):
    """
    Direct one-click approval/rejection endpoint used by Email & Telegram interactive action buttons.
    Returns a responsive HTML confirmation landing page.
    """
    clean_action = action.strip().upper()
    pr = _ensure_pr_in_store(pr_number)

    items_updated_summary = []

    if clean_action == "APPROVE":
        if pr:
            pr.status = "APPROVED"
            items_updated_summary = [
                f"<li><strong>{item.name}</strong>: +{item.reorder_qty} {item.unit} (Stok Fisik Bertambah)</li>"
                for item in pr.items
            ]
        stock_delta_info = _update_db_status(pr_number, "APPROVED", pr)
        status_badge = '<span style="background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; padding: 6px 14px; border-radius: 9999px; font-weight: 700; font-size: 0.9rem;">✅ DISETUJUI (APPROVED)</span>'
        title_color = "#22c55e"
        heading_text = "Pengadaan Barang Telah Disetujui"
        desc_text = f"Dokumen <strong>{pr_number}</strong> telah resmi disetujui. Status pesanan diperbarui ke APPROVED dan pengadaan dilanjutkan ke vendor terkait."
    else:
        if pr:
            pr.status = "REJECTED"
        stock_delta_info = _update_db_status(pr_number, "REJECTED", pr)
        status_badge = '<span style="background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; padding: 6px 14px; border-radius: 9999px; font-weight: 700; font-size: 0.9rem;">❌ DITOLAK (REJECTED)</span>'
        title_color = "#ef4444"
        heading_text = "Pengadaan Barang Ditolak"
        desc_text = f"Dokumen <strong>{pr_number}</strong> telah ditolak. Anggaran pengadaan dibatalkan dan stok fisik gudang tidak berubah."

    if pr:
        _regenerate_pdf(pr)

    pdf_download_url = f"/api/documents/pr/{pr_number}/download"
    items_html = "".join(items_updated_summary) if items_updated_summary else "<li>Daftar barang tercatat di tabel orders DuckDB.</li>"

    html_content = f"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Status Persetujuan | {pr_number}</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: 'Inter', sans-serif; background: radial-gradient(circle at top, #1e293b, #0f172a); color: #f8fafc; min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; padding: 24px; }}
            .container {{ background: rgba(30, 41, 59, 0.85); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 20px; max-width: 580px; width: 100%; padding: 40px 32px; text-align: center; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6); }}
            h1 {{ color: {title_color}; font-size: 1.6rem; font-weight: 800; margin: 16px 0 8px 0; }}
            p {{ color: #94a3b8; font-size: 0.95rem; line-height: 1.6; margin: 0 0 16px 0; }}
            .meta-box {{ background: rgba(15, 23, 42, 0.6); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 14px 18px; margin: 20px 0; font-size: 0.9rem; color: #cbd5e1; display: flex; justify-content: space-between; align-items: center; }}
            .meta-val {{ font-weight: 700; color: #f1f5f9; }}
            .btn-group {{ display: flex; gap: 12px; margin-top: 24px; flex-wrap: wrap; }}
            .btn {{ flex: 1; min-width: 140px; padding: 12px 20px; border-radius: 10px; font-weight: 600; font-size: 0.95rem; text-decoration: none; transition: all 0.2s ease; display: inline-flex; align-items: center; justify-content: center; gap: 8px; }}
            .btn-primary {{ background: #2563eb; color: white; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3); }}
            .btn-primary:hover {{ background: #1d4ed8; transform: translateY(-1px); }}
            .btn-secondary {{ background: rgba(255, 255, 255, 0.08); color: #cbd5e1; border: 1px solid rgba(255, 255, 255, 0.1); }}
            .btn-secondary:hover {{ background: rgba(255, 255, 255, 0.15); color: white; }}
            .stock-alert {{ padding: 12px; border-radius: 8px; font-size: 0.9rem; background: rgba(30, 41, 59, 0.7); border-left: 4px solid {title_color}; text-align: left; margin-top: 16px; color: #e2e8f0; }}
            .items-box {{ background: #0f172a; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: left; }}
            .items-box ul {{ margin: 0; padding-left: 20px; line-height: 1.6; color: #cbd5e1; font-size: 0.95rem; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div>{status_badge}</div>
            <h1>{heading_text}</h1>
            <p>{desc_text}</p>
            <div class="meta-box"><span>No. Purchase Requisition</span><span class="meta-val">{pr_number}</span></div>
            <div class="meta-box"><span>Diperbarui Oleh</span><span class="meta-val">{manager_name}</span></div>
            <div class="meta-box"><span>Waktu Keputusan</span><span class="meta-val">{datetime.now().strftime('%d %b %Y, %H:%M WIB')}</span></div>
            {'<div class="items-box"><div style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">Rincian Barang Terkait:</div><ul>' + items_html + '</ul></div>' if clean_action == 'APPROVE' else ''}
            <div class="stock-alert">{stock_delta_info}</div>
            <div class="btn-group">
                <a href="{pdf_download_url}" class="btn btn-secondary" target="_blank">📄 Unduh Dokumen PDF</a>
                <a href="/" class="btn btn-primary">🌐 Buka Web Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/{pr_number}", response_model=PurchaseRequisitionDoc)
async def get_requisition_by_number(pr_number: str):
    """Returns a single purchase requisition by PR Number."""
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

    action = payload.action.upper()
    pr.status = "APPROVED" if action == "APPROVE" else "REJECTED"
    _update_db_status(pr.pr_number, pr.status, pr if action == "APPROVE" else None)
    _regenerate_pdf(pr)

    message = (
        f"Dokumen {payload.pr_number} telah disetujui oleh {payload.manager_name}. Status diteruskan ke Purchasing."
        if action == "APPROVE" else
        f"Dokumen {payload.pr_number} telah ditolak oleh {payload.manager_name}."
    )

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
    Resets PR_STORE to clean initial PENDING state, resets DuckDB stock to initial state,
    and regenerates the clean initial PDF.
    """
    try:
        from database.seed_data import init_db, seed_data
        conn = init_db()
        seed_data(conn)
        conn.close()
    except Exception as e:
        print(f"[RESET] Warning re-seeding DuckDB: {e}")

    PR_STORE["PR-2026-0819-001"] = _create_default_pr()
    _regenerate_pdf(PR_STORE["PR-2026-0819-001"])

    return {"status": "reset", "message": "PR-2026-0819-001 reset to PENDING status with all 5 DuckDB critical items."}


@router.post("/telegram-webhook")
async def telegram_webhook_handler(request: Request):
    """
    Handles incoming interactive callbacks from Telegram Bot inline buttons.
    Automatically increments DuckDB inventory stock on APPROVE and keeps stock unchanged on REJECT.
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
            action, pr_num = parts[0].upper(), parts[1]
            pr = _ensure_pr_in_store(pr_num)

            if pr:
                pr.status = "APPROVED" if action == "APPROVE" else "REJECTED"

            _update_db_status(pr_num, "APPROVED" if action == "APPROVE" else "REJECTED", pr if action == "APPROVE" else None)

            if pr:
                _regenerate_pdf(pr)

            return {"status": "processed", "pr_number": pr_num, "action": action}

    return {"status": "ok"}
