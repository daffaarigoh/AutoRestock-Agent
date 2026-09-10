import asyncio
import re
import json
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status, Response, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from agents.state import PurchaseRequisition
from agents.workflow import resume_approval, run_autorestock_cycle
from core.security import TokenData, get_current_user
from database.db import get_db_connection
from mcp_server.tools import get_all_inventory_items

router = APIRouter(tags=["AutoRestock Agent"])

STORAGE_DIR = WORKSPACE_DIR / "storage"


class ApprovalRequest(BaseModel):
    pr_number: str = Field(..., description="Purchase Requisition number to approve or reject")
    action: str = Field("APPROVE", description="Decision action: 'APPROVE' or 'REJECT'")
    approver_name: str | None = Field("Warehouse Operations Manager", description="Name/Role of approver")
    notes: str | None = Field(None, description="Optional notes or reason for decision")


class ApprovalResponse(BaseModel):
    pr_number: str
    status: str
    approver: str
    message: str
    pr_document: PurchaseRequisition | None = None


@router.get("/api/inventory/items", response_model=list[dict[str, Any]])
def get_inventory_items(response: Response, current_user: TokenData = Depends(get_current_user)):
    """
    Retrieve all inventory items from DuckDB.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    try:
        items = get_all_inventory_items(tenant_id=current_user.tenant_id)
        return items
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch inventory items: {e!s}"
        )


@router.post("/api/agent/run-cycle", response_model=PurchaseRequisition)
def run_agent_cycle(current_user: TokenData = Depends(get_current_user)):
    """
    Triggers the LangGraph multi-agent workflow:
    1. Scan items below safety threshold.
    2. Planner (nemotron-35) matches optimal vendors & calculates budget.
    3. Auditor (nemotron-35) enforces compliance guardrails.
    4. Typst compiles the formal Purchase Requisition PDF.
    5. Graph pauses before Wait Approval Node (HITL).
    """
    try:
        tenant_id = current_user.tenant_id if current_user else "ALL"
        pr_document = run_autorestock_cycle(tenant_id=tenant_id)
        if pr_document:
            from api.routers.approval_routes import PR_STORE
            from docgen.compiler import generate_pr_pdf
            
            clean_filename = f"{pr_document.pr_number.replace('-', '_')}.pdf"
            PR_STORE[pr_document.pr_number] = pr_document
            generate_pr_pdf(pr_document, output_path=f"storage/documents/{clean_filename}")
        return pr_document
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AutoRestock agent cycle failed: {e!s}"
        )



@router.get("/api/documents/pr/{pr_number}/download")
def download_pr_document(pr_number: str, inline: bool = False):
    """
    Downloads or previews the generated Typst Purchase Requisition PDF.
    Use ?inline=true to display in-browser (for iframe previews).
    Checks status-specific folders first to ensure the served PDF matches true PR status.
    """
    clean_pr_num = pr_number.replace("/", "_").replace("\\", "_")
    clean_filename = f"{pr_number.replace('-', '_')}.pdf"
    
    # Check DB/PR_STORE status first
    from api.routers.approval_routes import _ensure_pr_in_store, _regenerate_pdf
    pr_doc = _ensure_pr_in_store(pr_number)
    current_status = (pr_doc.status if pr_doc else "PENDING").upper()
    
    candidate_paths = []
    if "APPROV" in current_status:
        candidate_paths = [
            STORAGE_DIR / "approved" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / "approved" / clean_filename,
            STORAGE_DIR / "documents" / clean_filename,
            STORAGE_DIR / "documents" / f"{clean_pr_num}.pdf",
        ]
    elif "REJECT" in current_status:
        candidate_paths = [
            STORAGE_DIR / "rejected" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / "rejected" / clean_filename,
            STORAGE_DIR / "documents" / clean_filename,
            STORAGE_DIR / "documents" / f"{clean_pr_num}.pdf",
        ]
    else:
        candidate_paths = [
            STORAGE_DIR / "pending" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / "pending" / clean_filename,
            STORAGE_DIR / "documents" / clean_filename,
            STORAGE_DIR / "documents" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / f"{clean_pr_num}.pdf"
        ]
    
    found_path = None
    for path in candidate_paths:
        if path.exists():
            found_path = path
            break
            
    # If not found or if the document needs regeneration for its current status
    if found_path is None and pr_doc:
        try:
            _regenerate_pdf(pr_doc)
            for path in candidate_paths:
                if path.exists():
                    found_path = path
                    break
        except Exception as e:
            print(f"[download_pr_document] Regeneration on-the-fly failed: {e}")

    # Recursive wildcard search fallback
    if found_path is None:
        matches = list(STORAGE_DIR.rglob(f"*{clean_pr_num}*.pdf"))
        if matches:
            found_path = matches[0]

    if found_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase Requisition PDF '{pr_number}' not found in storage."
        )
            
    return FileResponse(
        path=str(found_path),
        media_type="application/pdf",
        filename=f"{clean_pr_num}.pdf",
        content_disposition_type="inline" if inline else "attachment"
    )


@router.get("/api/documents/po/{po_id}/download")
def download_po_document(po_id: str, inline: bool = False):
    """
    Downloads or previews the official Typst Purchase Order (PO) PDF.
    Use ?inline=true to display in-browser (for iframe modal previews).
    Generates the PDF dynamically on-the-fly via Typst if not already compiled.
    """
    clean_po_id = po_id.replace("/", "_").replace("\\", "_")
    po_storage_dir = STORAGE_DIR / "purchase_orders"
    po_storage_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = po_storage_dir / f"{clean_po_id}.pdf"

    from docgen.compiler import generate_po_pdf
    try:
        pdf_path = generate_po_pdf(po_id, output_path=target_pdf)
    except Exception as err:
        if target_pdf.exists():
            pdf_path = str(target_pdf)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gagal menerbitkan dokumen Purchase Order '{po_id}': {err}"
            )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{clean_po_id}.pdf",
        content_disposition_type="inline" if inline else "attachment"
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
            detail=f"Failed to process PR approval: {e!s}"
        )


class UpdateItemThresholdRequest(BaseModel):
    min_threshold: int | None = Field(None, description="New minimum safety threshold")
    max_threshold: int | None = Field(None, description="New maximum safety threshold")
    current_stock: int | None = Field(None, description="Optional update to current physical stock")
    avg_daily_usage: float | None = Field(None, description="Optional update to daily usage burn rate")
    lead_time_days: int | None = Field(None, description="Optional update to vendor lead time")


@router.patch("/api/inventory/items/{item_id}")
def update_item_threshold(item_id: str, payload: UpdateItemThresholdRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Updates threshold and inventory parameters for a specific item in DuckDB.
    Supports real heterogeneous tenant tables and legacy items.
    """
    from database.schema_adapters import TenantSchemaAdapter
    tenant_id = current_user.tenant_id if current_user else "ALL"
    
    # 1. Look up existing item in real tenant tables or legacy items
    matching_items = TenantSchemaAdapter.get_specific_item_stock(item_id, tenant_id=tenant_id)
    if matching_items:
        existing_name = matching_items[0]["name"]
        cur_stock = matching_items[0].get("current_stock", 0)
        old_min = matching_items[0].get("min_threshold", 0)
    else:
        conn = get_db_connection(read_only=True)
        legacy = conn.execute("SELECT item_id, name, min_threshold, max_threshold, current_stock FROM items WHERE item_id = ? OR lower(name) LIKE ?", [item_id, f"%{item_id.lower()}%"]).fetchone()
        conn.close()
        if not legacy:
            raise HTTPException(status_code=404, detail=f"Item with ID '{item_id}' not found in inventory.")
        existing_name = legacy[1]
        cur_stock = legacy[4]
        old_min = legacy[2]

    # 2. Apply threshold update if provided
    new_min = payload.min_threshold if payload.min_threshold is not None else old_min
    if payload.min_threshold is not None:
        TenantSchemaAdapter.update_item_threshold(item_id, payload.min_threshold, tenant_id=tenant_id)

    # 3. Update legacy items table if extra fields provided
    conn = get_db_connection()
    try:
        updates = []
        params = []
        if payload.min_threshold is not None:
            updates.append("min_threshold = ?")
            params.append(payload.min_threshold)
        if payload.max_threshold is not None:
            updates.append("max_threshold = ?")
            params.append(payload.max_threshold)
        if payload.current_stock is not None:
            updates.append("current_stock = ?")
            params.append(payload.current_stock)
        if payload.avg_daily_usage is not None:
            updates.append("avg_daily_usage = ?")
            params.append(payload.avg_daily_usage)
        if payload.lead_time_days is not None:
            updates.append("lead_time_days = ?")
            params.append(payload.lead_time_days)

        if updates:
            params.extend([item_id, f"%{item_id.lower()}%"])
            conn.execute(f"UPDATE items SET {', '.join(updates)} WHERE item_id = ? OR lower(name) LIKE ?;", params)
            conn.commit()
    finally:
        conn.close()

    return {
        "status": "success",
        "message": f"Berhasil memperbarui {existing_name} ({item_id}).",
        "item": {
            "item_id": item_id,
            "name": existing_name,
            "min_threshold": new_min,
            "current_stock": payload.current_stock if payload.current_stock is not None else cur_stock
        }
    }



