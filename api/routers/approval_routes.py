from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
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
    """Updates DuckDB orders table and optionally increments stock on APPROVE, ensuring idempotency."""
    try:
        import uuid
        from database.db import get_db_connection
        is_approve = str(action).upper() in ["APPROVE", "APPROVED"]
        db_status = "APPROVED" if is_approve else "REJECTED"
        conn = get_db_connection()
        try:
            existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
            if "orders" not in existing_tables:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id VARCHAR PRIMARY KEY,
                        pr_number VARCHAR,
                        item_id VARCHAR,
                        vendor_id VARCHAR,
                        quantity INTEGER,
                        unit_price DOUBLE,
                        total_price DOUBLE,
                        status VARCHAR,
                        tenant_id VARCHAR
                    );
                """)

            # Check if order already exists and its current status
            existing_order = conn.execute("SELECT status FROM orders WHERE pr_number = ? LIMIT 1;", [pr_number]).fetchone()
            already_approved = existing_order and existing_order[0] == "APPROVED"
            
            # Only increment stock if we are approving AND it wasn't already approved
            if is_approve and not already_approved:
                from database.schema_adapters import TenantSchemaAdapter
                if pr and pr.items:
                    effective_tenant = getattr(pr, "tenant_id", "ALL") or "ALL"
                    for item in pr.items:
                        TenantSchemaAdapter.update_item_stock(
                            item_id=item.item_id,
                            qty_to_add=item.reorder_qty,
                            item_name=item.name,
                            tenant_id=effective_tenant
                        )
                else:
                    ord_rows = conn.execute("SELECT item_id, quantity, tenant_id FROM orders WHERE pr_number = ?;", [pr_number]).fetchall()
                    for it_id, it_qty, it_tenant in ord_rows:
                        TenantSchemaAdapter.update_item_stock(
                            item_id=it_id,
                            qty_to_add=it_qty,
                            tenant_id=it_tenant or "ALL"
                        )

            if existing_order:
                conn.execute("UPDATE orders SET status = ? WHERE pr_number = ?;", [db_status, pr_number])
            elif pr and pr.items:
                insert_orders_params = [
                    (f"ORD-{uuid.uuid4().hex[:8].upper()}", pr_number, it.item_id, it.vendor_id, it.reorder_qty, it.unit_price, it.total_price, db_status, pr.tenant_id or "ALL")
                    for it in pr.items
                ]
                conn.executemany("""
                    INSERT INTO orders (order_id, pr_number, item_id, vendor_id, quantity, unit_price, total_price, status, tenant_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, insert_orders_params)

            # Synchronize Purchase Orders (PO) in purchase_orders table: status becomes ORDERED
            if "purchase_orders" in existing_tables:
                if is_approve:
                    conn.execute("UPDATE purchase_orders SET status = 'ORDERED' WHERE pr_number = ?;", [pr_number])
                    if pr and pr.items:
                        item_ids = [it.item_id for it in pr.items]
                        placeholders = ", ".join(["?"] * len(item_ids))
                        conn.execute(f"UPDATE purchase_orders SET status = 'ORDERED' WHERE status = 'PENDING_APPROVAL' AND item_id IN ({placeholders});", item_ids)
                        
                        # Pre-compile official Typst PDF for ordered POs
                        try:
                            from docgen.compiler import generate_po_pdf
                            po_matches = conn.execute(f"SELECT po_id FROM purchase_orders WHERE pr_number = ? OR (status = 'ORDERED' AND item_id IN ({placeholders}));", [pr_number] + item_ids).fetchall()
                            for (p_id,) in po_matches:
                                generate_po_pdf(p_id)
                        except Exception as po_err:
                            print(f"PO DocGen error: {po_err}")
                else:
                    conn.execute("UPDATE purchase_orders SET status = 'REJECTED' WHERE pr_number = ?;", [pr_number])

            if "purchase_requests" in existing_tables:
                conn.execute("UPDATE purchase_requests SET status = ? WHERE pr_number = ?;", [db_status, pr_number])
        finally:
            conn.commit()
            conn.close()

        if is_approve:
            return "<strong>Stok Fisik Inventaris DuckDB Berhasil Ditambahkan Otomatis!</strong>"
        return "<strong>Stok Fisik Inventaris Tetap (Tidak Ada Penambahan).</strong>"
    except Exception as e:
        return f"Catatan database: {e!s}"


