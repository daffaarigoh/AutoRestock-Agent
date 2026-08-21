from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
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


@router.get("/quick-action", response_class=HTMLResponse)
async def quick_approval_action(
    pr_number: str,
    action: str = "APPROVE",
    manager_name: str = "Manager (Email / Telegram)",
    notes: Optional[str] = None
):
    """
    Direct one-click approval/rejection endpoint used by Email & Telegram interactive action buttons.
    Returns a responsive, premium HTML confirmation landing page.
    """
    clean_action = action.strip().upper()
    pr = PR_STORE.get(pr_number)

    # If PR not directly in PR_STORE, try fallback instantiation
    if not pr:
        if pr_number == "PR-2026-0819-001" or pr_number.startswith("PR-"):
            PR_STORE[pr_number] = PurchaseRequisitionDoc(
                pr_number=pr_number,
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
                        reason="Stok fisik 12 pcs di bawah safety threshold (50 pcs)."
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
                        reason="Stok fisik 8 pcs di bawah safety threshold (40 pcs)."
                    )
                ],
                total_budget=6994000.0,
                auditor_status="PASSED",
                auditor_notes="Compliance check passed.",
                pdf_path=f"/storage/documents/{pr_number.replace('-', '_')}.pdf",
                status="PENDING"
            )
            pr = PR_STORE[pr_number]

    items_updated_summary = []
    stock_delta_info = ""

    if clean_action == "APPROVE":
        if pr:
            pr.status = "APPROVED"
        
        # 1. Update DuckDB items & orders
        try:
            from database.db import get_db_connection
            conn = get_db_connection()
            if pr and pr.items:
                for item in pr.items:
                    conn.execute("""
                        UPDATE items
                        SET current_stock = current_stock + ?
                        WHERE item_id = ? OR name = ?;
                    """, [item.reorder_qty, item.item_id, item.name])
                    items_updated_summary.append(f"<li><strong>{item.name}</strong>: +{item.reorder_qty} {item.unit} (Stok Fisik Bertambah)</li>")
            
            conn.execute("""
                UPDATE orders
                SET status = 'APPROVED'
                WHERE pr_number = ?;
            """, [pr_number])
            conn.close()
            stock_delta_info = "✅ <strong>Stok Fisik Inventaris DuckDB Berhasil Ditambahkan Otomatis!</strong>"
        except Exception as e:
            stock_delta_info = f"⚠️ Catatan database: {str(e)}"

        status_badge = '<span style="background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; padding: 6px 14px; border-radius: 9999px; font-weight: 700; font-size: 0.9rem;">✅ DISETUJUI (APPROVED)</span>'
        title_color = "#22c55e"
        heading_text = "Pengadaan Barang Telah Disetujui"
        desc_text = f"Dokumen <strong>{pr_number}</strong> telah resmi disetujui. Status pesanan diperbarui ke APPROVED dan pengadaan dilanjutkan ke vendor terkait."
    
    else: # REJECT
        if pr:
            pr.status = "REJECTED"
        
        # Update orders status to REJECTED, stock stays intact
        try:
            from database.db import get_db_connection
            conn = get_db_connection()
            conn.execute("""
                UPDATE orders
                SET status = 'REJECTED'
                WHERE pr_number = ?;
            """, [pr_number])
            conn.close()
            stock_delta_info = "🔒 <strong>Stok Fisik Inventaris Tetap (Tidak Ada Penambahan).</strong>"
        except Exception as e:
            stock_delta_info = f"⚠️ Catatan database: {str(e)}"

        status_badge = '<span style="background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; padding: 6px 14px; border-radius: 9999px; font-weight: 700; font-size: 0.9rem;">❌ DITOLAK (REJECTED)</span>'
        title_color = "#ef4444"
        heading_text = "Pengadaan Barang Ditolak"
        desc_text = f"Dokumen <strong>{pr_number}</strong> telah ditolak. Anggaran pengadaan dibatalkan dan stok fisik gudang tidak berubah."

    # Regenerate Typst PDF
    pdf_download_url = f"/api/documents/pr/{pr_number}/download"
    if pr:
        try:
            from docgen.pdf_generator import pdf_generator
            clean_filename = f"{pr.pr_number.replace('-', '_')}.pdf"
            pdf_generator.generate_purchase_requisition_pdf(pr, output_filename=clean_filename)
            pr.pdf_path = f"/storage/documents/{clean_filename}"
        except Exception:
            pass

    items_html_block = f"""
    <div style="background: #0f172a; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: left;">
        <div style="font-size: 0.85rem; color: #94a3b8; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">Rincian Barang Terkait:</div>
        <ul style="margin: 0; padding-left: 20px; line-height: 1.6; color: #cbd5e1; font-size: 0.95rem;">
            {''.join(items_updated_summary) if items_updated_summary else '<li>Daftar barang tercatat di tabel orders DuckDB.</li>'}
        </ul>
    </div>
    """

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
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                background: radial-gradient(circle at top, #1e293b, #0f172a);
                color: #f8fafc;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                padding: 24px;
            }}
            .container {{
                background: rgba(30, 41, 59, 0.85);
                backdrop-filter: blur(12px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                max-width: 580px;
                width: 100%;
                padding: 40px 32px;
                text-align: center;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
            }}
            .status-container {{
                margin-bottom: 24px;
            }}
            h1 {{
                color: {title_color};
                font-size: 1.6rem;
                font-weight: 800;
                margin: 16px 0 8px 0;
            }}
            p {{
                color: #94a3b8;
                font-size: 0.95rem;
                line-height: 1.6;
                margin: 0 0 16px 0;
            }}
            .meta-box {{
                background: rgba(15, 23, 42, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                padding: 14px 18px;
                margin: 20px 0;
                font-size: 0.9rem;
                color: #cbd5e1;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            .meta-val {{
                font-weight: 700;
                color: #f1f5f9;
            }}
            .btn-group {{
                display: flex;
                gap: 12px;
                margin-top: 24px;
                flex-wrap: wrap;
            }}
            .btn {{
                flex: 1;
                min-width: 140px;
                padding: 12px 20px;
                border-radius: 10px;
                font-weight: 600;
                font-size: 0.95rem;
                text-decoration: none;
                transition: all 0.2s ease;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }}
            .btn-primary {{
                background: #2563eb;
                color: white;
                box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
            }}
            .btn-primary:hover {{
                background: #1d4ed8;
                transform: translateY(-1px);
            }}
            .btn-secondary {{
                background: rgba(255, 255, 255, 0.08);
                color: #cbd5e1;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }}
            .btn-secondary:hover {{
                background: rgba(255, 255, 255, 0.15);
                color: white;
            }}
            .stock-alert {{
                padding: 12px;
                border-radius: 8px;
                font-size: 0.9rem;
                background: rgba(30, 41, 59, 0.7);
                border-left: 4px solid {title_color};
                text-align: left;
                margin-top: 16px;
                color: #e2e8f0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="status-container">
                {status_badge}
                <h1>{heading_text}</h1>
                <p>{desc_text}</p>
            </div>

            <div class="meta-box">
                <span>No. Purchase Requisition</span>
                <span class="meta-val">{pr_number}</span>
            </div>

            <div class="meta-box">
                <span>Diperbarui Oleh</span>
                <span class="meta-val">{manager_name}</span>
            </div>

            <div class="meta-box">
                <span>Waktu Keputusan</span>
                <span class="meta-val">{datetime.now().strftime('%d %b %Y, %H:%M WIB')}</span>
            </div>

            {items_html_block if clean_action == 'APPROVE' else ''}

            <div class="stock-alert">
                {stock_delta_info}
            </div>

            <div class="btn-group">
                <a href="{pdf_download_url}" class="btn btn-secondary" target="_blank">
                    📄 Unduh Dokumen PDF
                </a>
                <a href="/" class="btn btn-primary">
                    🌐 Buka Web Dashboard
                </a>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


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
            action, pr_num = parts[0], parts[1]
            pr = PR_STORE.get(pr_num)
            
            if action.lower() == "approve":
                if pr:
                    pr.status = "APPROVED"
                # Update DuckDB stock
                try:
                    from database.db import get_db_connection
                    conn = get_db_connection()
                    if pr and pr.items:
                        for item in pr.items:
                            conn.execute("""
                                UPDATE items
                                SET current_stock = current_stock + ?
                                WHERE item_id = ? OR name = ?;
                            """, [item.reorder_qty, item.item_id, item.name])
                    conn.execute("UPDATE orders SET status = 'APPROVED' WHERE pr_number = ?;", [pr_num])
                    conn.close()
                except Exception as e:
                    print(f"[TELEGRAM WEBHOOK] DB Error: {e}")
            else:
                if pr:
                    pr.status = "REJECTED"
                try:
                    from database.db import get_db_connection
                    conn = get_db_connection()
                    conn.execute("UPDATE orders SET status = 'REJECTED' WHERE pr_number = ?;", [pr_num])
                    conn.close()
                except Exception:
                    pass

            if pr:
                try:
                    from docgen.pdf_generator import pdf_generator
                    clean_filename = f"{pr_num.replace('-', '_')}.pdf"
                    pdf_generator.generate_purchase_requisition_pdf(pr, output_filename=clean_filename)
                except Exception:
                    pass

            return {"status": "processed", "pr_number": pr_num, "action": action}

    return {"status": "ok"}