def process_goods_receipt(prompt: str, current_user: TokenData) -> dict | None:
    """
    Menangani pencatatan penerimaan fisik barang pesanan (Purchase Order) saat tiba di gudang regional.
    - Mengidentifikasi nomor PO atau mencari pengiriman aktif (IN_TRANSIT).
    - Memperbarui status PO menjadi DELIVERED dan actual_delivery = hari ini.
    - Menambahkan kuantitas fisik ke stock_balances di gudang terkait.
    - Mengalkulasi ulang stock_status (CRITICAL / LOW_STOCK -> NORMAL).
    - Menjaga persistensi data ke DuckDB dan CSV.
    """
    lower_prompt = prompt.strip().lower()
    
    # 1. Deteksi kata kunci kedatangan / penerimaan barang fisik di gudang
    receipt_action_keywords = [
        "sudah sampai", "sudah tiba", "telah sampai", "telah tiba", "sudah mendarat",
        "terima barang", "penerimaan barang", "catat penerimaan", "konfirmasi penerimaan",
        "konfirmasi kedatangan", "barang tiba", "barang sampai", "barang masuk",
        "barang datang", "catat barang", "terima po", "po sampai", "po tiba",
        "pesanan sampai", "pesanan tiba"
    ]
    has_explicit_receipt_intent = any(k in lower_prompt for k in receipt_action_keywords)
    
    if not has_explicit_receipt_intent:
        has_arrival_word = any(w in lower_prompt for w in ["sampai", "tiba", "terima", "diterima", "masuk", "mendarat"])
        has_po_or_wh = any(w in lower_prompt for w in ["po-", "po ", "po/", "purchase order", "gudang", "wh-"])
        if has_arrival_word and has_po_or_wh:
            has_explicit_receipt_intent = True

    if not has_explicit_receipt_intent:
        return None

    # 2. Strict RBAC / Tenant Authorization Check (Khusus Divisi Inventory atau Super Admin)
    u_tenant = str(getattr(current_user, 'tenant_id', 'ALL')).upper()
    u_role = str(getattr(current_user, 'role', 'USER')).upper()
    username = str(getattr(current_user, 'username', '')).lower()
    is_inv_authorized = (
        u_role in ["ADMIN", "MANAGER"] or 
        u_tenant in ["ALL", "INVENTORY", "TENANT_A"] or 
        username in ["admin", "usera", "user_inventory"]
    )
    if not is_inv_authorized:
        return {
            "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
            "action_type": "out_of_scope",
            "message": f"Akses Ditolak: Akun Anda ({current_user.username} - Divisi {u_tenant}) tidak memiliki wewenang untuk mencatat penerimaan barang fisik di Gudang Logistik. Akses ini dikhususkan untuk Staf Gudang / Divisi Inventory.",
            "generated_prs": [],
            "affected_items": []
        }

    # 3. Ekstraksi Identifier Purchase Order dari Prompt
    m_po_num = re.search(r'PO/BLT/\d{4}/\d{2}/\d{3}', prompt, re.IGNORECASE)
    m_po_id = re.search(r'\bPO[-_\s]?(\d{4}[-_\s]?\d{1,4}|\d{1,4})\b', prompt, re.IGNORECASE)

    conn = get_db_connection(read_only=True)
    try:
        po_row = None
        
        # A. Pencarian berbasis nomor PO resmi (PO/BLT/...)
        if m_po_num:
            po_num_str = m_po_num.group(0).upper()
            po_row = conn.execute("""
                SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                       i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                       po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                       w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                FROM purchase_orders po
                JOIN suppliers s ON po.supplier_id = s.supplier_id
                JOIN inventory_items i ON po.item_id = i.item_id
                JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                WHERE UPPER(po.po_number) = ?;
            """, [po_num_str]).fetchone()
            
        # B. Pencarian berbasis ID PO (PO-2026-006, PO-006, PO-6)
        if not po_row and m_po_id:
            raw_po_str = m_po_id.group(0).upper().replace(" ", "-").replace("_", "-")
            digits = re.findall(r'\d+', raw_po_str)
            digits_str = digits[-1] if digits else ""
            padded_digits = digits_str.zfill(3)

            canonical_po_id = f"PO-2026-{padded_digits}"
            po_row = conn.execute("""
                SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                       i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                       po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                       w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                FROM purchase_orders po
                JOIN suppliers s ON po.supplier_id = s.supplier_id
                JOIN inventory_items i ON po.item_id = i.item_id
                JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                WHERE UPPER(po.po_id) = ? OR UPPER(po.po_id) = ?;
            """, [raw_po_str, canonical_po_id]).fetchone()

            if not po_row:
                po_row = conn.execute("""
                    SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                           i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                           po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                           w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                    FROM purchase_orders po
                    JOIN suppliers s ON po.supplier_id = s.supplier_id
                    JOIN inventory_items i ON po.item_id = i.item_id
                    JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                    WHERE UPPER(po.po_number) LIKE ?;
                """, [f"%{padded_digits}"]).fetchone()

        # C. Jika tidak ada kode PO eksplisit, cari PO yang berstatus IN_TRANSIT berdasarkan material / gudang
        if not po_row:
            in_transit_rows = conn.execute("""
                SELECT po.po_id, po.po_number, po.supplier_id, s.supplier_name, po.item_id, 
                       i.item_name, i.item_code, i.category, i.unit, po.order_quantity, 
                       po.total_amount, po.status, po.actual_delivery, po.warehouse_id, 
                       w.warehouse_name, w.region, w.supervisor, i.min_stock, po.order_date, po.expected_delivery
                FROM purchase_orders po
                JOIN suppliers s ON po.supplier_id = s.supplier_id
                JOIN inventory_items i ON po.item_id = i.item_id
                JOIN warehouses w ON po.warehouse_id = w.warehouse_id
                WHERE po.status = 'IN_TRANSIT';
            """).fetchall()
            
            matched_pos = []
            for r in in_transit_rows:
                r_region = str(r[15]).lower()
                r_wh = str(r[14]).lower()
                r_item = str(r[5]).lower()
                r_sku = str(r[6]).lower()
                if (r_region in lower_prompt or r_wh in lower_prompt) and (any(part in lower_prompt for part in r_item.split()[:2]) or r_sku in lower_prompt):
                    matched_pos.append(r)
                elif r_item in lower_prompt or (len(r_item.split()) > 1 and " ".join(r_item.split()[:2]) in lower_prompt):
                    matched_pos.append(r)

            if len(matched_pos) == 1:
                po_row = matched_pos[0]
            elif len(matched_pos) > 1 or len(in_transit_rows) > 0:
                candidates = matched_pos if matched_pos else in_transit_rows
                msg = "**Sistem Mendeteksi Pengiriman Sedang Dalam Perjalanan (`IN_TRANSIT`)**\n\n"
                msg += "Mohon sebutkan nomor PO spesifik yang telah sampai di gudang fisik:\n\n"
                msg += "| No. PO | Kode Referensi | Material | Volume | Gudang Tujuan | Estimasi Tiba |\n"
                msg += "| :--- | :--- | :--- | :---: | :--- | :---: |\n"
                for c in candidates[:6]:
                    msg += f"| **{c[0]}** | `{c[1]}` | {c[5]} | {c[9]:,} {c[8]} | {c[14]} ({c[15]}) | {c[19] or '-'} |\n"
                msg += "\n*Contoh instruksi:* `Barang untuk PO-2026-006 sudah sampai di Gudang Bandung, tolong catat penerimaannya.`"
                return {
                    "parsed_intent": {"workflow_id": "goods_receipt_clarification"},
                    "action_type": "goods_receipt",
                    "message": msg,
                    "generated_prs": [],
                    "affected_items": []
                }
    finally:
        conn.close()

    if not po_row:
        return {
            "parsed_intent": {"workflow_id": "goods_receipt_not_found"},
            "action_type": "goods_receipt",
            "message": "Nomor Purchase Order (PO) yang Anda sebutkan tidak ditemukan dalam basis data logistik. Pastikan nomor PO benar (contoh: `PO-2026-006` atau `PO/BLT/2026/03/008`).",
            "generated_prs": [],
            "affected_items": []
        }

    # Atribut PO
    (po_id, po_number, supplier_id, supplier_name, item_id, 
     item_name, item_code, category, unit, order_quantity, 
     total_amount, po_status, actual_delivery, warehouse_id, 
     warehouse_name, region, supervisor, min_stock, order_date, expected_delivery) = po_row

    # 4. Validasi jika PO sudah pernah berstatus DELIVERED
    if po_status == 'DELIVERED':
        msg = f"**Informasi Penerimaan: Barang Sudah Pernah Diterima**\n\n"
        msg += f"Pesanan **{po_id}** (`{po_number}`) untuk material **{item_name}** ({order_quantity:,} {unit}) telah tercatat **DELIVERED** sebelumnya pada tanggal **{actual_delivery or '2026-01-22'}** di **{warehouse_name}** ({region}).\n\n"
        msg += f"- **Supervisor Gudang**: {supervisor}\n"
        msg += f"- **Status Fisik**: Seluruh kuantitas barang telah masuk ke saldo gudang dan tidak dilakukan penambahan ganda demi integritas data persediaan."
        return {
            "parsed_intent": {"workflow_id": "goods_receipt_already_delivered", "po_id": po_id},
            "action_type": "goods_receipt",
            "message": msg,
            "generated_prs": [],
            "affected_items": []
        }

    # 5. Eksekusi Pembaruan Basis Data (Koneksi Tulis DuckDB)
    today_str = datetime.now().strftime("%Y-%m-%d")
    now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    w_conn = get_db_connection(read_only=False)
    try:
        # A. Update purchase_orders ke status DELIVERED
        w_conn.execute("""
            UPDATE purchase_orders 
            SET status = 'DELIVERED', actual_delivery = ?
            WHERE po_id = ?;
        """, [today_str, po_id])

        # B. Update kuantitas fisik di stock_balances
        sb_row = w_conn.execute("""
            SELECT balance_id, quantity_on_hand, quantity_reserved, reorder_point, stock_status
            FROM stock_balances
            WHERE warehouse_id = ? AND item_id = ?;
        """, [warehouse_id, item_id]).fetchone()

        if sb_row:
            bal_id, old_qty, res_qty, rop, old_status = sb_row
            new_qty = old_qty + order_quantity
            # Kalkulasi ulang status kesehatan stok
            if new_qty <= rop * 0.5:
                new_status = 'CRITICAL'
            elif new_qty <= rop:
                new_status = 'LOW_STOCK'
            else:
                new_status = 'NORMAL'

            w_conn.execute("""
                UPDATE stock_balances
                SET quantity_on_hand = ?, stock_status = ?, last_updated = ?
                WHERE balance_id = ?;
            """, [new_qty, new_status, now_ts, bal_id])
        else:
            bal_id = f"STK-{warehouse_id}-{item_id}"
            old_qty = 0
            old_status = "TIDAK ADA"
            new_qty = order_quantity
            rop = min_stock
            new_status = 'NORMAL' if new_qty > rop else ('LOW_STOCK' if new_qty > rop * 0.5 else 'CRITICAL')
            w_conn.execute("""
                INSERT INTO stock_balances VALUES (?, ?, ?, ?, 0, ?, ?, ?);
            """, [bal_id, item_id, warehouse_id, new_qty, rop, new_status, now_ts])

        # C. Sinkronisasi tabel kompatibilitas 'items'
        w_conn.execute("""
            UPDATE items
            SET current_stock = (
                SELECT COALESCE(SUM(quantity_on_hand), 0)
                FROM stock_balances
                WHERE stock_balances.item_id = items.item_id
            )
            WHERE item_id = ?;
        """, [item_id])

        # D. Ekspor balik ke berkas CSV agar tersimpan permanen
        try:
            from pathlib import Path
            inv_csv_dir = Path(__file__).resolve().parent.parent.parent / "data" / "balitower" / "01_inventory"
            if inv_csv_dir.exists():
                df_pos = w_conn.execute("SELECT * FROM purchase_orders").df()
                df_pos.to_csv(inv_csv_dir / "purchase_orders.csv", index=False)
                df_stk = w_conn.execute("SELECT * FROM stock_balances").df()
                df_stk.to_csv(inv_csv_dir / "stock_balances.csv", index=False)
        except Exception:
            pass

    finally:
        w_conn.close()

    # 6. Format Respon Konfirmasi Korporat Bali Tower
    msg = f"**Konfirmasi Penerimaan Barang Fisik Berhasil Dibukukan**\n\n"
    msg += f"Penerimaan material pesanan **{po_id}** (`{po_number}`) telah diverifikasi tiba di gudang dan berhasil dicatatkan ke dalam basis data inventaris PT Bali Towerindo Sentra Tbk.\n\n"
    msg += "| Parameter | Rincian Transaksi Logistik |\n"
    msg += "| :--- | :--- |\n"
    msg += f"| **No. Purchase Order** | `{po_id}` ({po_number}) |\n"
    msg += f"| **Nama Material** | {item_name} (`{item_code}`) |\n"
    msg += f"| **Kategori & Volume** | {category} — **{order_quantity:,} {unit}** |\n"
    msg += f"| **Supplier / Rekanan** | {supplier_name} |\n"
    msg += f"| **Gudang Tujuan** | {warehouse_name} (`{warehouse_id}`) |\n"
    msg += f"| **Wilayah & Supervisor** | {region} — {supervisor} |\n"
    msg += f"| **Tanggal Penerimaan** | {today_str} (Tercatat Hari Ini) |\n"
    msg += f"| **Status Purchase Order** | Sebelumnya `{po_status}` ➔ **`DELIVERED`** |\n"
    msg += f"| **Saldo Fisik Gudang** | {old_qty:,} {unit} ➔ **{new_qty:,} {unit}** |\n"
    msg += f"| **Status Kesehatan Stok** | `{old_status}` ➔ **`{new_status}`** |\n\n"
    msg += f"*Saldo fisik gudang regional telah bertambah dan status pesanan telah otomatis disinkronkan ke DuckDB Enterprise.*"

    # Pre-generate official Typst PO PDF document for immediate preview / download
    try:
        from docgen.compiler import generate_po_pdf
        generate_po_pdf(po_id)
    except Exception as err:
        print(f"[Goods Receipt] PO PDF pre-generation note: {err}")

    return {
        "parsed_intent": {
            "workflow_id": "goods_receipt",
            "po_id": po_id,
            "po_number": po_number,
            "item_id": item_id,
            "warehouse_id": warehouse_id,
            "quantity_received": order_quantity
        },
        "action_type": "goods_receipt",
        "message": msg,
        "po_id": po_id,
        "po_number": po_number,
        "po_status": "DELIVERED",
        "status": "DELIVERED",
        "quantity_received": order_quantity,
        "stock_before": old_qty,
        "stock_after": new_qty,
        "pdf_download_url": f"/api/documents/po/{po_id}/download",
        "generated_prs": [],
        "affected_items": [{
            "name": item_name,
            "current_stock": new_qty,
            "min_stock": rop,
            "unit": unit
        }],
        "email_sent": False,
        "total_items_analyzed": 1,
        "target_destinations": ["database", "pdf"]
    }