def _regenerate_pdf(pr: PurchaseRequisitionDoc):
    """Regenerates Typst PDF with the current PR status and removes stale pending files."""
    try:
        from core.config import settings
        from docgen.compiler import generate_pr_pdf
        clean_pr_num = pr.pr_number.replace("/", "_").replace("\\", "_")
        clean_filename = f"{pr.pr_number.replace('-', '_')}.pdf"
        
        # 1. Generate to structured target dir (e.g. storage/approved/ or storage/rejected/)
        payload = pr.model_dump()
        target_file = generate_pr_pdf(payload)
        pr.pdf_path = target_file
        
        # 2. Also generate into storage/documents/ and ensure both naming variants exist in target dir
        settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        generate_pr_pdf(payload, output_path=settings.DOCUMENTS_DIR / clean_filename)
        generate_pr_pdf(payload, output_path=settings.DOCUMENTS_DIR / f"{clean_pr_num}.pdf")
        
        status_upper = pr.status.upper()
        if "APPROV" in status_upper:
            settings.APPROVED_DIR.mkdir(parents=True, exist_ok=True)
            generate_pr_pdf(payload, output_path=settings.APPROVED_DIR / f"{clean_pr_num}.pdf")
            generate_pr_pdf(payload, output_path=settings.APPROVED_DIR / clean_filename)
        elif "REJECT" in status_upper:
            settings.REJECTED_DIR.mkdir(parents=True, exist_ok=True)
            generate_pr_pdf(payload, output_path=settings.REJECTED_DIR / f"{clean_pr_num}.pdf")
            generate_pr_pdf(payload, output_path=settings.REJECTED_DIR / clean_filename)
        
        # 3. Clean up old pending files so it won't be served by cache/download
        for pfile in [settings.PENDING_DIR / f"{clean_pr_num}.pdf", settings.PENDING_DIR / clean_filename]:
            if pfile.exists():
                try:
                    pfile.unlink()
                except Exception as e:
                    print(f"[REGENERATE PDF WARN] Failed to delete stale pending PDF {pfile}: {e}")
    except Exception as e:
        print(f"[REGENERATE PDF ERROR] {e}")


def _ensure_pr_in_store(pr_number: str) -> PurchaseRequisitionDoc | None:
    """Gets a PR from store, reconstructing from DuckDB if missing, or creating fallback."""
    pr = PR_STORE.get(pr_number)
    if pr:
        return pr

    # Try reconstructing from DuckDB orders
    try:
        from database.db import get_db_connection
        conn = get_db_connection()
        existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
        if "vendors" in existing_tables:
            vendor_join = "LEFT JOIN vendors v ON o.vendor_id = v.vendor_id AND o.item_id = v.item_id"
            vendor_col = "v.name as vendor_name"
        elif "suppliers" in existing_tables:
            vendor_join = "LEFT JOIN suppliers v ON o.vendor_id = v.supplier_id"
            vendor_col = "v.supplier_name as vendor_name"
        else:
            vendor_join = ""
            vendor_col = "'Vendor Terdaftar' as vendor_name"

        order_rows = conn.execute(f"""
            SELECT o.pr_number, o.item_id, o.vendor_id, o.quantity, o.unit_price, o.total_price, o.status, o.tenant_id,
                   i.name as item_name, i.unit, {vendor_col}
            FROM orders o
            LEFT JOIN items i ON o.item_id = i.item_id
            {vendor_join}
            WHERE o.pr_number = ?;
        """, [pr_number]).fetchall()
        conn.close()

        if order_rows:
            items = []
            total_budget = 0.0
            db_status = order_rows[0][6] or "PENDING"
            tenant_id = order_rows[0][7] or "ALL"

            for row in order_rows:
                qty = row[3]
                uprice = row[4]
                tprice = row[5] or (qty * uprice)
                total_budget += tprice
                items.append(PurchaseItemRequest(
                    item_id=row[1],
                    name=row[8] or f"Item {row[1]}",
                    reorder_qty=qty,
                    unit=row[9] or "pcs",
                    vendor_id=row[2] or "VND-001",
                    vendor_name=row[10] or "Vendor Terdaftar",
                    unit_price=uprice,
                    total_price=tprice,
                    reason="Reconstructed from DuckDB orders"
                ))

            clean_filename = f"{pr_number.replace('-', '_')}.pdf"
            pr_doc = PurchaseRequisitionDoc(
                pr_number=pr_number,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                items=items,
                total_budget=total_budget,
                auditor_status="PASSED",
                auditor_notes="Compliance check: Sesuai alokasi pengadaan inventaris.",
                pdf_path=f"/storage/documents/{clean_filename}",
                status=db_status,
                tenant_id=tenant_id
            )
            PR_STORE[pr_number] = pr_doc
            return pr_doc
    except Exception as e:
        print(f"[_ensure_pr_in_store] Error loading from DB: {e}")

    if pr_number == "PR-2026-0819-001":
        PR_STORE[pr_number] = _create_default_pr(pr_number)
        return PR_STORE[pr_number]
    return None


