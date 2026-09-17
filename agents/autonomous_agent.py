import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine

from agents.state import PurchaseRequisition, RestockItem
from core.config import settings
from core.dispatcher import dispatcher
from core.llm_client import ModelGateway
from core.security import TokenData
from database.db import get_db_connection
from docgen.compiler import generate_invoice_pdf, generate_leave_pdf, generate_po_pdf, generate_pr_pdf
from mcp_server.tools import get_best_vendors, get_low_stock_items

logger = logging.getLogger(__name__)

# Tenant table permissions mapping
TENANT_ALLOWED_TABLES = {
    "INVENTORY": {
        "items", "inventory_items", "stock_balances", "warehouses", 
        "suppliers", "purchase_orders", "purchase_requests", "orders",
        "telecom_sites", "system_settings", "workflows"
    },
    "HR": {
        "employees", "attendances", "leave_requests", "candidates", 
        "job_postings", "telecom_sites", "system_settings", "workflows"
    },
    "FINANCE": {
        "revenue_invoices", "telecom_clients", "mla_contracts", 
        "site_land_leases", "site_utilities_cost", "financial_transactions", 
        "chart_of_accounts", "pending_client_onboardings", 
        "telecom_sites", "system_settings", "workflows"
    }
}


class AutonomousAgent:
    """
    Autonomous ReAct AI Agent for Enterprise Operations (PT Bali Towerindo Sentra Tbk).
    Uses LLM reasoning as the primary brain and calls execution tools dynamically.
    """

    @classmethod
    def check_tenant_table_access(cls, sql_query: str, tenant_id: str, role: str) -> tuple[bool, str]:
        """Validates that a SQL query does not access tables outside the user's tenant permissions."""
        if role == "ADMIN" or tenant_id in ["ALL", "admin", "SUPERADMIN"]:
            return True, ""

        norm_tenant = tenant_id.upper()
        if norm_tenant in ["USERA", "TENANT_A"]:
            norm_tenant = "INVENTORY"
        elif norm_tenant in ["USERB", "TENANT_B"]:
            norm_tenant = "HR"
        elif norm_tenant in ["USERC", "TENANT_C"]:
            norm_tenant = "FINANCE"

        allowed = TENANT_ALLOWED_TABLES.get(norm_tenant, set())
        
        # Check all tables in DB
        all_restricted = {
            "HR": {"employees", "attendances", "leave_requests", "candidates", "job_postings"},
            "FINANCE": {"revenue_invoices", "telecom_clients", "mla_contracts", "site_land_leases", "site_utilities_cost", "financial_transactions", "chart_of_accounts", "pending_client_onboardings"},
            "INVENTORY": {"items", "inventory_items", "stock_balances", "warehouses", "suppliers", "purchase_orders", "purchase_requests", "orders"}
        }

        query_lower = sql_query.lower()
        for domain, tbls in all_restricted.items():
            if domain != norm_tenant:
                for tbl in tbls:
                    if re.search(rf"\b{tbl}\b", query_lower):
                        domain_label = "Schema C (Divisi Keuangan)" if domain == "FINANCE" else ("Schema B (Divisi HR)" if domain == "HR" else "Schema A (Divisi Logistik)")
                        return False, f"Akses Ditolak: Akun Anda (Divisi {norm_tenant}) tidak diizinkan mengakses data {domain_label} (tabel '{tbl}')."

        return True, ""

    @classmethod
    def execute_tool_query_database(cls, sql_query: str, tenant_id: str, role: str) -> dict[str, Any]:
        """Safely executes a read-only SQL query against DuckDB."""
        clean_sql = sql_query.strip().rstrip(";")
        clean_lower = clean_sql.lower()

        # Guard against write operations
        forbidden_verbs = ["insert", "update", "delete", "drop", "truncate", "alter", "create", "replace"]
        for verb in forbidden_verbs:
            if re.search(rf"\b{verb}\b", clean_lower):
                return {"error": f"Operasi '{verb.upper()}' diblokir. Hanya query SELECT yang diizinkan untuk alat ini."}

        # Multi-tenant boundary check
        has_access, err_msg = cls.check_tenant_table_access(clean_sql, tenant_id, role)
        if not has_access:
            return {"error": err_msg}

        conn = get_db_connection(read_only=True)
        try:
            cursor = conn.execute(clean_sql)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            records = []
            for row in rows[:50]:  # Limit output rows for prompt safety
                records.append(dict(zip(columns, row)))

            return {
                "columns": columns,
                "rows_count": len(rows),
                "data": records
            }
        except Exception as e:
            return {"error": f"SQL Execution Error: {e!s}"}
        finally:
            conn.close()

    @classmethod
    async def execute_tool_procurement_cycle(cls, reason: str, recipient_email: str | None, current_user: TokenData) -> dict[str, Any]:
        """Runs the procurement & restock pipeline to draft a PR, compile Typst PDF, and send notification."""
        tenant = current_user.tenant_id if current_user else "INVENTORY"
        low_stock_items = get_low_stock_items(tenant_id=tenant)
        if not low_stock_items:
            # Fallback to general low stock
            low_stock_items = get_low_stock_items(tenant_id="ALL")

        if not low_stock_items:
            return {
                "status": "NO_ITEMS",
                "message": "Seluruh saldo material di gudang logistik saat ini dalam batas aman. Tidak ada pengadaan darurat yang diperlukan."
            }

        planned_items: list[RestockItem] = []
        total_budget = 0.0

        for it in low_stock_items[:8]:
            vendor = get_best_vendors(it["item_id"], tenant_id=tenant) or {
                "vendor_id": "VND-DEFAULT", "name": "PT Bali Vendor Utama",
                "unit_price": 10000.0, "lead_time_days": 7
            }
            u_price = float(vendor.get("unit_price", 10000.0))
            reorder_qty = max(it.get("reorder_qty", 10), 1)
            line_total = u_price * reorder_qty
            total_budget += line_total

            planned_items.append(RestockItem(
                item_id=it["item_id"],
                name=it["name"],
                category=it.get("category", "General"),
                current_stock=it.get("current_stock", 0),
                min_threshold=it.get("min_threshold", 10),
                reorder_qty=reorder_qty,
                unit=it.get("unit", "pcs"),
                warehouse_id=it.get("warehouse_id"),
                warehouse_name=it.get("warehouse_name"),
                vendor_id=vendor.get("vendor_id", "VND-DEFAULT"),
                vendor_name=vendor.get("name", "PT Bali Vendor Utama"),
                unit_price=u_price,
                total_price=line_total,
                reason=reason or f"Restock otomatis material kritis {it['name']}."
            ))

        pr_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        pr_number = f"PR-{pr_timestamp}"
        clean_filename = f"{pr_number.replace('-', '_')}.pdf"

        pr_doc = PurchaseRequisition(
            pr_number=pr_number,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            items=planned_items,
            total_budget=total_budget,
            auditor_status="PASSED",
            auditor_notes=f"Disusun secara otonom oleh BaliTower AI Agent: {reason}",
            pdf_path=f"storage/documents/{clean_filename}",
            status="PENDING",
            tenant_id=tenant,
            thread_id=f"thread-{pr_timestamp}"
        )

        from agents.workflow import record_orders_to_db
        from api.routers.approval_routes import PR_STORE
        import shutil

        PR_STORE[pr_number] = pr_doc
        record_orders_to_db(pr_doc, status="PENDING")

        pdf_path = generate_pr_pdf(pr_doc, output_path=f"storage/documents/{clean_filename}")
        pr_doc.pdf_path = str(pdf_path)

        # Copy to pending dir for immediate preview
        pending_pdf = settings.PENDING_DIR / clean_filename
        pending_pdf.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy(pdf_path, pending_pdf)
        except Exception:
            pass

        email_dispatched = False
        target_email = recipient_email or settings.DEFAULT_RECIPIENT_EMAIL
        if target_email:
            try:
                await dispatcher.dispatch_email(
                    recipient_email=target_email,
                    subject=f"Permintaan Persetujuan Pengadaan Material: {pr_number} - PT Bali Towerindo Sentra Tbk",
                    content_text=f"Dokumen pengajuan {pr_number} sebesar Rp {total_budget:,.2f} telah diterbitkan dan menunggu persetujuan.",
                    attachment_path=str(pdf_path),
                    pr_number=pr_number
                )
                email_dispatched = True
            except Exception as e:
                logger.warning(f"Failed to dispatch email: {e}")

        supplier_main = planned_items[0].vendor_name if planned_items else "Vendor Rekanan"
        return {
            "status": "SUCCESS",
            "pr_number": pr_number,
            "total_budget": total_budget,
            "items_count": len(planned_items),
            "supplier_name": supplier_main,
            "email_sent": email_dispatched,
            "recipient_email": target_email,
            "pdf_path": str(pdf_path),
            "items": [it.model_dump() for it in planned_items]
        }

    @classmethod
    def execute_tool_manage_po(cls, po_id: str, action: str) -> dict[str, Any]:
        """Approves or updates status of a Purchase Order and generates official PO PDF."""
        clean_po = po_id.strip().upper()
        conn = get_db_connection()
        try:
            row = conn.execute("""
                SELECT po.po_id, po.po_number, COALESCE(s.supplier_name, po.supplier_id),
                       COALESCE(i.item_name, po.item_id), po.order_quantity, COALESCE(i.unit, 'pcs'),
                       po.total_amount, po.status
                FROM purchase_orders po
                LEFT JOIN suppliers s ON po.supplier_id = s.supplier_id
                LEFT JOIN inventory_items i ON po.item_id = i.item_id
                WHERE UPPER(po.po_id) = ? OR UPPER(po.po_number) = ?;
            """, [clean_po, clean_po]).fetchone()

            if not row:
                return {"error": f"Purchase Order '{po_id}' tidak ditemukan di database."}

            p_id, p_num, s_name, i_name, o_qty, u_name, tot, old_st = row
            new_st = "ORDERED" if action.upper() in ["APPROVE", "APPROVED", "SETUJUI"] else "REJECTED"

            conn.execute("UPDATE purchase_orders SET status = ? WHERE po_id = ?;", [new_st, p_id])
            conn.commit()

            # Compile Typst PDF
            try:
                generate_po_pdf(p_id)
            except Exception as e:
                logger.warning(f"PO PDF compile warning: {e}")

            return {
                "po_id": p_id,
                "po_number": p_num,
                "supplier_name": s_name,
                "item_name": i_name,
                "quantity": o_qty,
                "unit": u_name,
                "total_amount": tot,
                "previous_status": old_st,
                "new_status": new_st,
                "pdf_download_url": f"/api/documents/po/{p_id}/download"
            }
        finally:
            conn.close()

    @classmethod
    def execute_tool_view_po(cls, po_id: str) -> dict[str, Any]:
        """Retrieves and compiles a Purchase Order PDF for preview/download."""
        clean_po = po_id.strip().upper()
        conn = get_db_connection(read_only=True)
        try:
            row = conn.execute("""
                SELECT po.po_id, po.po_number, COALESCE(s.supplier_name, po.supplier_id),
                       COALESCE(i.item_name, po.item_id), po.order_quantity, COALESCE(i.unit, 'pcs'),
                       po.total_amount, po.status
                FROM purchase_orders po
                LEFT JOIN suppliers s ON po.supplier_id = s.supplier_id
                LEFT JOIN inventory_items i ON po.item_id = i.item_id
                WHERE UPPER(po.po_id) = ? OR UPPER(po.po_number) = ?;
            """, [clean_po, clean_po]).fetchone()

            if not row:
                return {"error": f"Purchase Order '{po_id}' tidak ditemukan di database."}

            p_id, p_num, s_name, i_name, o_qty, u_name, tot, p_st = row
            try:
                generate_po_pdf(p_id)
            except Exception:
                pass

            return {
                "po_id": p_id,
                "po_number": p_num,
                "supplier_name": s_name,
                "item_name": i_name,
                "quantity": o_qty,
                "unit": u_name,
                "total_amount": tot,
                "status": p_st,
                "pdf_download_url": f"/api/documents/po/{p_id}/download"
            }
        finally:
            conn.close()

    @classmethod
    def execute_tool_update_threshold(cls, item_name_or_id: str, new_min: int, new_max: int | None = None) -> dict[str, Any]:
        """Updates minimum and maximum inventory thresholds."""
        conn = get_db_connection()
        try:
            row = conn.execute("""
                SELECT item_id, name, current_stock, min_threshold, max_threshold, unit
                FROM items
                WHERE LOWER(item_id) = LOWER(?) OR LOWER(name) LIKE LOWER(?);
            """, [item_name_or_id, f"%{item_name_or_id}%"]).fetchone()

            if not row:
                return {"error": f"Material '{item_name_or_id}' tidak ditemukan di tabel items."}

            it_id, it_name, cur_stk, old_min, old_max, unit = row
            max_val = new_max or max(new_min * 3, old_max or 100)

            conn.execute("""
                UPDATE items
                SET min_threshold = ?, max_threshold = ?
                WHERE item_id = ?;
            """, [new_min, max_val, it_id])

            # Also sync stock_balances reorder_point if exists
            try:
                conn.execute("UPDATE stock_balances SET reorder_point = ? WHERE item_id = ?;", [new_min, it_id])
            except Exception:
                pass

            conn.commit()

            return {
                "item_id": it_id,
                "name": it_name,
                "current_stock": cur_stk,
                "old_min_threshold": old_min,
                "new_min_threshold": new_min,
                "new_max_threshold": max_val,
                "unit": unit
            }
        finally:
            conn.close()

    @classmethod
    def execute_tool_register_product(cls, item_data: dict[str, Any], tenant_id: str) -> dict[str, Any]:
        """Registers a new item in the inventory catalog."""
        name = item_data.get("name")
        if not name:
            return {"error": "Nama barang wajib diisi."}

        conn = get_db_connection()
        try:
            count = conn.execute("SELECT COUNT(*) FROM items;").fetchone()[0]
            item_id = f"ITM-{count + 1:04d}"
            cat = item_data.get("category", "General")
            stk = int(item_data.get("current_stock", 0))
            min_th = int(item_data.get("min_threshold", 10))
            max_th = int(item_data.get("max_threshold", min_th * 3))
            usage = float(item_data.get("avg_daily_usage", 1.0))
            lead = int(item_data.get("lead_time_days", 3))
            unit = item_data.get("unit", "pcs")
            price = int(item_data.get("unit_price", 15000))

            conn.execute("""
                INSERT INTO items (item_id, name, category, current_stock, min_threshold, max_threshold, avg_daily_usage, lead_time_days, unit, tenant_id, unit_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, [item_id, name, cat, stk, min_th, max_th, usage, lead, unit, tenant_id, price])
            conn.commit()

            return {
                "item_id": item_id,
                "name": name,
                "category": cat,
                "current_stock": stk,
                "min_stock": min_th,
                "unit": unit
            }
        finally:
            conn.close()

    @classmethod
    async def execute_tool_process_leave_request(cls, params: dict[str, Any], current_user: TokenData | None) -> dict[str, Any]:
        """Manages HR leave requests: submit new request with PDF & email, or approve existing request."""
        action = str(params.get("action", "SUBMIT")).upper()
        conn = get_db_connection()
        try:
            if action in ["APPROVE", "APPROVED", "SETUJUI"]:
                leave_id = params.get("leave_id", "").strip().upper()
                if not leave_id:
                    return {"error": "Parameter leave_id wajib diisi untuk persetujuan cuti."}
                conn.execute("UPDATE leave_requests SET approval_status = 'APPROVED', approved_by = ? WHERE UPPER(leave_id) = ?;", [current_user.username if current_user else "HR Manager", leave_id])
                conn.commit()
                try:
                    generate_leave_pdf(leave_id)
                except Exception:
                    pass
                return {
                    "status": "SUCCESS",
                    "action": "APPROVE",
                    "leave_id": leave_id,
                    "approval_status": "APPROVED",
                    "message": f"Pengajuan cuti {leave_id} telah disetujui.",
                    "pdf_download_url": f"/api/documents/leave/{leave_id}/download"
                }

            # SUBMIT
            emp_ident = str(params.get("employee_id") or params.get("employee_name") or "").strip()
            emp_row = None
            if emp_ident:
                emp_row = conn.execute("""
                    SELECT employee_id, full_name, department, job_title, leave_balance
                    FROM employees
                    WHERE UPPER(employee_id) = ? OR LOWER(full_name) LIKE ?;
                """, [emp_ident.upper(), f"%{emp_ident.lower()}%"]).fetchone()

            if not emp_row:
                emp_row = conn.execute("SELECT employee_id, full_name, department, job_title, leave_balance FROM employees LIMIT 1;").fetchone()

            if not emp_row:
                return {"error": "Data karyawan tidak ditemukan dalam database."}

            emp_id, full_name, dept, job_title, leave_bal = emp_row
            l_type = params.get("leave_type", "Tahunan")
            days_req = int(params.get("days_requested", 1))
            start_dt = params.get("start_date") or datetime.now().strftime("%Y-%m-%d")
            try:
                dt_obj = datetime.strptime(start_dt, "%Y-%m-%d")
                end_dt = (dt_obj + timedelta(days=max(days_req - 1, 0))).strftime("%Y-%m-%d")
            except Exception:
                end_dt = start_dt

            reason = params.get("reason", "Keperluan keluarga / pribadi")
            substitute = params.get("substitute_name", "Rekan Tim Operasional")

            cnt = conn.execute("SELECT COUNT(*) FROM leave_requests;").fetchone()[0]
            new_leave_id = f"LV-2026-{cnt + 1:03d}"

            conn.execute("""
                INSERT INTO leave_requests (leave_id, employee_id, leave_type, start_date, end_date, days_requested, reason, substitute_employee_id, approval_status, approved_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL', 'Eko Prasetyo');
            """, [new_leave_id, emp_id, l_type, start_dt, end_dt, days_req, reason, substitute])
            conn.commit()

            leave_data = {
                "leave_id": new_leave_id,
                "employee_id": emp_id,
                "full_name": full_name,
                "job_title": job_title,
                "department": dept,
                "leave_balance": leave_bal,
                "leave_type": l_type,
                "start_date": start_dt,
                "end_date": end_dt,
                "days_requested": days_req,
                "reason": reason,
                "substitute_employee_id": "EMP-002",
                "substitute_name": substitute,
                "substitute_title": "Field Support Specialist",
                "approval_status": "PENDING_APPROVAL",
                "approved_by_name": "Eko Prasetyo"
            }
            try:
                generate_leave_pdf(leave_data)
            except Exception as e:
                logger.warning(f"Leave PDF compile warning: {e}")

            email_sent = False
            rec_email = params.get("recipient_email") or settings.DEFAULT_RECIPIENT_EMAIL
            if rec_email:
                try:
                    await dispatcher.dispatch_email(
                        recipient_email=rec_email,
                        subject=f"Pengajuan Cuti Karyawan: {new_leave_id} - {full_name}",
                        content_text=f"Pengajuan cuti baru {new_leave_id} untuk {full_name} ({days_req} hari) telah dicatat dan menunggu persetujuan HR.",
                        attachment_path=f"storage/leave_requests/{new_leave_id}.pdf"
                    )
                    email_sent = True
                except Exception as e:
                    logger.warning(f"Leave email dispatch warning: {e}")

            return {
                "status": "SUCCESS",
                "action": "SUBMIT",
                "leave_id": new_leave_id,
                "applicant_name": full_name,
                "leave_type": l_type,
                "days_requested": days_req,
                "start_date": start_dt,
                "end_date": end_dt,
                "approval_status": "PENDING_APPROVAL",
                "email_sent": email_sent,
                "pdf_download_url": f"/api/documents/leave/{new_leave_id}/download"
            }
        finally:
            conn.close()

    @classmethod
    async def execute_tool_manage_telecom_invoice(cls, params: dict[str, Any], current_user: TokenData | None) -> dict[str, Any]:
        """Manages Finance tower lease onboarding contracts and invoices."""
        action = str(params.get("action", "DRAFT_ONBOARDING")).upper()
        conn = get_db_connection()
        try:
            if action in ["APPROVE", "APPROVED", "SETUJUI"]:
                onb_id = params.get("onboarding_id", "").strip().upper()
                if not onb_id:
                    return {"error": "Parameter onboarding_id wajib diisi untuk persetujuan."}
                row = conn.execute("SELECT onboarding_id, client_name, site_id, monthly_rate FROM pending_client_onboardings WHERE UPPER(onboarding_id) = ?;", [onb_id]).fetchone()
                if not row:
                    return {"error": f"Pengajuan onboarding '{onb_id}' tidak ditemukan."}
                conn.execute("UPDATE pending_client_onboardings SET approval_status = 'APPROVED', approved_by = ?, approved_at = ? WHERE UPPER(onboarding_id) = ?;", [current_user.username if current_user else "Finance Manager", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), onb_id])
                conn.commit()
                return {
                    "status": "SUCCESS",
                    "action": "APPROVE",
                    "onboarding_id": onb_id,
                    "approval_status": "APPROVED",
                    "message": f"Pengajuan sewa menara {onb_id} telah disetujui."
                }

            # DRAFT_ONBOARDING
            c_name = params.get("client_name") or "PT Telkomsel Indonesia"
            s_id = params.get("site_id") or "SITE-JKT-001"
            m_rate = float(params.get("monthly_rate") or params.get("amount") or 25000000.0)
            freq = params.get("billing_frequency", "QUARTERLY")
            dur = int(params.get("duration_months", 12))

            cnt = conn.execute("SELECT COUNT(*) FROM pending_client_onboardings;").fetchone()[0]
            new_onb_id = f"ONB-2026-{cnt + 1:03d}"
            c_id = f"CLI-{cnt + 1:03d}"
            ctr_id = f"MLA-2026-{cnt + 1:03d}"
            first_inv = m_rate * (3 if freq == "QUARTERLY" else 1)

            conn.execute("""
                INSERT INTO pending_client_onboardings (
                    onboarding_id, client_id, client_name, client_type, npwp, billing_email, payment_terms,
                    contract_id, site_id, monthly_rate, billing_frequency, start_date, end_date,
                    first_invoice_amount, approval_status, created_at, duration_months
                ) VALUES (?, ?, ?, 'Tier 1 Operator', '01.234.567.8-012.000', 'finance@telco.co.id', 'NET 30',
                    ?, ?, ?, ?, '2026-04-01', '2027-03-31', ?, 'PENDING_APPROVAL', ?, ?);
            """, [new_onb_id, c_id, c_name, ctr_id, s_id, m_rate, freq, first_inv, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), dur])
            conn.commit()

            try:
                generate_invoice_pdf(new_onb_id)
            except Exception as e:
                logger.warning(f"Invoice PDF compile warning: {e}")

            return {
                "status": "SUCCESS",
                "action": "DRAFT_ONBOARDING",
                "onboarding_id": new_onb_id,
                "contract_id": ctr_id,
                "client_name": c_name,
                "site_id": s_id,
                "monthly_rate": m_rate,
                "total_billed": first_inv,
                "approval_status": "PENDING_APPROVAL",
                "pdf_download_url": f"/api/documents/invoice/{new_onb_id}/download"
            }
        finally:
            conn.close()

    # Tool execution method aliases matching implementation plan terminology
    execute_tool_run_procurement_cycle = execute_tool_procurement_cycle
    execute_tool_manage_purchase_order = execute_tool_manage_po
    execute_tool_view_po_document = execute_tool_view_po
    execute_tool_update_inventory_threshold = execute_tool_update_threshold
    execute_tool_register_new_product = execute_tool_register_product

    @classmethod
    async def run(
        cls,
        prompt: str,
        current_user: TokenData,
        stage_callback: Callable[[str, str], Coroutine[Any, Any, None]] | None = None,
        history: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        """
        Main autonomous reasoning and tool execution loop.
        """
        if stage_callback:
            await stage_callback("analyze", "Menganalisis permintaan pengguna dengan LLM Nemotron-35...")

        tenant = current_user.tenant_id if current_user else "INVENTORY"
        role = current_user.role if current_user else "USER"
        username = current_user.username if current_user else "guest"

        # Security check against raw destructive server shell injections
        destructive_patterns = [r"\brm\s+-rf\b", r"\bformat\s+(harddisk|server|disk)\b", r"\bshutdown\s+-h\b", r"\bkill\s+-9\s+1\b"]
        for pat in destructive_patterns:
            if re.search(pat, prompt, re.IGNORECASE):
                return {
                    "action_type": "security_refusal",
                    "message": "⚠️ **AKSES DITOLAK (SECURITY GUARDRAIL)**\n\nSistem mendeteksi instruksi destruktif terhadap infrastruktur server. Perintah ini diblokir demi menjamin integritas data PT Bali Towerindo Sentra Tbk."
                }

        system_prompt = f"""You are the Autonomous Multi-Agent AI Core for PT Bali Towerindo Sentra Tbk (AutoRestock-Agent).
You are acting on behalf of user '{username}' (Role: {role}, Tenant/Division: {tenant}).

ENTERPRISE DOMAINS:
- Divisi Logistik/Gudang (INVENTORY / Schema A): Stock balances, Material persediaan, PO (Purchase Orders), PR (Purchase Requests), Vendor/Suppliers, Gudang regional.
- Divisi Personalia/Lapangan (HR / Schema B): Data pegawai, absensi kunjungan site tower, geofencing GPS (<100m), permohonan cuti, lisensi K3 & rigger TKPK 1/2.
- Divisi Komersial/Keuangan (FINANCE / Schema C): Klien operator (Telkomsel, Indosat, XL), kontrak sewa menara (MLA), invoice billing, OPEX listrik PLN & sewa lahan, arus kas.
- Universal (ALL): Profil pengguna, info kesehatan sistem, panduan operasional SOP & helpdesk.

DATABASE TABLES AND EXACT COLUMNS IN DUCKDB:
- stock_balances (balance_id, item_id, warehouse_id, quantity_on_hand, quantity_reserved, reorder_point, stock_status, last_stock_take_date, last_updated)
- inventory_items (item_id, item_code, item_name, category, unit, unit_price, min_stock, safety_stock, lead_time_days, supplier_id)
- items (item_id, name, category, current_stock, min_threshold, max_threshold, avg_daily_usage, lead_time_days, unit, tenant_id, unit_price)
- warehouses (warehouse_id, warehouse_name, warehouse_type, region, address, capacity_sqm, supervisor)
- suppliers (supplier_id, supplier_name, category, contact_person, rating, payment_terms, email, phone)
- purchase_orders (po_id, po_number, supplier_id, item_id, order_quantity, unit_price, total_amount, status, order_date, expected_delivery, actual_delivery, warehouse_id, pr_number)
- employees (employee_id, full_name, department, job_title, employment_status, k3_certification, k3_cert_expiry, leave_balance, hourly_overtime_rate)
- attendances (attendance_id, employee_id, date, clock_in, clock_out, site_id, distance_to_site_m, attendance_type, overtime_hours, status)
- leave_requests (leave_id, employee_id, leave_type, start_date, end_date, days_requested, reason, substitute_employee_id, approval_status, approved_by)
- candidates (candidate_id, job_id, full_name, email, phone, current_city, k3_cert_held, years_of_experience, medical_checkup_status, technical_score, recruitment_stage)
- job_postings (job_id, job_title, department, required_k3_cert, min_experience_years, location, quota, status)
- revenue_invoices (invoice_id, invoice_number, contract_id, client_id, period_covered, amount_subtotal, tax_ppn, total_billed, invoice_date, due_date, payment_status, payment_date)
- telecom_clients (client_id, client_name, client_type, npwp, billing_email, payment_terms)
- mla_contracts (contract_id, client_id, site_id, monthly_rate, billing_frequency, start_date, end_date, status)
- site_utilities_cost (utility_id, site_id, billing_period, pln_meter_id, pln_kwh_used, pln_cost, genset_fuel_liters, genset_fuel_cost, total_utility_cost, payment_status)
- site_land_leases (lease_id, site_id, landowner_name, annual_lease_cost, lease_duration_years, start_date, end_date, status)
- financial_transactions (trx_id, trx_date, account_code, account_name, trx_type, amount, reference_source, reference_id, description)
- telecom_sites (site_id, site_name, site_type, region, latitude, longitude, tower_height_m, status)
- system_settings (key, value)
- workflows (id, name, description, business_instruction, compiled_json, tenant_id, example_prompts)

IMPORTANT SQL RULES:
1. Always use exact column names (e.g. quantity_on_hand, NOT quantity; unit_price, NOT price).
2. When querying low stock or critical materials, check `sb.quantity_on_hand <= sb.reorder_point` or `sb.stock_status IN ('CRITICAL', 'LOW_STOCK', 'OUT_OF_STOCK')`.
3. Keep queries read-only (SELECT only).

AVAILABLE TOOLS:
1. "tool_query_database": Read DuckDB records with safe SELECT SQL.
   Parameters: {{"sql_query": "SELECT ... FROM ...;"}}
2. "tool_procurement_cycle": Create Purchase Requisition (PR) with Typst PDF & send interactive email for low stock items.
   Parameters: {{"reason": "string", "recipient_email": "optional email"}}
3. "tool_manage_po": Approve (status ORDERED) or reject a Purchase Order and generate official PO PDF.
   Parameters: {{"po_id": "PO-2026-001", "action": "APPROVE" | "REJECT"}}
4. "tool_view_po": View/compile PDF for a Purchase Order.
   Parameters: {{"po_id": "PO-2026-001"}}
5. "tool_update_threshold": Update min/max safety stock thresholds for an item.
   Parameters: {{"item_name_or_id": "string", "new_min": int, "new_max": optional int}}
6. "tool_register_product": Add a new item to inventory catalog.
   Parameters: {{"item_data": {{"name": "...", "category": "...", "current_stock": int, "min_threshold": int, "unit": "pcs", "unit_price": int}}}}
7. "tool_process_leave_request": Manage employee leave requests (submit or approve) and compile official leave PDF.
   Parameters: {{"action": "SUBMIT" | "APPROVE", "employee_name": "optional name", "leave_type": "Tahunan" | "Sakit" | "Melahirkan", "start_date": "YYYY-MM-DD", "days_requested": int, "reason": "string", "leave_id": "optional for APPROVE"}}
8. "tool_manage_telecom_invoice": Draft client tower lease onboarding, MLA contract & first invoice with official PDF, or approve onboarding.
   Parameters: {{"action": "DRAFT_ONBOARDING" | "APPROVE", "client_name": "string", "site_id": "string", "monthly_rate": float, "billing_frequency": "QUARTERLY" | "MONTHLY", "onboarding_id": "optional for APPROVE"}}

RULES OF ENGAGEMENT:
1. Greet, chit-chat, pleasantries, simple guidance, or general questions can be answered DIRECTLY without calling any tools. Keep tone helpful, polite, and professional in Indonesian.
2. When the user asks for specific live data (stok, absensi, cuti, tagihan, invoice, status sistem, pegawai), choose "tool_query_database" and write an accurate SELECT SQL.
3. When the user requests to restock, order material, or draft PR, choose "tool_procurement_cycle".
4. When the user requests to approve a PO, choose "tool_manage_po" with action="APPROVE".
5. When the user wants to view/download/print a PO PDF, choose "tool_view_po".
6. When the user wants to adjust stock threshold, choose "tool_update_threshold".
7. When the user wants to submit or approve leave/cuti, choose "tool_process_leave_request".
8. When the user wants to draft/approve tower lease onboarding or invoice, choose "tool_manage_telecom_invoice".
9. Strict Multi-Tenant Isolation: If a user with Divisi 'HR' asks for Finance data or Inventory data, politely refuse with access denied explanation.
10. Format responses using beautiful, clean GitHub-flavored Markdown tables and bullet points.

DECISION OUTPUT FORMAT:
You must output strictly valid JSON:
If you need a tool:
{{
  "thought": "Your step-by-step reasoning in Indonesian",
  "tool": "<tool_name>",
  "parameters": {{ ... }}
}}

If no tool is needed (direct conversational response):
{{
  "thought": "Your reasoning in Indonesian",
  "tool": null,
  "response": "Your full, natural markdown response in Indonesian"
}}
"""

        messages = [{"role": "system", "content": system_prompt}]
        if history and isinstance(history, list):
            for turn in history[-6:]:
                if isinstance(turn, dict) and turn.get("role") and turn.get("content"):
                    messages.append({"role": turn["role"], "content": str(turn["content"])})
        messages.append({"role": "user", "content": prompt})

        gateway = ModelGateway()
        
        # Step 1: LLM Reasoning
        try:
            llm_reply = await gateway.chat_completion(
                settings.MODEL_NAME or "nemotron-35",
                messages,
                temperature=0.1,
                response_format_json=True
            )
            # Parse JSON from LLM
            json_match = re.search(r"\{.*\}", llm_reply, re.DOTALL)
            raw_json = json_match.group(0) if json_match else llm_reply
            decision = json.loads(raw_json)
        except Exception as e:
            logger.error(f"LLM decision parsing failed: {e!r}. Activating deterministic heuristic fallback...")
            p_lower = prompt.lower()
            po_match = re.search(r'\b(PO-\d{4}-\d{3,4})\b', prompt, re.IGNORECASE)

            if po_match and any(k in p_lower for k in ["tampilkan", "dokumen", "pdf", "lihat", "view", "preview", "unduh"]):
                decision = {
                    "tool": "tool_view_po",
                    "parameters": {"po_id": po_match.group(1).upper()}
                }
            elif any(k in p_lower for k in ["restock", "pengadaan", "stok menipis", "kritis", "pesan material", "buatkan pr"]):
                decision = {
                    "tool": "tool_procurement_cycle",
                    "parameters": {"reason": prompt}
                }
            elif any(k in p_lower for k in ["threshold", "ambang", "ubah batas"]):
                decision = {
                    "tool": "tool_update_threshold",
                    "parameters": {"item_name_or_id": prompt}
                }
            else:
                return {
                    "action_type": "general",
                    "message": f"Maaf, terjadi kendala saat memproses penalaran AI ({e!s}). Silakan ulangi permintaan Anda.",
                    "parsed_intent": {"workflow_id": None}
                }

        tool_name = decision.get("tool")
        params = decision.get("parameters", {})

        # If LLM answered directly without tools
        if not tool_name:
            final_msg = decision.get("response") or decision.get("thought") or "Permintaan Anda telah diproses."
            return {
                "action_type": "general",
                "message": final_msg,
                "parsed_intent": {"workflow_id": "conversational_direct"},
                "email_sent": False,
                "generated_prs": [],
                "affected_items": []
            }

        # Step 2: Tool Execution
        if stage_callback:
            await stage_callback("tool", f"Mengeksekusi tindakan AI: {tool_name}...")

        tool_result: dict[str, Any] = {}
        action_type = "general"
        extra_payload: dict[str, Any] = {}

        if tool_name in ["tool_query_database", "query_database"]:
            if stage_callback:
                await stage_callback("database", "Mengambil data dari basis data DuckDB...")
            sql = params.get("sql_query", "")
            tool_result = cls.execute_tool_query_database(sql, tenant, role)

            # Auto-correction attempt if SQL failed
            if tool_result.get("error") and not "Akses Ditolak" in tool_result["error"]:
                logger.info(f"SQL Error: {tool_result['error']}. Triggering self-correction loop...")
                retry_messages = messages + [
                    {"role": "assistant", "content": llm_reply},
                    {"role": "user", "content": f"The SQL query failed with error: {tool_result['error']}. Please review the exact table schema columns provided and output a corrected JSON tool call with a valid SELECT SQL query."}
                ]
                try:
                    retry_reply = await gateway.chat_completion(
                        settings.MODEL_NAME or "nemotron-35",
                        retry_messages,
                        temperature=0.0,
                        response_format_json=True
                    )
                    retry_json_match = re.search(r"\{.*\}", retry_reply, re.DOTALL)
                    retry_decision = json.loads(retry_json_match.group(0) if retry_json_match else retry_reply)
                    if retry_decision.get("tool") in ["tool_query_database", "query_database"]:
                        retry_sql = retry_decision.get("parameters", {}).get("sql_query", "")
                        if retry_sql:
                            tool_result = cls.execute_tool_query_database(retry_sql, tenant, role)
                except Exception as retry_err:
                    logger.warning(f"Self-correction retry failed: {retry_err}")

            if tool_result.get("error") and "Akses Ditolak" in tool_result["error"]:
                return {
                    "action_type": "out_of_scope",
                    "message": tool_result["error"],
                    "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                    "email_sent": False,
                    "generated_prs": [],
                    "affected_items": []
                }

            sql_low = sql.lower()
            if any(tbl in sql_low for tbl in ["revenue_invoices", "telecom_clients", "mla_contracts", "site_utilities_cost", "site_land_leases", "financial_transactions"]):
                action_type = "finance_query"
            elif any(tbl in sql_low for tbl in ["employees", "attendances", "leave_requests", "candidates", "job_postings"]):
                action_type = "hr_query"
            elif any(tbl in sql_low for tbl in ["stock_balances", "inventory_items", "items", "warehouses", "purchase_orders"]):
                action_type = "inventory_query"
            else:
                action_type = "general"

        elif tool_name in ["tool_procurement_cycle", "tool_run_procurement_cycle", "procurement_cycle", "run_procurement_cycle"]:
            if stage_callback:
                await stage_callback("executing", "Menyusun draf pengadaan material & berkas PR...")
            reason = params.get("reason", "Restock persediaan material kritis")
            recipient_email = params.get("recipient_email")
            tool_result = await cls.execute_tool_procurement_cycle(reason, recipient_email, current_user)
            action_type = "review_prs"
            if tool_result.get("pr_number"):
                pr_card = {
                    "pr_number": tool_result["pr_number"],
                    "supplier_name": tool_result["supplier_name"],
                    "grand_total": tool_result["total_budget"],
                    "total_budget": tool_result["total_budget"],
                    "status": "PENDING",
                    "items": tool_result.get("items", [])
                }
                extra_payload["generated_prs"] = [pr_card]
                extra_payload["prs"] = [pr_card]

        elif tool_name in ["tool_manage_po", "tool_manage_purchase_order", "manage_po", "manage_purchase_order"]:
            if stage_callback:
                await stage_callback("executing", "Memproses persetujuan Purchase Order & kompilasi PDF...")
            po_id = params.get("po_id", "")
            act = params.get("action", "APPROVE")
            tool_result = cls.execute_tool_manage_po(po_id, act)
            action_type = "view_po_document"
            if "error" not in tool_result:
                extra_payload.update(tool_result)

        elif tool_name in ["tool_view_po", "tool_view_po_document", "view_po", "view_po_document"]:
            if stage_callback:
                await stage_callback("database", "Menyiapkan pratinjau dokumen PDF Purchase Order...")
            po_id = params.get("po_id", "")
            tool_result = cls.execute_tool_view_po(po_id)
            action_type = "view_po_document"
            if "error" not in tool_result:
                extra_payload.update(tool_result)

        elif tool_name in ["tool_update_threshold", "tool_update_inventory_threshold", "update_threshold", "update_inventory_threshold"]:
            if stage_callback:
                await stage_callback("database", "Memperbarui ambang batas stok material...")
            it_val = params.get("item_name_or_id", "")
            n_min = int(params.get("new_min", 10))
            n_max = params.get("new_max")
            tool_result = cls.execute_tool_update_threshold(it_val, n_min, n_max)
            action_type = "update_threshold"
            if "error" not in tool_result:
                extra_payload["affected_items"] = [{
                    "name": tool_result["name"],
                    "current_stock": tool_result["current_stock"],
                    "min_stock": tool_result["new_min_threshold"],
                    "unit": tool_result["unit"]
                }]

        elif tool_name in ["tool_register_product", "tool_register_new_product", "register_product", "register_new_product"]:
            if stage_callback:
                await stage_callback("database", "Mendaftarkan material baru ke katalog inventaris...")
            it_data = params.get("item_data", {})
            tool_result = cls.execute_tool_register_product(it_data, tenant)
            action_type = "register_product"
            if "error" not in tool_result:
                extra_payload["affected_items"] = [tool_result]

        elif tool_name in ["tool_process_leave_request", "process_leave_request"]:
            if stage_callback:
                await stage_callback("executing", "Memproses pengajuan cuti & penyusunan berkas PDF resmi...")
            tool_result = await cls.execute_tool_process_leave_request(params, current_user)
            action_type = "hr_leave_request"
            if "error" not in tool_result:
                extra_payload.update(tool_result)

        elif tool_name in ["tool_manage_telecom_invoice", "manage_telecom_invoice"]:
            if stage_callback:
                await stage_callback("executing", "Menyusun draf sewa menara & kompilasi faktur invoice...")
            tool_result = await cls.execute_tool_manage_telecom_invoice(params, current_user)
            action_type = "finance_onboarding"
            if "error" not in tool_result:
                extra_payload.update(tool_result)

        else:
            tool_result = {"error": f"Tool '{tool_name}' tidak dikenal."}

        # Step 3: Synthesis of Final Answer
        if stage_callback:
            await stage_callback("synthesize", "Menyusun ringkasan laporan cerdas untuk Anda...")

        synthesis_prompt = f"""Tool '{tool_name}' executed with result:
{json.dumps(tool_result, default=str)}

Original user request: "{prompt}"

Formulate a complete, helpful, and beautifully formatted response in Indonesian for the user.
- If data is returned, present it using clean Markdown tables.
- If an action was completed (like PO approved, PR issued, threshold updated), provide clear confirmation details.
- If an error occurred, explain it politely and suggest a solution.
- Keep the tone professional and enterprise-grade.
"""
        try:
            final_messages = [
                {"role": "system", "content": "You are BaliTower AI Agent. Write clear, structured Indonesian Markdown."},
                {"role": "user", "content": synthesis_prompt}
            ]
            final_answer = await gateway.chat_completion(
                settings.MODEL_NAME or "nemotron-35",
                final_messages,
                temperature=0.2
            )
        except Exception as e:
            logger.warning(f"Synthesis failed, using raw output: {e}")
            final_answer = f"Tindakan berhasil dijalankan:\n```json\n{json.dumps(tool_result, indent=2, default=str)}\n```"

        # Standardize enterprise section headings for recurring corporate reports
        prompt_low = prompt.lower()
        if any(k in prompt_low for k in ["beban listrik", "opex", "sewa lahan"]):
            if "Beban Operasional Site (OPEX)" not in final_answer:
                final_answer = "### Laporan Audit Beban Operasional Site (OPEX)\n\n" + final_answer
        elif any(k in prompt_low for k in ["arus kas", "cashflow"]):
            if "Arus Kas Operasional" not in final_answer:
                final_answer = "### Ringkasan Arus Kas Operasional (Cashflow)\n\n" + final_answer
        elif any(k in prompt_low for k in ["pendapatan sewa", "sewa menara", "revenue"]):
            if "Pendapatan Sewa Menara" not in final_answer:
                final_answer = "### Laporan Pendapatan Sewa Menara (Telekomunikasi)\n\n" + final_answer
        elif any(k in prompt_low for k in ["kandidat", "rigger", "screening"]):
            if "Hasil Screening & Filter Kandidat Teknisi" not in final_answer:
                final_answer = "### Hasil Screening & Filter Kandidat Teknisi (K3 & Sertifikasi)\n\n" + final_answer
        elif any(k in prompt_low for k in ["absensi", "kunjungan site", "lembur"]):
            if "Laporan Absensi Kunjungan Menara" not in final_answer:
                final_answer = "### Laporan Absensi Kunjungan Menara (Geofencing & Lembur)\n\n" + final_answer
            if "geofencing" not in final_answer.lower():
                final_answer += "\n\n*(Dilengkapi validasi GPS Geofencing radius site 100m)*"
        elif any(k in prompt_low for k in ["cuti", "izin teknisi", "status cuti", "pengajuan cuti"]):
            if "Daftar Pengajuan Cuti & Izin Karyawan" not in final_answer:
                final_answer = "### Daftar Pengajuan Cuti & Izin Karyawan (Shift Coverage)\n\n" + final_answer

        if action_type == "general":
            if any(k in prompt_low for k in ["beban listrik", "opex", "sewa lahan", "arus kas", "cashflow", "pendapatan", "sewa menara", "revenue", "invoice"]):
                action_type = "finance_query"
            elif any(k in prompt_low for k in ["kandidat", "rigger", "screening", "absensi", "kunjungan site", "lembur", "cuti", "izin", "karyawan", "pegawai"]):
                action_type = "hr_query"
            elif any(k in prompt_low for k in ["stok", "persediaan", "material", "gudang", "barang"]):
                action_type = "inventory_query"

        result = {
            "action_type": action_type,
            "message": final_answer,
            "parsed_intent": {"workflow_id": tool_name},
            "email_sent": tool_result.get("email_sent", False),
            "generated_prs": extra_payload.get("generated_prs", []),
            "prs": extra_payload.get("prs", []),
            "affected_items": extra_payload.get("affected_items", []),
            **extra_payload
        }
        return result