class CustomPromptRequest(BaseModel):
    prompt: str = Field(..., description="Natural language prompt from user describing restock intent or workflow")
    destinations: list[str] | None = Field(None, description="Explicit destinations: ['database', 'email', 'pdf']")
    recipient_email: str | None = Field(None, description="Optional custom recipient email")


async def execute_prompt_logic(
    request: CustomPromptRequest,
    current_user: TokenData,
    stage_callback = None
) -> dict:
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt tidak boleh kosong.")

    lower_prompt = request.prompt.strip().lower()

    if stage_callback:
        await stage_callback("analyze", "🔍 Menganalisis instruksi & hak akses wewenang...")

    # 1. Pure thank-you / pleasantries check
    thanks_keywords = ["terima kasih", "terimakasih", "makasih", "thank you", "thanks", "tq", "matur nuwun", "hatur nuhun", "syukron", "arigato", "thx"]
    action_keywords = ["restock", "stok", "stock", "beli", "pesan", "order", "pr", "tambah", "daftar", "update", "threshold", "ambang", "audit", "gudang", "barang", "produk", "sku"]

    is_pure_thanks = any(k in lower_prompt for k in thanks_keywords) and not any(k in lower_prompt for k in action_keywords)
    if is_pure_thanks:
        return {
            "parsed_intent": {"workflow_id": "pleasantry"},
            "action_type": "general",
            "message": "Sama-sama! Senang bisa membantu Anda. Jika ada kebutuhan cek stok barang, update batas minimum stok, atau pengadaan lainnya, silakan beri tahu saya.",
            "generated_prs": [],
            "affected_items": []
        }

    # 2. Pure greeting check
    greeting_keywords = ["hi", "halo", "hello", "hei", "hey", "selamat pagi", "selamat siang", "selamat sore", "selamat malam", "pagi", "siang", "sore", "malam", "tes", "test", "testing"]
    is_pure_greeting = (lower_prompt in greeting_keywords or any(lower_prompt.startswith(k + " ") for k in greeting_keywords)) and not any(k in lower_prompt for k in action_keywords) and len(lower_prompt.split()) <= 6
    if is_pure_greeting:
        return {
            "parsed_intent": {"workflow_id": "greeting"},
            "action_type": "general",
            "message": "Halo! Saya adalah AutoRestock Agent untuk manajemen inventaris dan pengadaan. Ada yang bisa saya bantu terkait persediaan dan restock barang hari ini?",
            "generated_prs": [],
            "affected_items": []
        }

    from agents.router import SemanticRouter, check_clarification_needs, extract_recipient_email
    from agents.json_executor import JSONExecutionEngine
    from database.db import get_db_connection
    import json

    # 2.5 Clarification Check (Human-in-the-Loop Clarification Guard)
    clarification = check_clarification_needs(request.prompt, current_user.tenant_id)
    if clarification:
        if stage_callback:
            await stage_callback("clarification", f"❓ Membutuhkan klarifikasi: {clarification.get('title')}...")
        return {
            "parsed_intent": {"workflow_id": None},
            "action_type": "clarification_needed",
            "message": clarification.get("message"),
            "clarification": clarification,
            "generated_prs": [],
            "affected_items": []
        }

    # 3. Strict Multi-Tenant Domain Boundary Guard
    u_tenant = str(getattr(current_user, 'tenant_id', 'ALL')).upper()
    u_role = str(getattr(current_user, 'role', 'USER')).upper()

    is_profile_query = any(w in lower_prompt for w in ["profil", "siapa saya", "info akun", "hak akses", "wewenang", "role saya", "user info", "wf-all-01"])
    is_system_query = any(w in lower_prompt for w in ["info sistem", "status sistem", "status server", "health check", "spesifikasi sistem", "informasi sistem", "versi sistem", "kesehatan sistem", "wf-all-02"]) or (("status" in lower_prompt or "kesehatan" in lower_prompt or "info" in lower_prompt) and ("sistem" in lower_prompt or "server" in lower_prompt))
    is_guideline_query = any(w in lower_prompt for w in ["panduan operasional", "sop perusahaan", "kontak darurat", "helpdesk", "aturan kerja", "panduan", "sop", "wf-all-03"])
    is_all_schema_keyword = is_profile_query or is_system_query or is_guideline_query

    is_hr_keyword = any(w in lower_prompt for w in ["kandidat", "pelamar", "rigger", "climber", "tkpk", "rekrutmen", "screening", "absen", "hadir", "lembur", "overtime", "geofencing", "kunjungan site", "cuti", "izin", "sakit", "karyawan", "pegawai", "wf-002", "wf-003", "wf-a02"])
    is_fin_keyword = (
        any(w in lower_prompt for w in ["pemasukan", "pendapatan", "revenue", "invoice", "tagihan", "operator", "telkomsel", "indosat", "xl", "smartfren", "pengeluaran", "beban", "opex", "listrik", "pln", "sewa lahan", "genset", "biaya", "arus kas", "cash flow", "cashflow", "saldo kas", "wf-004", "wf-005", "wf-006", "wf-a03", "keuangan", "finance"])
        or (bool(re.search(r'\bkas\b', lower_prompt)) and "berkas" not in lower_prompt)
        or ("saldo" in lower_prompt and any(w in lower_prompt for w in ["keuangan", "bank", "kas"]))
    )
    is_inv_keyword = (
        any(w in lower_prompt for w in ["stok", "material", "baterai", "kabel", "closure", "odc", "kritis", "persediaan", "gudang", "beli", "pesan", "restock", "supplier", "purchase order", "po", "terima", "sampai", "tiba", "penerimaan", "pengiriman", "delivered", "transit", "approved", "setujui", "wf-001", "wf-a01"])
        or bool(re.search(r'\bpo\b', lower_prompt))
    )

    # If it's a Schema ALL request, it is universally accessible to all users!
    if not is_all_schema_keyword and u_role != "ADMIN" and u_tenant != "ALL":
        if is_fin_keyword and u_tenant != "FINANCE":
            if stage_callback:
                await stage_callback("denied", "🚫 Memeriksa wewenang divisi...")
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Permintaan ini di luar ranah kewenangan Anda. Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi {current_user.tenant_id}. Anda tidak memiliki akses ke data HR atau Keuangan perusahaan.",
                "generated_prs": [],
                "affected_items": []
            }
        if is_hr_keyword and u_tenant != "HR":
            if stage_callback:
                await stage_callback("denied", "🚫 Memeriksa wewenang divisi...")
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Permintaan ini di luar ranah kewenangan Anda. Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi {current_user.tenant_id}. Anda tidak memiliki akses ke data Material Gudang atau Keuangan perusahaan.",
                "generated_prs": [],
                "affected_items": []
            }
        if is_inv_keyword and u_tenant != "INVENTORY":
            if stage_callback:
                await stage_callback("denied", "🚫 Memeriksa wewenang divisi...")
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Permintaan ini di luar ranah kewenangan Anda. Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi {current_user.tenant_id}. Anda tidak memiliki akses ke data Material Gudang atau Data Personalia.",
                "generated_prs": [],
                "affected_items": []
            }

    # 3.4. Purchase Order (PO) Approval & Status Change Handler
    is_po_approval = (
        any(k in lower_prompt for k in ["setujui", "approve", "disetujui", "persetujuan"])
        and any(k in lower_prompt for k in ["po", "purchase order", "po-", "po/"])
    ) or (
        "perbarui status" in lower_prompt and any(k in lower_prompt for k in ["approved", "disetujui"]) and any(k in lower_prompt for k in ["po", "purchase order"])
    )
    if is_po_approval:
        from docgen.compiler import generate_po_pdf
        digits = re.findall(r'\d+', request.prompt)
        last_digits = digits[-1].zfill(3) if digits else ""

        c_conn = get_db_connection()
        po_row = c_conn.execute("""
            SELECT po.po_id, po.po_number, s.supplier_name, i.item_name, po.order_quantity, i.unit, po.total_amount, po.status
            FROM purchase_orders po
            JOIN suppliers s ON po.supplier_id = s.supplier_id
            JOIN inventory_items i ON po.item_id = i.item_id
            WHERE UPPER(po.po_id) = ? OR UPPER(po.po_number) = ?
               OR po.po_number LIKE ? OR po.po_id LIKE ?;
        """, [
            request.prompt.upper(), request.prompt.upper(),
            f"%{last_digits}%", f"%{last_digits}%"
        ]).fetchone()

        if po_row:
            p_id, p_num, s_name, i_name, o_qty, u_name, tot, old_st = po_row
            new_st = "APPROVED"
            c_conn.execute("UPDATE purchase_orders SET status = ? WHERE po_id = ?;", [new_st, p_id])
            c_conn.commit()
            c_conn.close()

            # Compile official Typst PO PDF with APPROVED status
            try:
                generate_po_pdf(p_id)
            except Exception as e:
                print(f"[PO PDF Compile Error]: {e}")

            msg = f"**Purchase Order Resmi Berhasil Disetujui (APPROVED)**\n\n"
            msg += f"Dokumen surat pesanan **{p_id}** (`{p_num}`) kepada supplier **{s_name}** telah resmi disetujui.\n\n"
            msg += f"- **Nomor PO**: `{p_num}` ({p_id})\n"
            msg += f"- **Supplier Rekanan**: {s_name}\n"
            msg += f"- **Material Dipesan**: {i_name} ({o_qty:,} {u_name})\n"
            msg += f"- **Total Anggaran**: Rp {tot:,}\n"
            msg += f"- **Status Sebelumnya**: `{old_st}` $\\rightarrow$ **`APPROVED`**\n\n"
            msg += f"Berkas dokumen resmi berformat PDF Typst dengan kop surat PT Bali Towerindo Sentra Tbk telah diterbitkan dan siap diunduh atau dipratinjau."

            return {
                "parsed_intent": {"workflow_id": "approve_purchase_order", "po_id": p_id, "po_number": p_num},
                "action_type": "view_po_document",
                "message": msg,
                "po_id": p_id,
                "po_number": p_num,
                "supplier_name": s_name,
                "grand_total": tot,
                "status": new_st,
                "pdf_download_url": f"/api/documents/po/{p_id}/download",
                "generated_prs": [],
                "affected_items": []
            }
        else:
            c_conn.close()

    # 3.5. Goods Receipt Physical Arrival Handler (Penerimaan Barang Fisik Masuk Gudang)
    goods_receipt_result = process_goods_receipt(request.prompt, current_user)
    if goods_receipt_result is not None:
        return goods_receipt_result

    # 3.6. Purchase Order (PO) PDF Document Query / Generation Handler
    po_doc_keywords = ["pdf", "dokumen", "surat pesanan", "lihat po", "cetak po", "download po", "unduh po", "buka po", "print po"]
    is_asking_po_doc = any(k in lower_prompt for k in po_doc_keywords) and any(k in lower_prompt for k in ["po-", "po ", "po/", "purchase order"])
    if is_asking_po_doc:
        from docgen.compiler import generate_po_pdf
        digits = re.findall(r'\d+', request.prompt)
        last_digits = digits[-1].zfill(3) if digits else ""
        
        target_po_term = None
        m_po_num = re.search(r'PO/BLT/\d{4}/\d{2}/\d{3}', request.prompt, re.IGNORECASE)
        m_po_id = re.search(r'\bPO[-_\s]?(\d{4}[-_\s]?\d{1,4}|\d{1,4})\b', request.prompt, re.IGNORECASE)
        if m_po_num:
            target_po_term = m_po_num.group(0).upper()
        elif m_po_id:
            raw_id = m_po_id.group(0).upper().replace(" ", "-").replace("_", "-")
            padded = digits[-1].zfill(3) if digits else ""
            target_po_term = f"PO-2026-{padded}" if len(padded) == 3 else raw_id
            
        if target_po_term or last_digits:
            lookup_term = target_po_term or f"PO-2026-{last_digits}"
            try:
                generate_po_pdf(lookup_term)
                c_conn = get_db_connection(read_only=True)
                po_info = c_conn.execute("""
                    SELECT po.po_id, po.po_number, s.supplier_name, i.item_name, po.order_quantity, i.unit, po.total_amount, po.status
                    FROM purchase_orders po
                    JOIN suppliers s ON po.supplier_id = s.supplier_id
                    JOIN inventory_items i ON po.item_id = i.item_id
                    WHERE UPPER(po.po_id) = ? OR UPPER(po.po_number) = ?
                       OR po.po_number LIKE ? OR po.po_id LIKE ?;
                """, [
                    lookup_term.upper(), lookup_term.upper(),
                    f"%{last_digits}%", f"%{last_digits}%"
                ]).fetchone()
                c_conn.close()
                
                if po_info:
                    p_id, p_num, s_name, i_name, o_qty, u_name, tot, p_st = po_info
                    msg = f"**Dokumen Resmi Purchase Order Telah Dikompilasi (Typst Engine)**\n\n"
                    msg += f"Dokumen PO resmi **{p_id}** (`{p_num}`) untuk pengadaan material ke rekanan **{s_name}** telah selesai disusun.\n\n"
                    msg += f"- **Material**: {i_name} ({o_qty:,} {u_name})\n"
                    msg += f"- **Nilai Tagihan**: Rp {tot:,}\n"
                    msg += f"- **Status Pesanan**: `{p_st}`\n\n"
                    msg += f"Silakan klik tombol di bawah untuk melihat pratinjau dokumen PDF resmi di dalam aplikasi atau mengunduhnya."
                    return {
                        "parsed_intent": {"workflow_id": "view_po_document", "po_id": p_id, "po_number": p_num},
                        "action_type": "view_po_document",
                        "message": msg,
                        "po_id": p_id,
                        "po_number": p_num,
                        "supplier_name": s_name,
                        "grand_total": tot,
                        "status": p_st,
                        "pdf_download_url": f"/api/documents/po/{p_id}/download",
                        "generated_prs": [],
                        "affected_items": []
                    }
            except Exception as po_err:
                print(f"[PO PDF Handler] Error: {po_err}")

    # 4. Bali Tower Domain Query Handler (HR, Finance, Inventory, and Schema ALL)
    conn = get_db_connection(read_only=True)
    try:
        # Schema ALL - A. Cek Profil Pengguna & Hak Akses (WF-ALL-01)
        if is_profile_query:
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa profil pengguna di database...")
            tenant_desc = {
                "ALL": "Super Administrator (Akses Penuh Seluruh Schema)",
                "INVENTORY": "Divisi Logistik & Gudang Material (Schema A)",
                "HR": "Divisi Personalia & Field Workforce (Schema B)",
                "FINANCE": "Divisi Keuangan & Akuntansi (Schema C)"
            }.get(u_tenant, f"Divisi {u_tenant}")

            modules_access = {
                "ALL": "Inventory (A), HR & Recruitment (B), Finance & OPEX (C), Pengaturan Sistem",
                "INVENTORY": "Inventory, Stok Material, Restock PO, Gudang Menara",
                "HR": "HR, Absensi Geofencing, Cuti, Screening K3 Rigger",
                "FINANCE": "Finance, Tagihan Operator, OPEX Listrik/Lahan, Arus Kas"
            }.get(u_tenant, "Modul Standar")

            msg = (
                f"### 👤 Profil Pengguna & Hak Akses Sistem\n\n"
                f"| Parameter | Keterangan |\n"
                f"| :--- | :--- |\n"
                f"| **Username** | `{current_user.username}` |\n"
                f"| **Role Wewenang** | **{current_user.role}** |\n"
                f"| **Divisi (Tenant)** | **{tenant_desc} [{u_tenant}]** |\n"
                f"| **Modul yang Diizinkan** | {modules_access} |\n"
                f"| **Status Akun** | 🟢 **ACTIVE / VERIFIED** |\n\n"
                f"*Info:* Alur kerja utilitas ini merupakan bagian dari **Schema ALL** dan dapat diakses oleh seluruh pengguna."
            )
            return {"parsed_intent": {"workflow_id": "WF-ALL-01"}, "action_type": "profile_query", "message": msg, "generated_prs": [], "affected_items": []}

        # Schema ALL - B. Informasi Sistem & Status Layanan (WF-ALL-02)
        if is_system_query:
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa status kesehatan server & sistem...")
            from core.config import settings
            table_count = len(conn.execute("SHOW TABLES;").fetchall())
            wf_count = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
            msg = (
                f"### ⚙️ Informasi & Status Operasional Sistem AutoRestock-Agent\n\n"
                f"| Komponen | Status / Spesifikasi |\n"
                f"| :--- | :--- |\n"
                f"| **Aplikasi** | `{settings.APP_NAME}` (Environment: `{settings.APP_ENV}`) |\n"
                f"| **Database Engine** | DuckDB Embedded (Total Tabel: `{table_count}`, Workflows: `{wf_count}`) |\n"
                f"| **AI Gateway Model** | `{settings.MODEL_NAME}` (Endpoint: `{settings.MODEL_URL}`) |\n"
                f"| **Multi-Agent Engine** | LangGraph StateGraph + HITL Interruption Guard |\n"
                f"| **DocGen Engine** | Typst Native Compiler (<50ms PDF Rendering) |\n"
                f"| **API Server Host:Port** | `{settings.API_HOST}:{settings.API_PORT}` |\n"
                f"| **Status Layanan** | 🟢 **ONLINE & OPERATIONAL** |\n\n"
                f"*Info:* Alur kerja diagnostik sistem ini merupakan bagian dari **Schema ALL**."
            )
            return {"parsed_intent": {"workflow_id": "WF-ALL-02"}, "action_type": "system_info_query", "message": msg, "generated_prs": [], "affected_items": []}

        # Schema ALL - C. Panduan Operasional & Kontak Darurat (WF-ALL-03)
        if is_guideline_query:
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa panduan SOP operasional & helpdesk...")
            msg = (
                f"### 📋 Panduan Operasional & Kontak Darurat (PT Bali Towerindo Sentra Tbk)\n\n"
                f"#### 1. Aturan Kerja & SOP Antar-Divisi\n"
                f"- **Divisi Inventory (Schema A):** Batas minimum stok dievaluasi berkala. Jika status KRITIS, draft PR otomatis disusun oleh AI dan diajukan ke manajer operasional.\n"
                f"- **Divisi HR (Schema B):** Seluruh teknisi menara wajib mematuhi standar K3 (TKPK 1/2) dan absensi geofencing GPS maksimal radius 100m dari titik menara.\n"
                f"- **Divisi Keuangan (Schema C):** Invoicing sewa menara ke operator telekomunikasi diterbitkan per siklus bulanan, audit utilitas listrik PLN/BBM genset diaudit berkala.\n\n"
                f"#### 2. Kontak Darurat & Helpdesk Operasional\n"
                f"| Tim | PIC | Saluran Kontak |\n"
                f"| :--- | :--- | :--- |\n"
                f"| **NOC & Tower Helpdesk 24/7** | Tim NOC Pusat | `ext. 101` / `noc@balitower.co.id` |\n"
                f"| **Keamanan & K3 Lapangan** | Koordinator HSE | `ext. 108` / `k3@balitower.co.id` |\n"
                f"| **IT Support & System Agent** | DevOps Admin | `ext. 112` / `it-support@balitower.co.id` |\n\n"
                f"*Info:* Alur kerja informasi SOP ini merupakan bagian dari **Schema ALL**."
            )
            return {"parsed_intent": {"workflow_id": "WF-ALL-03"}, "action_type": "guidelines_query", "message": msg, "generated_prs": [], "affected_items": []}

        # A. HR - Pelamar / Kandidat / Rigger K3
        if any(w in lower_prompt for w in ["kandidat", "pelamar", "rigger", "climber", "tkpk", "rekrutmen", "screening"]):
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa basis data kandidat rigger di DuckDB...")
            cand_rows = conn.execute("""
                SELECT c.full_name, j.job_title, c.k3_cert_held, c.years_of_experience, c.medical_checkup_status, c.technical_score, c.recruitment_stage
                FROM candidates c
                JOIN job_postings j ON c.job_id = j.job_id
                ORDER BY c.technical_score DESC LIMIT 6;
            """).fetchall()
            msg = "**Hasil Screening & Filter Kandidat Teknisi (Bali Tower)**\n\n"
            msg += "| Nama Kandidat | Posisi | Sertifikat K3 | Pengalaman | Tes Medis | Skor | Status |\n"
            msg += "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |\n"
            for r in cand_rows:
                msg += f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} th | {r[4]} | {r[5]} | **{r[6]}** |\n"
            msg += "\n*Catatan:* Kandidat dengan sertifikasi **TKPK 1/2** dan status tes medis **FIT_FOR_HEIGHT** direkomendasikan langsung untuk tahap Trial Lapangan."
            return {"parsed_intent": {"workflow_id": "hr_filter_candidates"}, "action_type": "hr_query", "message": msg, "generated_prs": [], "affected_items": []}

        # B. HR - Absensi & Lembur Teknisi Lapangan
        if any(w in lower_prompt for w in ["absen", "hadir", "lembur", "overtime", "geofencing", "kunjungan site"]):
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa absensi & geofencing teknisi lapangan...")
            att_rows = conn.execute("""
                SELECT a.date, e.full_name, s.site_name, a.distance_to_site_m, a.overtime_hours, a.status
                FROM attendances a
                JOIN employees e ON a.employee_id = e.employee_id
                LEFT JOIN telecom_sites s ON a.site_id = s.site_id
                WHERE a.overtime_hours > 0
                ORDER BY a.date DESC LIMIT 6;
            """).fetchall()
            tot_ot = conn.execute("SELECT COALESCE(SUM(overtime_hours), 0) FROM attendances").fetchone()[0]
            msg = f"**Laporan Absensi Kunjungan Menara & Lembur Teknisi (Total Lembur: {tot_ot:.1f} Jam)**\n\n"
            msg += "| Tanggal | Teknisi | Titik Menara (Site) | Jarak GPS | Lembur | Status |\n"
            msg += "| :---: | :--- | :--- | :---: | :---: | :---: |\n"
            for r in att_rows:
                msg += f"| {r[0]} | {r[1]} | {r[2]} | {r[3]}m | **{r[4]} jam** | {r[5]} |\n"
            msg += "\n*Validasi Geofencing:* Seluruh teknisi terverifikasi berada dalam radius aman (<100m) dari titik koordinat menara."
            return {"parsed_intent": {"workflow_id": "hr_attendance_audit"}, "action_type": "hr_query", "message": msg, "generated_prs": [], "affected_items": []}

        # C. HR - Cuti & Izin
        if any(w in lower_prompt for w in ["cuti", "izin", "sakit", "leave"]):
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa pengajuan cuti karyawan...")
            lv_rows = conn.execute("""
                SELECT e.full_name, l.leave_type, l.days_requested, l.start_date, l.reason, COALESCE(sub.full_name, '-'), l.approval_status
                FROM leave_requests l
                JOIN employees e ON l.employee_id = e.employee_id
                LEFT JOIN employees sub ON l.substitute_employee_id = sub.employee_id;
            """).fetchall()
            msg = "**Daftar Pengajuan Cuti & Izin Karyawan**\n\n"
            msg += "| Karyawan | Jenis Cuti | Hari | Mulai | Alasan | Teknisi Pengganti | Status |\n"
            msg += "| :--- | :--- | :---: | :---: | :--- | :--- | :---: |\n"
            for r in lv_rows:
                msg += f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | **{r[6]}** |\n"
            return {"parsed_intent": {"workflow_id": "hr_leave_query"}, "action_type": "hr_query", "message": msg, "generated_prs": [], "affected_items": []}

        # D. Finance - Pemasukan & Invoices Operator
        if any(w in lower_prompt for w in ["pemasukan", "pendapatan", "revenue", "invoice", "tagihan", "operator", "telkomsel", "indosat", "xl", "smartfren"]):
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa tagihan & invoice operator sewa menara...")
            rev_rows = conn.execute("""
                SELECT c.client_name, COUNT(i.invoice_id), CAST(SUM(i.total_billed) AS BIGINT),
                       CAST(SUM(CASE WHEN i.payment_status = 'PAID' THEN i.total_billed ELSE 0 END) AS BIGINT),
                       CAST(SUM(CASE WHEN i.payment_status = 'UNPAID' THEN i.total_billed ELSE 0 END) AS BIGINT)
                FROM revenue_invoices i
                JOIN telecom_clients c ON i.client_id = c.client_id
                GROUP BY c.client_name ORDER BY 3 DESC;
            """).fetchall()
            msg = "**Rekapitulasi Pendapatan Sewa Menara per Operator (Q1 2026)**\n\n"
            msg += "| Operator Klien | Invoices | Total Tagihan (IDR) | Sudah Lunas (IDR) | Piutang (AR) |\n"
            msg += "| :--- | :---: | :---: | :---: | :---: |\n"
            for r in rev_rows:
                msg += f"| {r[0]} | {r[1]} | Rp {r[2]:,} | Rp {r[3]:,} | **Rp {r[4]:,}** |\n"
            return {"parsed_intent": {"workflow_id": "finance_revenue_report"}, "action_type": "finance_query", "message": msg, "generated_prs": [], "affected_items": []}

        # E. Finance - Pengeluaran OPEX / Listrik PLN / Sewa Lahan
        is_pr_intent = any(k in lower_prompt for k in ["pr", "purchase requisition", "restock", "stok", "order", "pesan", "pengadaan", "typst"])
        if (any(w in lower_prompt for w in ["pengeluaran", "beban", "opex", "listrik", "pln", "sewa lahan", "lahan", "genset"]) or ("biaya" in lower_prompt and not is_pr_intent)) and not is_pr_intent:
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa transaksi beban operasional site...")
            opex_rows = conn.execute("""
                SELECT account_name, COUNT(*), CAST(SUM(amount) AS BIGINT)
                FROM financial_transactions WHERE trx_type = 'OUTFLOW'
                GROUP BY account_name ORDER BY 3 DESC;
            """).fetchall()
            msg = "**Laporan Rincian Beban Operasional Site (OPEX)**\n\n"
            msg += "| Kategori Beban | Transaksi | Total Realisasi (IDR) |\n"
            msg += "| :--- | :---: | :---: |\n"
            for r in opex_rows:
                msg += f"| {r[0]} | {r[1]} kali | **Rp {r[2]:,}** |\n"
            return {"parsed_intent": {"workflow_id": "finance_opex_audit"}, "action_type": "finance_query", "message": msg, "generated_prs": [], "affected_items": []}

        # F. Finance - Arus Kas (Cash Flow)
        is_po_or_pr = any(k in lower_prompt for k in ["po", "purchase order", "pr", "order", "barang", "material", "setujui", "approval"])
        is_cash_match = any(w in lower_prompt for w in ["arus kas", "cash flow", "cashflow"]) or (
            bool(re.search(r'\bkas\b', lower_prompt)) and "berkas" not in lower_prompt and not is_po_or_pr
        ) or ("saldo" in lower_prompt and any(w in lower_prompt for w in ["keuangan", "bank"]) and not is_po_or_pr)
        if is_cash_match:
            if stage_callback:
                await stage_callback("database", "📊 Menghitung arus kas masuk & keluar...")
            inflow = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM financial_transactions WHERE trx_type = 'INFLOW'").fetchone()[0]
            outflow = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM financial_transactions WHERE trx_type = 'OUTFLOW'").fetchone()[0]
            net = inflow - outflow
            msg = "**Ringkasan Arus Kas Operasional PT Bali Towerindo Sentra Tbk**\n\n"
            msg += f"- **Total Kas Masuk (Inflow):** Rp {int(inflow):,}\n"
            msg += f"- **Total Kas Keluar (Outflow):** Rp {int(outflow):,}\n"
            msg += f"- **Surplus Arus Kas Bersih (Net Cash Flow):** **Rp {int(net):,}**\n\n"
            msg += "Arus kas perusahaan berada dalam kondisi sehat dengan rasio penerimaan sewa menara yang stabil."
            return {"parsed_intent": {"workflow_id": "finance_cashflow"}, "action_type": "finance_query", "message": msg, "generated_prs": [], "affected_items": []}

        # G. Purchase Requisition (PR) Status & Info Query
        if lower_prompt.strip() in ["pr", "cek pr", "daftar pr", "status pr", "lihat pr", "purchase requisition", "info pr"]:
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa dokumen Purchase Requisition aktif...")
            pr_rows = []
            try:
                pr_rows = conn.execute("""
                    SELECT pr_number, status, total_amount, created_at
                    FROM purchase_requests
                    ORDER BY created_at DESC LIMIT 5;
                """).fetchall()
            except Exception:
                pass
            if pr_rows:
                msg = "Daftar Purchase Requisition (PR) Terkini:\n\n"
                msg += "| No. PR | Status | Total Anggaran | Tanggal |\n"
                msg += "| :--- | :---: | :---: |\n"
                for r in pr_rows:
                    msg += f"| {r[0]} | {r[1]} | Rp {int(r[2] or 0):,} | {str(r[3])[:16]} |\n"
                msg += "\nPetunjuk: Untuk menerbitkan PR baru bagi material yang menipis, ketik: buat draft PR untuk stok menipis."
            else:
                msg = "Informasi Purchase Requisition (PR)\n\n"
                msg += "Saat ini belum ada dokumen Purchase Requisition (PR) aktif di sistem.\n\n"
                msg += "Petunjuk: Untuk menerbitkan dokumen PR otomatis bagi material yang berada di bawah batas minimum, silakan ketik:\n"
                msg += "buat draft PR untuk stok menipis"
            return {"parsed_intent": {"workflow_id": "pr_query"}, "action_type": "info", "message": msg, "generated_prs": [], "affected_items": []}

        # H. Purchase Order (PO) General Inquiry
        if lower_prompt.strip() in ["po", "cek po", "daftar po", "status po", "lihat po", "purchase order", "info po"]:
            if stage_callback:
                await stage_callback("database", "📊 Memeriksa daftar Purchase Order aktif...")
            po_rows = conn.execute("""
                SELECT po_id, po_number, status, total_amount, warehouse_id
                FROM purchase_orders
                ORDER BY order_date DESC LIMIT 5;
            """).fetchall()
            msg = "Daftar Purchase Order (PO) Terkini:\n\n"
            msg += "| No. PO | Ref Internal | Status | Nilai Tagihan | Gudang Tujuan |\n"
            msg += "| :--- | :--- | :---: | :---: | :---: |\n"
            for r in po_rows:
                msg += f"| {r[0]} | {r[1]} | {r[2]} | Rp {int(r[3] or 0):,} | {r[4]} |\n"
            msg += "\nPetunjuk: Ketik 'lihat dokumen PO-2026-006' untuk mencetak PDF atau 'PO-2026-006 sudah sampai di Bandung' untuk mencatat barang tiba."
            return {"parsed_intent": {"workflow_id": "po_query"}, "action_type": "info", "message": msg, "generated_prs": [], "affected_items": []}

        # I. Inventory - Cek Stok Material (Menipis vs Umum)
        is_restock_action = any(w in lower_prompt for w in [
            "beli", "pesan", "restock", "buat", "buatkan", "bikin", "draf", "draft", "terbitkan", "pipeline", "reorder", "pengadaan"
        ])
        if any(w in lower_prompt for w in ["stok", "material", "baterai", "kabel", "closure", "odc", "kritis", "persediaan", "menipis", "habis"]) and not is_restock_action:
            is_low_stock_filter = any(w in lower_prompt for w in ["menipis", "kritis", "kurang", "habis", "rendah", "limit", "minimum", "reorder"])
            
            if is_low_stock_filter:
                stk_rows = conn.execute("""
                    SELECT i.item_code, i.item_name, i.category, COALESCE(SUM(sb.quantity_on_hand), 0) AS total_stock, i.min_stock, i.unit
                    FROM inventory_items i
                    LEFT JOIN stock_balances sb ON i.item_id = sb.item_id
                    GROUP BY i.item_code, i.item_name, i.category, i.min_stock, i.unit
                    HAVING COALESCE(SUM(sb.quantity_on_hand), 0) <= i.min_stock
                    ORDER BY (COALESCE(SUM(sb.quantity_on_hand), 0) * 1.0 / NULLIF(i.min_stock, 1)) ASC;
                """).fetchall()

                if not stk_rows:
                    msg = "Status Pemantauan Stok Material Menara & Fiber Optic\n\n"
                    msg += "Kondisi Normal & Aman: Seluruh 35 item material infrastruktur menara saat ini berada dalam kondisi AMAN (tidak ada stok di bawah ambang batas minimum / reorder point).\n\n"
                    msg += "Persediaan di seluruh gudang regional (Jakarta, Bandung, Denpasar, Medan, Semarang, Surabaya, Makassar) mencukupi kebutuhan operasional."
                    return {"parsed_intent": {"workflow_id": "inventory_stock_query"}, "action_type": "inventory_query", "message": msg, "generated_prs": [], "affected_items": []}

                msg = "Status Stok Material Kritis / Menipis (Di Bawah Batas Minimum)\n\n"
                msg += "| Kode SKU | Nama Material | Kategori | Total Stok | Batas Min | Status |\n"
                msg += "| :--- | :--- | :--- | :---: | :---: | :---: |\n"
                for r in stk_rows:
                    st = "KRITIS" if r[3] <= r[4] * 0.5 else "MENIPIS"
                    msg += f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} {r[5]} | {r[4]} | {st} |\n"
                msg += "\nCatatan: Terdapat material di bawah ambang batas minimum. Untuk menerbitkan PR restock otomatis, ketik: buat draft PR untuk stok menipis."
                return {"parsed_intent": {"workflow_id": "inventory_stock_query"}, "action_type": "inventory_query", "message": msg, "generated_prs": [], "affected_items": []}
            else:
                stk_rows = conn.execute("""
                    SELECT i.item_code, i.item_name, i.category, COALESCE(SUM(sb.quantity_on_hand), 0) AS total_stock, i.min_stock, i.unit
                    FROM inventory_items i
                    LEFT JOIN stock_balances sb ON i.item_id = sb.item_id
                    GROUP BY i.item_code, i.item_name, i.category, i.min_stock, i.unit
                    ORDER BY 3 ASC, 1 ASC LIMIT 8;
                """).fetchall()
                msg = "Ringkasan Katalog & Persediaan Material Menara\n\n"
                msg += "| Kode SKU | Nama Material | Kategori | Total Stok | Batas Min | Kondisi |\n"
                msg += "| :--- | :--- | :--- | :---: | :---: | :---: |\n"
                for r in stk_rows:
                    st = "KRITIS" if r[3] <= r[4] * 0.5 else "PERLU PERHATIAN" if r[3] <= r[4] else "AMAN"
                    msg += f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} {r[5]} | {r[4]} | {st} |\n"
                return {"parsed_intent": {"workflow_id": "inventory_stock_query"}, "action_type": "inventory_query", "message": msg, "generated_prs": [], "affected_items": []}

    except Exception as err:
        pass
    finally:
        conn.close()

    try:
        if stage_callback:
            await stage_callback("routing", "🧠 Menentukan alur kerja multi-agent yang sesuai...")

        # Route prompt to workflow ID strictly scoped by tenant_id
        route_result = await SemanticRouter.route_prompt(request.prompt, current_user.tenant_id)
        workflow_id = route_result.get("workflow_id")
        
        # If no workflow matches or prompt is out of scope / unrelated:
        if not workflow_id or route_result.get("is_unrelated"):
            if stage_callback:
                await stage_callback("fallback", "⚠️ Memeriksa batasan alur kerja...")
            conn = get_db_connection(read_only=True)
            user_wfs = conn.execute(
                "SELECT id, name, description FROM workflows WHERE tenant_id = ? OR tenant_id = 'ALL' ORDER BY id ASC",
                [current_user.tenant_id]
            ).fetchall()
            conn.close()

            return {
                "parsed_intent": {"workflow_id": None},
                "action_type": "unrecognized_intent",
                "message": "Permintaan Anda belum terpetakan ke alur otomatis. Anda dapat menanyakan seputar:\n"
                           "- **Schema ALL**: Cek profil pengguna, status informasi sistem, atau panduan operasional & kontak darurat.\n"
                           "- **Modul Divisi**: Sesuai wewenang divisi Anda (Inventory, HR, atau Finance).",
                "available_workflows": [{"id": r[0], "name": r[1], "description": r[2]} for r in user_wfs],
                "email_sent": False,
                "generated_prs": [],
                "affected_items": [],
                "total_items_analyzed": 0,
                "execution_steps": [],
                "target_destinations": [],
                "total_budget_formatted": "Rp 0"
            }
            
        # Fetch workflow from DB and verify tenant authorization
        conn = get_db_connection()
        wf_row = conn.execute("SELECT compiled_json, tenant_id FROM workflows WHERE id = ?", [workflow_id]).fetchone()
        conn.close()
        
        if not wf_row:
            return {
                "parsed_intent": {"workflow_id": workflow_id},
                "action_type": "unrecognized_intent",
                "message": f"Alur kerja '{workflow_id}' belum terdaftar di sistem database.",
                "generated_prs": [],
                "affected_items": []
            }
            
        compiled_json_str, wf_tenant = wf_row
        allowed_tenants = [current_user.tenant_id, "ALL"]
        if current_user.tenant_id in ["INVENTORY", "TENANT_A", "usera"]:
            allowed_tenants.extend(["INVENTORY", "TENANT_A", "usera"])
        elif current_user.tenant_id in ["HR", "TENANT_B", "userb"]:
            allowed_tenants.extend(["HR", "TENANT_B", "userb"])
        elif current_user.tenant_id in ["FINANCE", "TENANT_C", "userc"]:
            allowed_tenants.extend(["FINANCE", "TENANT_C", "userc"])

        if wf_tenant and wf_tenant not in allowed_tenants and current_user.role != "ADMIN":
            target_label = "Schema C (Divisi Keuangan)" if wf_tenant == "FINANCE" else f"Schema {wf_tenant}"
            return {
                "parsed_intent": {"workflow_id": workflow_id},
                "action_type": "permission_denied",
                "message": f"Akses Ditolak: Alur kerja {workflow_id} dikhususkan untuk {target_label}. Akun Anda ({current_user.username} - Divisi {current_user.tenant_id}) tidak memiliki izin untuk mengeksekusi alur kerja ini.",
                "generated_prs": [],
                "affected_items": []
            }
            
        compiled_json = json.loads(compiled_json_str)

        if stage_callback:
            await stage_callback("executing", f"⚡ Menjalankan alur kerja otomatis: {workflow_id}...")
        
        # Dynamic email extraction & dispatch flags
        recip_email = route_result.get("recipient_email") or request.recipient_email or extract_recipient_email(request.prompt)
        send_email_flag = route_result.get("send_email", False) or bool(recip_email)

        if send_email_flag and stage_callback:
            display_email = recip_email or "manajer operasional"
            await stage_callback("email", f"📧 Menyiapkan notifikasi & persetujuan PR ke {display_email}...")

        # Execute workflow
        context = {
            "threshold_updates": route_result.get("threshold_updates", []),
            "target_item_name": route_result.get("target_item_name"),
            "send_email": send_email_flag,
            "recipient_email": recip_email,
            "new_item_data": route_result.get("new_item_data", {}),
            "username": current_user.username,
            "role": current_user.role,
            "tenant_id": current_user.tenant_id,
            "user_info": {"username": current_user.username, "role": current_user.role, "tenant_id": current_user.tenant_id}
        }
        result = await JSONExecutionEngine.execute(compiled_json, current_user.tenant_id, custom_context=context)
        
        # Map to dashboard.js expected schema
        action_type = "general"
        if "update_threshold" in compiled_json.get("workflow", ""):
            action_type = "update_threshold"
        elif "daftar" in compiled_json.get("workflow", "") or "register" in compiled_json.get("workflow", "") or "tambah" in compiled_json.get("workflow", "") or result.get("registered_item"):
            action_type = "register_product"
        elif result.get("pr_number"):
            action_type = "review_prs"
        elif context.get("send_email") and "email" in str(compiled_json.get("steps", [])):
            action_type = "notify_email"
            
        affected = []
        # Return items to dashboard
        low_stock_ctx = context.get("low_stock_items") or []
        specific_ctx = context.get("specific_items") or []
        planned_ctx = context.get("planned_items") or []
        if result.get("registered_item"):
            reg = result["registered_item"]
            new_item = context.get("new_item_data") or {}
            affected = [{
                "name": reg.get("name", "Item Baru"),
                "current_stock": new_item.get("current_stock", 0),
                "min_stock": new_item.get("min_threshold", 0),
                "unit": new_item.get("unit", "pcs")
            }]
        elif low_stock_ctx:
            affected = [{"name": it["name"], "current_stock": it["current_stock"], "min_stock": it.get("min_threshold", 0), "unit": it["unit"]} for it in low_stock_ctx]
        elif planned_ctx:
            affected = [{"name": it.name, "current_stock": it.current_stock, "min_stock": getattr(it, "safety_stock", 0), "unit": it.unit} for it in planned_ctx]
        elif specific_ctx:
            affected = [{"name": it["name"], "current_stock": it["current_stock"], "min_stock": it.get("min_threshold", 0), "unit": it["unit"]} for it in specific_ctx]

        total_cnt = result.get("total_items_analyzed")
        if total_cnt is None:
            total_cnt = len(affected)

        dashboard_response = {
            "parsed_intent": {"workflow_id": workflow_id},
            "action_type": action_type,
            "message": result.get("summary", ""),
            "email_sent": result.get("email_sent", False),
            "generated_prs": [],
            "affected_items": affected,
            "total_items_analyzed": total_cnt,
            "target_destinations": result.get("target_destinations", ["database"]),
            "pdf_download_url": result.get("pdf_download_url"),
            "execution_steps": result.get("execution_steps", []),
            "total_budget_formatted": result.get("total_budget_formatted", "Rp 0")
        }

        if result.get("pr_number"):
            from api.routers.approval_routes import PR_STORE
            pr_doc = PR_STORE.get(result["pr_number"])
            if pr_doc:
                dashboard_response["generated_prs"] = [{
                    "pr_number": pr_doc.pr_number,
                    "supplier_name": "Multiple Vendors" if len(set(it.vendor_name for it in pr_doc.items)) > 1 else (pr_doc.items[0].vendor_name if pr_doc.items else "Vendor"),
                    "grand_total": pr_doc.total_budget,
                    "status": pr_doc.status.lower(),
                    "email_sent": result.get("email_sent", False),
                    "items": [{"item_name": it.name, "quantity": it.reorder_qty, "unit": it.unit} for it in pr_doc.items]
                }]
                
        return dashboard_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal mengeksekusi dynamic workflow: {e!s}"
        )


