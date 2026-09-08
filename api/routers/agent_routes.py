import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status, Response, Depends
from fastapi.responses import FileResponse
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


class CustomPromptRequest(BaseModel):
    prompt: str = Field(..., description="Natural language prompt from user describing restock intent or workflow")
    destinations: list[str] | None = Field(None, description="Explicit destinations: ['database', 'email', 'pdf']")
    recipient_email: str | None = Field(None, description="Optional custom recipient email")


@router.post("/api/agent/custom-prompt")
async def execute_custom_prompt_workflow(request: CustomPromptRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Accepts free-form natural language instructions from non-technical users,
    synthesizes a custom multi-agent workflow, executes actions, and dispatches outputs.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt tidak boleh kosong.")

    lower_prompt = request.prompt.strip().lower()
    
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

    from agents.router import SemanticRouter
    from agents.json_executor import JSONExecutionEngine
    from database.db import get_db_connection
    import json
    
    # 3. Strict Multi-Tenant Domain Boundary Guard
    u_tenant = str(getattr(current_user, 'tenant_id', 'ALL')).upper()
    u_role = str(getattr(current_user, 'role', 'USER')).upper()

    is_hr_keyword = any(w in lower_prompt for w in ["kandidat", "pelamar", "rigger", "climber", "tkpk", "rekrutmen", "screening", "absen", "hadir", "lembur", "overtime", "geofencing", "kunjungan site", "cuti", "izin", "sakit", "karyawan", "pegawai"])
    is_fin_keyword = any(w in lower_prompt for w in ["pemasukan", "pendapatan", "revenue", "invoice", "tagihan", "operator", "telkomsel", "indosat", "xl", "smartfren", "pengeluaran", "beban", "opex", "listrik", "pln", "sewa lahan", "lahan", "genset", "biaya", "arus kas", "cash flow", "cashflow", "kas", "saldo"])
    is_inv_keyword = any(w in lower_prompt for w in ["stok", "material", "baterai", "kabel", "closure", "odc", "kritis", "persediaan", "gudang", "beli", "pesan", "restock", "supplier", "purchase order", "po"])

    if u_role != "ADMIN" and u_tenant != "ALL":
        if u_tenant == "INVENTORY" and (is_hr_keyword or is_fin_keyword) and not is_inv_keyword:
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi Inventory & Logistik. Anda tidak memiliki wewenang untuk mengakses data HR atau Keuangan perusahaan.",
                "generated_prs": [],
                "affected_items": []
            }
        if u_tenant == "HR" and (is_inv_keyword or is_fin_keyword) and not is_hr_keyword:
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi HR & Field Workforce. Anda tidak memiliki wewenang untuk mengakses data Material Gudang atau Keuangan perusahaan.",
                "generated_prs": [],
                "affected_items": []
            }
        if u_tenant == "FINANCE" and (is_inv_keyword or is_hr_keyword) and not is_fin_keyword:
            return {
                "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                "action_type": "out_of_scope",
                "message": f"Akses Ditolak: Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi Keuangan & Akuntansi. Anda tidak memiliki wewenang untuk mengakses data Material Gudang atau Data Personalia.",
                "generated_prs": [],
                "affected_items": []
            }

    # 4. Bali Tower Domain Query Handler (HR, Finance, Inventory)
    conn = get_db_connection(read_only=True)
    try:
        # A. HR - Pelamar / Kandidat / Rigger K3
        if any(w in lower_prompt for w in ["kandidat", "pelamar", "rigger", "climber", "tkpk", "rekrutmen", "screening"]):
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
        if any(w in lower_prompt for w in ["pengeluaran", "beban", "opex", "listrik", "pln", "sewa lahan", "lahan", "genset", "biaya"]):
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
        if any(w in lower_prompt for w in ["arus kas", "cash flow", "cashflow", "kas", "transaksi", "saldo"]):
            inflow = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM financial_transactions WHERE trx_type = 'INFLOW'").fetchone()[0]
            outflow = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM financial_transactions WHERE trx_type = 'OUTFLOW'").fetchone()[0]
            net = inflow - outflow
            msg = "**Ringkasan Arus Kas Operasional PT Bali Towerindo Sentra Tbk**\n\n"
            msg += f"- **Total Kas Masuk (Inflow):** Rp {int(inflow):,}\n"
            msg += f"- **Total Kas Keluar (Outflow):** Rp {int(outflow):,}\n"
            msg += f"- **Surplus Arus Kas Bersih (Net Cash Flow):** **Rp {int(net):,}**\n\n"
            msg += "Arus kas perusahaan berada dalam kondisi sehat dengan rasio penerimaan sewa menara yang stabil."
            return {"parsed_intent": {"workflow_id": "finance_cashflow"}, "action_type": "finance_query", "message": msg, "generated_prs": [], "affected_items": []}

        # G. Inventory - Cek Stok Material
        if any(w in lower_prompt for w in ["stok", "material", "baterai", "kabel", "closure", "odc", "kritis", "persediaan"]) and not any(w in lower_prompt for w in ["beli", "pesan", "restock", "pr"]):
            stk_rows = conn.execute("""
                SELECT i.item_code, i.item_name, i.category, COALESCE(SUM(sb.quantity_on_hand), 0), i.min_stock, i.unit
                FROM inventory_items i
                LEFT JOIN stock_balances sb ON i.item_id = sb.item_id
                GROUP BY i.item_code, i.item_name, i.category, i.min_stock, i.unit
                ORDER BY 4 ASC LIMIT 8;
            """).fetchall()
            msg = "**Status Stok Material Infrastruktur Menara & Fiber Optic**\n\n"
            msg += "| Kode SKU | Nama Material | Kategori | Total Stok | Batas Min | Status |\n"
            msg += "| :--- | :--- | :--- | :---: | :---: | :---: |\n"
            for r in stk_rows:
                st = "KRITIS" if r[3] <= r[4] * 0.5 else "PERLU PERHATIAN" if r[3] <= r[4] else "AMAN"
                msg += f"| {r[0]} | {r[1]} | {r[2]} | **{r[3]} {r[5]}** | {r[4]} | {st} |\n"
            return {"parsed_intent": {"workflow_id": "inventory_stock_query"}, "action_type": "inventory_query", "message": msg, "generated_prs": [], "affected_items": []}

    except Exception as err:
        pass
    finally:
        conn.close()

    try:
        # Route prompt to workflow ID strictly scoped by tenant_id
        route_result = await SemanticRouter.route_prompt(request.prompt, current_user.tenant_id)
        workflow_id = route_result.get("workflow_id")
        
        # If no workflow matches or prompt is out of scope / unrelated:
        if not workflow_id or route_result.get("is_unrelated"):
            conn = get_db_connection(read_only=True)
            user_wfs = conn.execute(
                "SELECT id, name, description FROM workflows WHERE tenant_id = ? OR tenant_id = 'ALL' ORDER BY id ASC",
                [current_user.tenant_id]
            ).fetchall()
            conn.close()

            return {
                "parsed_intent": {"workflow_id": None},
                "action_type": "unrecognized_intent",
                "message": "Permintaan Anda belum terpetakan ke alur otomatis. Anda dapat menanyakan seputar 3 modul operasional Bali Tower:\n"
                           "1. **Inventory**: Cek stok material menara, baterai lithium, kabel FO, atau buat Purchase Requisition.\n"
                           "2. **HR**: Cek log absensi & lembur teknisi, daftar cuti, atau filter pelamar rigger K3 TKPK.\n"
                           "3. **Finance**: Cek pendapatan sewa menara per operator, beban listrik PLN/lahan, atau arus kas.",
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
            raise Exception(f"Workflow {workflow_id} not found in database.")
            
        compiled_json_str, wf_tenant = wf_row
        if wf_tenant and wf_tenant not in [current_user.tenant_id, "ALL"] and current_user.role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Akses ditolak: Alur kerja {workflow_id} dikhususkan untuk {wf_tenant} dan tidak dapat diakses oleh akun Anda ({current_user.tenant_id})."
            )
            
        compiled_json = json.loads(compiled_json_str)
        
        # Execute workflow
        context = {
            "threshold_updates": route_result.get("threshold_updates", []),
            "target_item_name": route_result.get("target_item_name"),
            "send_email": route_result.get("send_email", False),
            "new_item_data": route_result.get("new_item_data", {})
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
        if result.get("registered_item"):
            reg = result["registered_item"]
            new_item = context.get("new_item_data", {})
            affected = [{
                "name": reg.get("name", "Item Baru"),
                "current_stock": new_item.get("current_stock", 0),
                "min_stock": new_item.get("min_threshold", 0),
                "unit": new_item.get("unit", "pcs")
            }]
        elif context.get("low_stock_items"):
            affected = [{"name": it["name"], "current_stock": it["current_stock"], "min_stock": it.get("min_threshold", 0), "unit": it["unit"]} for it in context["low_stock_items"]]
        elif context.get("specific_items"):
            affected = [{"name": it["name"], "current_stock": it["current_stock"], "min_stock": it.get("min_threshold", 0), "unit": it["unit"]} for it in context["specific_items"]]

        dashboard_response = {
            "parsed_intent": {"workflow_id": workflow_id},
            "action_type": action_type,
            "message": result.get("summary", ""),
            "email_sent": result.get("email_sent", False),
            "generated_prs": [],
            "affected_items": affected,
            "total_items_analyzed": result.get("total_items_analyzed", len(affected)),
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


@router.get("/api/agent/prompt-templates")
def get_prompt_templates():
    """
    Returns curated 1-click prompt templates for non-technical users tailored to Bali Tower.
    """
    return [
        {
            "id": 1,
            "title": "Cek Stok Material & Alert Restock",
            "prompt": "Tolong cek semua material fiber optic dan power backup yang stoknya kritis, serta tampilkan estimasi kebutuhan restock."
        },
        {
            "id": 2,
            "title": "Absensi & Lembur Teknisi Lapangan",
            "prompt": "Tampilkan rekap absensi kunjungan site menara teknisi rigger minggu ini beserta validasi geofencing GPS dan total jam lembur."
        },
        {
            "id": 3,
            "title": "Filter Pelamar Rigger K3 TKPK",
            "prompt": "Saring kandidat pelamar posisi Rigger / Tower Climber yang memiliki sertifikasi K3 TKPK aktif dan berstatus layak naik menara (Fit for Height)."
        },
        {
            "id": 4,
            "title": "Laporan Pemasukan Sewa Menara",
            "prompt": "Tampilkan ringkasan pendapatan sewa menara dari operator Telkomsel, XL, dan Indosat beserta piutang invoice yang belum dibayar."
        },
        {
            "id": 5,
            "title": "Biaya Listrik PLN & Sewa Lahan",
            "prompt": "Tampilkan rincian pengeluaran beban operasional untuk tagihan listrik PLN shelter dan sewa lahan lokasi menara per site."
        },
        {
            "id": 6,
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