# --- API Endpoints ---

@router.get("/list", response_model=list[PurchaseRequisitionDoc])
async def get_all_requisitions(response: Response, current_user: TokenData = Depends(get_current_user)):
    """Returns list of active purchase requisitions filtered by tenant."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    # Sync PRs from DuckDB orders
    try:
        from database.db import get_db_connection
        conn = get_db_connection(read_only=True)
        existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
        pr_rows = []
        if "orders" in existing_tables:
            pr_rows = conn.execute("SELECT DISTINCT pr_number, status FROM orders;").fetchall()
        elif "purchase_requests" in existing_tables:
            pr_rows = conn.execute("SELECT DISTINCT pr_number, status FROM purchase_requests;").fetchall()
        conn.close()
        for pr_num, db_status in pr_rows:
            if pr_num:
                pr = _ensure_pr_in_store(pr_num)
                if pr and db_status and pr.status != db_status:
                    pr.status = db_status
    except Exception as e:
        print(f"[get_all_requisitions] Error syncing from DB: {e}")

    if current_user.role == "ADMIN":
        return list(PR_STORE.values())
    
    return [pr for pr in PR_STORE.values() if pr.tenant_id == current_user.tenant_id or pr.tenant_id == "ALL"]


@router.get("/quick-action", response_class=HTMLResponse)
async def quick_approval_action(
    pr_number: str,
    action: str = "APPROVE",
    manager_name: str = "Manager",
    notes: str | None = None
):
    """
    Direct one-click approval/rejection endpoint used by Email interactive action buttons.
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
        status_badge = '<span style="background: #DCFCE7; color: #166534; border: 1px solid #86EFAC; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.05em; text-transform: uppercase;">STATUS: DISETUJUI (APPROVED)</span>'
        title_color = "#0F172A"
        heading_text = "Otorisasi Pengadaan Berhasil Dicatatkan"
        desc_text = f"Dokumen Purchase Requisition <strong>{pr_number}</strong> telah resmi disetujui. Sistem telah memproses pengesahan dan Purchase Order (PO) resmi kini siap diteruskan ke rekanan vendor terpilih untuk pengiriman material."
    else:
        if pr:
            pr.status = "REJECTED"
        stock_delta_info = _update_db_status(pr_number, "REJECTED", pr)
        status_badge = '<span style="background: #FEE2E2; color: #991B1B; border: 1px solid #FCA5A5; padding: 6px 14px; border-radius: 6px; font-weight: 700; font-size: 11.5px; letter-spacing: 0.05em; text-transform: uppercase;">STATUS: DITOLAK (REJECTED)</span>'
        title_color = "#0F172A"
        heading_text = "Pengadaan Barang Ditolak"
        desc_text = f"Dokumen Purchase Requisition <strong>{pr_number}</strong> telah ditolak. Alokasi anggaran dibatalkan dan kuantitas stok gudang tetap dipertahankan."

    if pr:
        _regenerate_pdf(pr)

    pdf_download_url = f"/api/documents/pr/{pr_number}/download"
    items_html = "".join(items_updated_summary) if items_updated_summary else "<li>Daftar barang tercatat dalam basis data logistik.</li>"

    html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Konfirmasi Otorisasi | {pr_number}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: #F1F5F9;
            color: #0F172A;
            margin: 0;
            padding: 32px 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }}
        .receipt-card {{
            background: #FFFFFF;
            border: 1px solid #CBD5E1;
            border-radius: 8px;
            max-width: 620px;
            width: 100%;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
        }}
        .receipt-header {{
            background: #0F172A;
            color: #FFFFFF;
            padding: 22px 28px;
            border-bottom: 3px solid #2563EB;
        }}
        .corp-name {{
            font-size: 14px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #F8FAFC;
            margin: 0;
        }}
        .corp-dept {{
            font-size: 12px;
            color: #94A3B8;
            margin: 4px 0 0 0;
        }}
        .receipt-body {{
            padding: 32px 28px;
        }}
        .status-container {{
            margin-bottom: 20px;
        }}
        h1 {{
            font-size: 20px;
            font-weight: 700;
            color: {title_color};
            margin: 0 0 10px 0;
            line-height: 1.3;
        }}
        p.lead-desc {{
            color: #475569;
            font-size: 13.5px;
            line-height: 1.6;
            margin: 0 0 20px 0;
        }}
        .meta-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 18px 0;
            font-size: 13px;
        }}
        .meta-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid #E2E8F0;
        }}
        .meta-label {{
            color: #64748B;
            width: 40%;
            font-weight: 500;
        }}
        .meta-val {{
            color: #0F172A;
            font-weight: 600;
            text-align: right;
            font-family: 'Consolas', monospace;
        }}
        .items-box {{
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 16px;
            margin: 20px 0;
            font-size: 13px;
        }}
        .items-box-title {{
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #475569;
            margin-bottom: 10px;
        }}
        .items-box ul {{
            margin: 0;
            padding-left: 20px;
            line-height: 1.6;
            color: #334155;
        }}
        .btn-row {{
            display: flex;
            gap: 12px;
            margin-top: 28px;
            flex-wrap: wrap;
        }}
        .btn {{
            flex: 1;
            min-width: 140px;
            padding: 12px 18px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            text-decoration: none;
            text-align: center;
            transition: background 0.15s ease;
        }}
        .btn-primary {{
            background: #0F172A;
            color: #FFFFFF !important;
            border: 1px solid #0F172A;
        }}
        .btn-primary:hover {{
            background: #1E293B;
        }}
        .btn-secondary {{
            background: #FFFFFF;
            color: #334155 !important;
            border: 1px solid #CBD5E1;
        }}
        .btn-secondary:hover {{
            background: #F8FAFC;
        }}
        .receipt-footer {{
            background: #F8FAFC;
            border-top: 1px solid #E2E8F0;
            padding: 16px 28px;
            font-size: 11.5px;
            color: #64748B;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="receipt-card">
        <div class="receipt-header">
            <h2 class="corp-name">PT Bali Towerindo Sentra Tbk</h2>
            <p class="corp-dept">Enterprise Operations Command Center &mdash; Procurement System</p>
        </div>
        <div class="receipt-body">
            <div class="status-container">
                {status_badge}
            </div>
            <h1>{heading_text}</h1>
            <p class="lead-desc">{desc_text}</p>

            <table class="meta-table">
                <tr>
                    <td class="meta-label">Nomor Purchase Requisition</td>
                    <td class="meta-val">{pr_number}</td>
                </tr>
                <tr>
                    <td class="meta-label">Otorisator / Penyetuju</td>
                    <td class="meta-val">{manager_name}</td>
                </tr>
                <tr>
                    <td class="meta-label">Waktu Pengesahan</td>
                    <td class="meta-val">{datetime.now().strftime('%d %b %Y, %H:%M WIB')}</td>
                </tr>
                <tr>
                    <td class="meta-label">Tindak Lanjut Sistem</td>
                    <td class="meta-val" style="color: #15803D;">{'Penerbitan PO Resmi' if clean_action == 'APPROVE' else 'Pengadaan Dibatalkan'}</td>
                </tr>
            </table>

            {'<div class="items-box"><div class="items-box-title">Alokasi Material yang Divalidasi:</div><ul>' + items_html + '</ul></div>' if clean_action == 'APPROVE' else ''}

            <div class="btn-row">
                <a href="{pdf_download_url}" class="btn btn-secondary" target="_blank">Unduh Dokumen PDF Resmi</a>
                <a href="/" class="btn btn-primary">Buka Web Dashboard</a>
            </div>
        </div>
        <div class="receipt-footer">
            Dokumen resmi ini disahkan secara elektronik melalui sistem terintegrasi DuckDB Enterprise.
        </div>
    </div>
</body>
</html>"""
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
    pr = _ensure_pr_in_store(payload.pr_number)
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
        conn.execute("DELETE FROM orders;")
        conn.execute("DELETE FROM vendors;")
        conn.execute("DELETE FROM items;")
        seed_data(conn)
        conn.close()
    except Exception as e:
        print(f"[RESET] Warning re-seeding DuckDB: {e}")

    try:
        from database.db import get_db_connection
        b_conn = get_db_connection(read_only=False)
        try:
            b_conn.execute("DELETE FROM orders WHERE pr_number = 'PR-2026-0819-001';")
            b_conn.commit()
        finally:
            b_conn.close()
    except Exception as e:
        print(f"[RESET] Warning cleaning balitower orders: {e}")

    PR_STORE["PR-2026-0819-001"] = _create_default_pr()
    _regenerate_pdf(PR_STORE["PR-2026-0819-001"])

    return {"status": "reset", "message": "PR-2026-0819-001 reset to PENDING status with all 5 DuckDB critical items."}