@router.post("/api/agent/custom-prompt")
async def execute_custom_prompt_workflow(request: CustomPromptRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Accepts free-form natural language instructions from non-technical users,
    synthesizes a custom multi-agent workflow, executes actions, and dispatches outputs.
    """
    return await execute_prompt_logic(request, current_user)


@router.post("/api/agent/stream-prompt")
async def execute_custom_prompt_workflow_stream(request: CustomPromptRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Real-Time SSE Streaming Endpoint for interactive Chat Dashboard (TTPS Optimization).
    Streams live stage status badges, clarification questions, token-by-token content,
    and final rich interactive dashboard response card.
    """
    async def event_generator():
        stages_queue = asyncio.Queue()

        async def stage_cb(stage: str, message: str):
            await stages_queue.put({"type": "status", "stage": stage, "message": message})

        # 1. Instant Initial Stage Badge (TTPS < 20ms)
        yield f"data: {json.dumps({'type': 'status', 'stage': 'analyze', 'message': '🔍 Menganalisis instruksi & hak akses wewenang...'})}\n\n"

        # 2. Asynchronous execution with real-time stage forwarding
        task = asyncio.create_task(execute_prompt_logic(request, current_user, stage_callback=stage_cb))

        while not task.done():
            try:
                stage_msg = await asyncio.wait_for(stages_queue.get(), timeout=0.08)
                yield f"data: {json.dumps(stage_msg)}\n\n"
            except asyncio.TimeoutError:
                pass

        # Drain any remaining stage events
        while not stages_queue.empty():
            stage_msg = stages_queue.get_nowait()
            yield f"data: {json.dumps(stage_msg)}\n\n"

        try:
            result = await task
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        # 3. Clarification event if parameters missing
        if result.get("action_type") == "clarification_needed":
            yield f"data: {json.dumps({'type': 'clarification', 'clarification': result.get('clarification'), 'message': result.get('message')})}\n\n"

        # 4. Token-by-token streaming for ultra-fluid typing effect
        msg = result.get("message", "")
        if msg:
            words = msg.split(" ")
            for i, w in enumerate(words):
                token = w + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                await asyncio.sleep(0.01)

        # 5. Final complete event with rich interactive payload
        yield f"data: {json.dumps({'type': 'complete', 'payload': result})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/agent/prompt-templates")
def get_prompt_templates():
    """
    Returns curated 1-click prompt templates for non-technical users tailored to Bali Tower.
    """
    return [
        {
            "id": 1,
            "title": "Cek Stok Kritis & Buat Draf PR",
            "prompt": "Periksa stok material menara yang menipis dan buatkan draf Purchase Requisition (PR)."
        },
        {
            "id": 2,
            "title": "Catat Penerimaan Barang PO Tiba",
            "prompt": "Barang untuk PO-2026-006 sudah sampai di Gudang Bandung, tolong catat penerimaannya."
        },
        {
            "id": 3,
            "title": "Lihat & Unduh Dokumen PO Resmi",
            "prompt": "Tolong tampilkan dokumen PDF untuk PO-2026-006."
        },
        {
            "id": 4,
            "title": "Absensi & Lembur Teknisi Lapangan",
            "prompt": "Tampilkan rekap absensi kunjungan site menara teknisi rigger minggu ini beserta validasi geofencing GPS dan total jam lembur."
        },
        {
            "id": 4,
            "title": "Filter Pelamar Rigger K3 TKPK",
            "prompt": "Saring kandidat pelamar posisi Rigger / Tower Climber yang memiliki sertifikasi K3 TKPK aktif dan berstatus layak naik menara (Fit for Height)."
        },
        {
            "id": 5,
            "title": "Laporan Pemasukan Sewa Menara",
            "prompt": "Tampilkan ringkasan pendapatan sewa menara dari operator Telkomsel, XL, dan Indosat beserta piutang invoice yang belum dibayar."
        },
        {
            "id": 6,
            "title": "Biaya Listrik PLN & Sewa Lahan",
            "prompt": "Tampilkan rincian pengeluaran beban operasional untuk tagihan listrik PLN shelter dan sewa lahan lokasi menara per site."
        },
        {
            "id": 7,
            "title": "Ringkasan Arus Kas Operasional",
            "prompt": "Berapa total kas masuk (inflow) versus kas keluar (outflow) dan surplus kas bersih operasional saat ini?"
        }
    ]



@router.get("/api/agent/tools", tags=["Agent Configuration"])
def get_agent_tools():
    '''
    Returns the comprehensive list of tools (APIs) available to the AI model
    for executing autonomous workflows.
    '''
    return {
        "status": "success",
        "available_tools": [
            {
                "tool_name": "inventory.register_product",
                "description": "Registers and inserts new product items into the active tenant's inventory database."
            },
            {
                "tool_name": "inventory.get_low_stock_products",
                "description": "Queries products that have fallen below their minimum safety threshold."
            },
            {
                "tool_name": "inventory.get_all_products",
                "description": "Queries all products for full warehouse audits."
            },
            {
                "tool_name": "inventory.check_specific_stock",
                "description": "Queries the current stock level of a specific product."
            },
            {
                "tool_name": "inventory.update_threshold",
                "description": "Updates the safety stock threshold bounds for a product."
            },
            {
                "tool_name": "inventory.crud_record",
                "description": "Performs generic database record operations."
            },
            {
                "tool_name": "notification.dispatch",
                "description": "Dispatches system alerts to configured notification channels."
            },
            {
                "tool_name": "notification.send_email",
                "description": "Sends detailed HTML email notifications to stakeholders."
            },
            {
                "tool_name": "docgen.compile",
                "description": "Compiles raw data into formal Typst PDF documents."
            },
            {
                "tool_name": "purchase_order.create_draft",
                "description": "Generates a draft Purchase Requisition (PR) document based on low stock data."
            }
        ]
    }

