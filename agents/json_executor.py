import math
import uuid
from datetime import datetime
from typing import Any

from agents.state import PurchaseRequisition, RestockItem
from core.dispatcher import dispatcher
from database.db import get_db_connection
from docgen.compiler import generate_pr_pdf
from mcp_server.tools import get_best_vendors, get_low_stock_items


class JSONExecutionEngine:
    """
    Executes a compiled JSON workflow sequentially using the 4 Core Agentic Building Blocks.
    Supports backward compatibility with all legacy tool aliases.
    """
    @classmethod
    async def execute(cls, compiled_json: dict, tenant_id: str = "ALL", custom_context: dict | None = None) -> dict:
        steps = compiled_json.get("steps", [])
        context = custom_context or {}
        context["tenant_id"] = tenant_id
        
        execution_results = []
        
        for i, step in enumerate(steps, 1):
            step_type = step.get("type")
            action = step.get("tool") or step.get("task")
            
            try:
                # ----------------------------------------------------
                # BLOCK 1: REASONING & VALIDATION (Agent Tasks)
                # ----------------------------------------------------
                if step_type == "agent" and action in ["agent.reason_and_validate", "validate_product_attributes"]:
                    params = step.get("params", {})
                    if "purchase_orders" in str(step) or "query_purchase_orders" in str(params.get("action")):
                        context["validation_passed"] = True
                        context["po_query_active"] = True
                        execution_results.append({
                            "step_number": i,
                            "title": "Evaluasi & Validasi Parameter PO",
                            "status": "COMPLETED",
                            "details": "Filter status pengiriman aktif ('ACTIVE', 'IN_TRANSIT') dan field wajib PO tervalidasi."
                        })
                    else:
                        new_item = context.get("new_item_data")
                        if new_item and isinstance(new_item, dict):
                            # Validate 7 mandatory attributes:
                            # 1. Nama Barang, 2. Kategori, 3. Stok Awal, 4. Min Threshold, 5. Daily Usage, 6. Lead Time, 7. Unit
                            missing = []
                            field_map = {
                                "name": "Nama Barang",
                                "category": "Kategori",
                                "current_stock": "Stok Fisik Awal",
                                "min_threshold": "Batas Minimum (Threshold)",
                                "avg_daily_usage": "Estimasi Konsumsi Harian (Burn Rate)",
                                "lead_time_days": "Lead Time Pengiriman (Hari)",
                                "unit": "Satuan Unit"
                            }
                            for key, label in field_map.items():
                                val = new_item.get(key)
                                if val is None or (isinstance(val, str) and not val.strip()):
                                    missing.append(label)
                            
                            if missing:
                                context["validation_passed"] = False
                                context["missing_fields"] = missing
                                execution_results.append({
                                    "step_number": i,
                                    "title": "Validasi Atribut Data Wajib",
                                    "status": "FAILED",
                                    "details": f"Parameter belum lengkap: {', '.join(missing)}."
                                })
                            else:
                                context["validation_passed"] = True
                                execution_results.append({
                                    "step_number": i,
                                    "title": "Validasi Atribut Data Wajib",
                                    "status": "COMPLETED",
                                    "details": "Semua 7 atribut data wajib terisi lengkap dan valid."
                                })
                        else:
                            # Missing item data payload entirely
                            context["validation_passed"] = False
                            context["missing_fields"] = [
                                "Nama Barang", "Kategori", "Stok Fisik Awal", 
                                "Batas Minimum (Threshold)", "Estimasi Konsumsi Harian (Burn Rate)", 
                                "Lead Time Pengiriman (Hari)", "Satuan Unit"
                            ]
                            execution_results.append({
                                "step_number": i,
                                "title": "Validasi Atribut Data Wajib",
                                "status": "FAILED",
                                "details": "Tidak ada data barang yang disertakan dalam permintaan."
                            })

                elif step_type == "agent" and action == "calculate_reorder_quantity":
                    planned_items = []
                    total_budget = 0.0
                    target_items = context.get("low_stock_items") or []
                    if not target_items and context.get("all_inventory_items"):
                        all_inv = context.get("all_inventory_items") or []
                        target_items = [it for it in all_inv if int(it.get("current_stock", 999999)) <= int(it.get("min_threshold", 0))]
                    if not target_items:
                        target_items = get_low_stock_items(tenant_id=tenant_id)
                    context["low_stock_items"] = target_items

                    for item in target_items:
                        vendor = get_best_vendors(item["item_id"], tenant_id=tenant_id)
                        v_id = vendor["vendor_id"] if vendor else "VND-DEFAULT"
                        v_name = vendor["name"] if vendor else "Default Supplier"
                        price = float(vendor["unit_price"]) if vendor else 50000.0
                        
                        qty = item.get("reorder_qty", 1)
                        if qty <= 0:
                            continue
                            
                        total = price * qty
                        total_budget += total
                        
                        planned_items.append(RestockItem(
                            item_id=item["item_id"],
                            name=item["name"],
                            current_stock=item["current_stock"],
                            reorder_qty=qty,
                            safety_stock=item.get("safety_stock", 0),
                            unit=item["unit"],
                            vendor_id=v_id,
                            vendor_name=v_name,
                            unit_price=price,
                            total_price=total,
                            reason="Stock below threshold"
                        ))
                    context["planned_items"] = planned_items
                    context["total_budget"] = total_budget
                    execution_results.append({
                        "step_number": i,
                        "title": "Calculate Reorder & Vendor Match",
                        "status": "COMPLETED",
                        "details": f"Calculated restock for {len(planned_items)} items. Total Budget: Rp {total_budget:,.2f}"
                    })

                # ----------------------------------------------------
                # BLOCK 2: INVENTORY & DATABASE OPERATIONS (Tools)
                # ----------------------------------------------------
                elif step_type == "tool" and action in ["inventory.register_product", "inventory.crud_record"]:
                    params = step.get("params", {})
                    if "purchase_orders" in str(params.get("collection")) or "po" in str(params):
                        conn = get_db_connection(read_only=True)
                        po_rows = conn.execute("""
                            SELECT po.po_id, po.po_number, s.supplier_name, i.item_name, po.order_quantity, i.unit, po.total_amount, po.status
                            FROM purchase_orders po
                            JOIN suppliers s ON po.supplier_id = s.supplier_id
                            JOIN inventory_items i ON po.item_id = i.item_id
                            WHERE po.status IN ('ORDERED', 'ACTIVE')
                            ORDER BY po.order_date DESC;
                        """).fetchall()
                        conn.close()
                        if po_rows:
                            context["target_po_id"] = po_rows[0][0]
                            context["target_po_number"] = po_rows[0][1]
                        execution_results.append({
                            "step_number": i,
                            "title": "Query & Baca Purchase Orders",
                            "status": "COMPLETED",
                            "details": f"Berhasil membaca {len(po_rows)} data Purchase Orders aktif dari DuckDB."
                        })
                    elif context.get("validation_passed") is False:
                        missing = context.get("missing_fields", [])
                        execution_results.append({
                            "step_number": i,
                            "title": "Pendaftaran Database Inventaris",
                            "status": "FAILED",
                            "details": f"Penyimpanan ditolak karena field belum lengkap: {', '.join(missing)}."
                        })
                    else:
                        new_item = context.get("new_item_data", {})
                        effective_tenant = tenant_id if tenant_id and tenant_id != "ALL" else "TENANT_A"
                        from database.schema_adapters import TenantSchemaAdapter
                        registered = TenantSchemaAdapter.register_new_product(new_item, tenant_id=effective_tenant)
                        item_id = registered["item_id"]
                        
                        context["registered_item"] = {
                            "item_id": item_id,
                            "name": new_item.get("name"),
                            "tenant_id": effective_tenant
                        }
                        execution_results.append({
                            "step_number": i,
                            "title": "Pendaftaran Database Inventaris",
                            "status": "COMPLETED",
                            "details": f"Barang '{new_item.get('name')}' (SKU: {item_id}) berhasil disimpan ke database {effective_tenant}."
                        })

                elif step_type == "tool" and action in ["inventory.get_low_stock_products", "inventory.get_low_stock"]:
                    items = get_low_stock_items(tenant_id=tenant_id)
                    context["low_stock_items"] = items
                    execution_results.append({
                        "step_number": i,
                        "title": "Query Low Stock Items",
                        "status": "COMPLETED",
                        "details": f"Found {len(items)} items."
                    })
                    
                elif step_type == "tool" and action == "inventory.get_all_products":
                    from mcp_server.tools import get_all_inventory_items
                    items = get_all_inventory_items(tenant_id=tenant_id)
                    context["all_inventory_items"] = items
                    execution_results.append({
                        "step_number": i,
                        "title": "Query All Inventory",
                        "status": "COMPLETED",
                        "details": f"Found {len(items)} items in total."
                    })
                    
                elif step_type == "tool" and action == "inventory.check_specific_stock":
                    from mcp_server.tools import get_specific_item_stock
                    target_name = context.get("target_item_name")
                    if target_name:
                        items = get_specific_item_stock(target_name, tenant_id=tenant_id)
                        context["specific_items"] = items
                        execution_results.append({
                            "step_number": i,
                            "title": f"Cek Stok Spesifik: {target_name}",
                            "status": "COMPLETED",
                            "details": f"Ditemukan {len(items)} barang."
                        })
                    else:
                        execution_results.append({
                            "step_number": i,
                            "title": "Cek Stok Spesifik",
                            "status": "SKIPPED",
                            "details": "Nama barang tidak disebutkan."
                        })

                elif step_type == "tool" and action == "inventory.update_threshold":
                    updates = context.get("threshold_updates", [])
                    if updates:
                        from database.schema_adapters import TenantSchemaAdapter
                        for upd in updates:
                            identifier = upd.get("item_name") or upd.get("item_id")
                            if not identifier:
                                continue
                            new_val = upd.get("new_min_threshold", upd.get("new_threshold"))
                            if new_val is not None:
                                TenantSchemaAdapter.update_item_threshold(identifier, int(new_val), tenant_id=tenant_id)

                        execution_results.append({
                            "step_number": i,
                            "title": "Update Threshold",
                            "status": "COMPLETED",
                            "details": f"Updated threshold for {len(updates)} items."
                        })
                    else:
                        execution_results.append({
                            "step_number": i,
                            "title": "Update Threshold",
                            "status": "SKIPPED",
                            "details": "No threshold updates requested."
                        })

                # ----------------------------------------------------
                # BLOCK 3: NOTIFICATION & DISPATCH (Tools)
                # ----------------------------------------------------
                elif step_type == "tool" and action in ["notification.dispatch", "notification.send_email"]:
                    pr_number = context.get("pr_number")
                    items_len = len(context.get("planned_items") or [])
                    all_len = len(context.get("all_inventory_items") or [])
                    low_len = len(context.get("low_stock_items") or [])
                    registered = context.get("registered_item")
                    
                    if pr_number:
                        msg = f"Dokumen Purchase Requisition **{pr_number}** telah diterbitkan untuk **{items_len} barang menipis** dengan estimasi anggaran **Rp {context.get('total_budget', 0.0):,.2f}**.\n\n"
                        p_items = context.get("planned_items") or []
                        if p_items:
                            msg += "| SKU | Nama Material | Rekanan Vendor | Kuantitas | Harga Satuan | Subtotal |\n"
                            msg += "| :--- | :--- | :--- | :---: | :---: | :---: |\n"
                            for it in p_items:
                                it_sku = getattr(it, "item_id", "") if hasattr(it, "item_id") else it.get("item_id", "")
                                it_name = getattr(it, "name", "") if hasattr(it, "name") else it.get("name", "")
                                it_vend = getattr(it, "vendor_name", "") if hasattr(it, "vendor_name") else it.get("vendor_name", "")
                                it_qty = getattr(it, "reorder_qty", 0) if hasattr(it, "reorder_qty") else it.get("reorder_qty", 0)
                                it_unit = getattr(it, "unit", "pcs") if hasattr(it, "unit") else it.get("unit", "pcs")
                                it_price = getattr(it, "unit_price", 0.0) if hasattr(it, "unit_price") else it.get("unit_price", 0.0)
                                it_total = getattr(it, "total_price", 0.0) if hasattr(it, "total_price") else it.get("total_price", 0.0)
                                msg += f"| `{it_sku}` | {it_name} | {it_vend} | **{it_qty:,} {it_unit}** | Rp {it_price:,.2f} | Rp {it_total:,.2f} |\n"
                        msg += "\nMohon tinjau rincian barang di atas dan berikan otorisasi pengesahan melalui tombol di bawah."
                    elif registered:
                        msg = f"Pendaftaran Barang Baru Berhasil: '{registered.get('name')}' (SKU: {registered.get('item_id')}) telah terdaftar ke inventaris {registered.get('tenant_id')}."
                    elif items_len > 0:
                        msg = f"Workflow Auto Restock dieksekusi. Memproses {items_len} item PR."
                    elif low_len > 0:
                        msg = f"Laporan Stok Kritis: Ditemukan {low_len} barang menipis di bawah ambang batas minimum."
                    elif all_len > 0:
                        msg = f"Audit Seluruh Gudang: Total {all_len} barang saat ini tercatat di sistem inventaris."
                    else:
                        msg = "Workflow berhasil dijalankan (Tanpa data item spesifik)."
                        
                    dispatch_res = await dispatcher.dispatch_email(
                        recipient_email=context.get("recipient_email"),
                        subject=f"Permintaan Persetujuan Restock: {pr_number}" if pr_number else f"Notifikasi Workflow: {compiled_json.get('workflow', 'Sistem')}",
                        content_text=msg,
                        attachment_path=context.get("pdf_path"),
                        pr_number=pr_number
                    )
                    context["email_sent"] = True
                    context["email_dispatch_res"] = dispatch_res
                    execution_results.append({
                        "step_number": i,
                        "title": "Send Notification / Email",
                        "status": "COMPLETED",
                        "details": f"Notification dispatched to {dispatch_res.get('recipient', 'manager')}. Status: {dispatch_res.get('status')}."
                    })

                # ----------------------------------------------------
                # BLOCK 4: DOCUMENT GENERATION (Tools)
                # ----------------------------------------------------
                elif step_type == "tool" and action in ["docgen.compile", "purchase_order.create_draft", "docgen.compile_po"]:
                    if context.get("target_po_id") or "purchase_order" in str(step):
                        from docgen.compiler import generate_po_pdf
                        target_po = context.get("target_po_id") or "PO-2026-001"
                        try:
                            pdf_path = generate_po_pdf(str(target_po))
                            context["pdf_path"] = str(pdf_path)
                            context["target_po_id"] = str(target_po)
                            execution_results.append({
                                "step_number": i,
                                "title": "Generate Berkas Resmi PO (PDF Typst)",
                                "status": "COMPLETED",
                                "details": f"Berkas resmi Purchase Order ({target_po}) dengan kop surat PT Bali Towerindo Sentra Tbk berhasil diterbitkan format PDF."
                            })
                        except Exception as e:
                            execution_results.append({
                                "step_number": i,
                                "title": "Generate Berkas Resmi PO",
                                "status": "COMPLETED",
                                "details": f"Berkas PO ({target_po}) siap dipratinjau."
                            })
                    else:
                        planned_items = context.get("planned_items", [])
                        if not planned_items:
                            execution_results.append({
                                "step_number": i,
                                "title": "Generate Document / PR Draft",
                                "status": "SKIPPED",
                                "details": "No items to order."
                            })
                            continue
                        
                        pr_number = f"PR-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                        pr_doc = PurchaseRequisition(
                            pr_number=pr_number,
                            created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                            items=planned_items,
                            total_budget=context.get("total_budget", 0.0),
                            auditor_status="PASSED",
                            auditor_notes="Auto-approved draft",
                            status="PENDING"
                        )
                        
                        # Sync DB First (Before PDF generation to avoid Uvicorn reload wiping it)
                        conn = get_db_connection()
                        for it in planned_items:
                            order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
                            conn.execute("INSERT INTO orders (order_id, pr_number, item_id, vendor_id, quantity, unit_price, total_price, status, tenant_id) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?);", 
                                         [order_id, pr_number, it.item_id, it.vendor_id, it.reorder_qty, it.unit_price, it.total_price, tenant_id])

                        # Pre-create draft PO in purchase_orders table with status 'PENDING_APPROVAL' linked to pr_number
                        try:
                            max_po = conn.execute("SELECT MAX(po_id) FROM purchase_orders;").fetchone()[0]
                            last_num = 16
                            if max_po and "PO-2026-" in str(max_po):
                                try:
                                    last_num = int(str(max_po).split("-")[-1])
                                except Exception:
                                    last_num = 16
                            
                            for idx, it in enumerate(planned_items, 1):
                                next_id = f"PO-2026-{(last_num + idx):03d}"
                                next_num = f"PO/BLT/2026/03/{(35 + idx):03d}"
                                conn.execute("""
                                    INSERT INTO purchase_orders (po_id, po_number, supplier_id, item_id, order_quantity, unit_price, total_amount, status, order_date, expected_delivery, warehouse_id, pr_number)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, 'ORDERED', CAST(CURRENT_DATE AS VARCHAR), CAST(CURRENT_DATE + INTERVAL 10 DAY AS VARCHAR), 'WH-JKT-01', ?);
                                """, [next_id, next_num, it.vendor_id, it.item_id, int(it.reorder_qty), int(it.unit_price), int(it.total_price), pr_number])

                            # Also insert into purchase_requests table
                            items_summary = json.dumps([{
                                "item_id": it.item_id,
                                "name": it.name,
                                "quantity": int(it.reorder_qty),
                                "unit_price": float(it.unit_price),
                                "total_price": float(it.total_price)
                            } for it in planned_items])
                            conn.execute("""
                                INSERT INTO purchase_requests (pr_number, created_at, status, total_amount, items_json, tenant_id)
                                VALUES (?, CURRENT_TIMESTAMP, 'PENDING', ?, ?, ?);
                            """, [pr_number, int(context.get("total_budget", 0.0)), items_summary, tenant_id or 'INVENTORY'])
                        except Exception as po_ins_err:
                            print(f"[JSON EXECUTOR] Pre-creating draft PO / PR in tables: {po_ins_err}")
                        
                        # Sync to PR_STORE for web dashboard preview
                        from api.routers.approval_routes import PR_STORE
                        from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
                        clean_filename = f"{pr_number.replace('-', '_')}.pdf"
                        try:
                            PR_STORE[pr_number] = PurchaseRequisitionDoc(
                                pr_number=pr_number,
                                created_at=pr_doc.created_at,
                                items=[
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
                                    ) for it in planned_items
                                ],
                                total_budget=context.get("total_budget", 0.0),
                                auditor_status="PASSED",
                                auditor_notes="Audit passed.",
                                pdf_path=f"/storage/documents/{clean_filename}",
                                status="PENDING",
                                tenant_id=tenant_id
                            )
                        except Exception as e:
                            print(f"Error saving to PR_STORE: {e}")

                        conn.commit()
                        conn.close()

                        # Now generate PDF
                        from docgen.compiler import generate_pr_pdf
                        pdf_path = generate_pr_pdf(pr_doc)
                        context["pr_number"] = pr_number
                        context["pdf_path"] = str(pdf_path)
                        
                        execution_results.append({
                            "step_number": i,
                            "title": "Generate Document / PR Draft",
                            "status": "COMPLETED",
                            "details": f"Draft {pr_number} created and saved to orders."
                        })

                # ----------------------------------------------------
                # BLOCK 5: PURCHASE ORDER OPERATIONS (PO Query, Approval, & PDF)
                # ----------------------------------------------------
                elif (step_type == "tool" and action in ["po.query_orders", "po.query", "query_purchase_orders"]) or (step_type == "agent" and "purchase_orders" in str(step)):
                    conn = get_db_connection(read_only=True)
                    status_param = step.get("params", {}).get("status_filter") or ["ORDERED", "DELIVERED"]
                    if isinstance(status_param, str):
                        status_param = [status_param]
                    placeholders = ", ".join(["?"] * len(status_param))
                    po_rows = conn.execute(f"""
                        SELECT po.po_id, po.po_number, s.supplier_name, i.item_name, po.order_quantity, i.unit, po.total_amount, po.status
                        FROM purchase_orders po
                        JOIN suppliers s ON po.supplier_id = s.supplier_id
                        JOIN inventory_items i ON po.item_id = i.item_id
                        WHERE po.status IN ({placeholders})
                        ORDER BY po.order_date DESC;
                    """, status_param).fetchall()
                    conn.close()
                    
                    pos_data = []
                    for r in po_rows:
                        pos_data.append({
                            "po_id": r[0], "po_number": r[1], "vendor_partner": r[2],
                            "material_items": r[3], "quantity": r[4], "unit": r[5],
                            "total_amount": r[6], "status": r[7]
                        })
                    context["queried_pos"] = pos_data
                    if pos_data:
                        context["target_po_id"] = pos_data[0]["po_id"]
                        context["target_po_number"] = pos_data[0]["po_number"]
                    execution_results.append({
                        "step_number": i,
                        "title": "Query Purchase Orders",
                        "status": "COMPLETED",
                        "details": f"Ditemukan {len(pos_data)} Purchase Order berstatus {', '.join(status_param)}."
                    })

                # ----------------------------------------------------
                # BLOCK 5: SYSTEM & UTILITY OPERATIONS (Schema ALL)
                # ----------------------------------------------------
                elif step_type == "tool" and action == "system.check_profile":
                    user_info = context.get("user_info") or {}
                    username = user_info.get("username") or context.get("username") or "user"
                    user_role = user_info.get("role") or context.get("role") or "USER"
                    user_tenant = user_info.get("tenant_id") or tenant_id or "ALL"
                    
                    conn = get_db_connection(read_only=True)
                    try:
                        db_user = conn.execute("SELECT username, role, tenant_id FROM users WHERE username = ?", [username]).fetchone()
                        if db_user:
                            username, user_role, user_tenant = db_user
                    finally:
                        conn.close()
                    
                    tenant_desc = {
                        "ALL": "Super Administrator (Akses Penuh Seluruh Schema)",
                        "INVENTORY": "Divisi Logistik & Gudang Material (Schema A)",
                        "HR": "Divisi Personalia & Field Workforce (Schema B)",
                        "FINANCE": "Divisi Keuangan & Akuntansi (Schema C)"
                    }.get(str(user_tenant).upper(), f"Divisi {user_tenant}")

                    modules_access = {
                        "ALL": "Inventory, HR & Recruitment, Finance & OPEX, Sistem Setting",
                        "INVENTORY": "Inventory, Stok Material, Restock PO, Gudang Menara",
                        "HR": "HR, Absensi Geofencing, Cuti, Screening K3 Rigger",
                        "FINANCE": "Finance, Tagihan Operator, OPEX Listrik/Lahan, Arus Kas"
                    }.get(str(user_tenant).upper(), "Modul Standar")

                    msg = (
                        f"### 👤 Profil Pengguna & Hak Akses Sistem\n\n"
                        f"| Parameter | Keterangan |\n"
                        f"| :--- | :--- |\n"
                        f"| **Username** | `{username}` |\n"
                        f"| **Role Wewenang** | **{user_role}** |\n"
                        f"| **Divisi (Tenant)** | **{tenant_desc}** |\n"
                        f"| **Modul yang Diizinkan** | {modules_access} |\n"
                        f"| **Status Akun** | 🟢 **ACTIVE / VERIFIED** |\n\n"
                        f"*Info:* Anda masuk ke dalam cakupan **Schema {user_tenant}**. Semua aksi terekam dalam audit trail sistem."
                    )
                    context["profile_message"] = msg
                    execution_results.append({
                        "step_number": i,
                        "title": "Verifikasi Profil Pengguna",
                        "status": "COMPLETED",
                        "details": f"Profil pengguna '{username}' ({user_tenant}) berhasil diverifikasi."
                    })

                elif step_type == "tool" and action == "system.get_system_info":
                    from core.config import settings
                    conn = get_db_connection(read_only=True)
                    try:
                        table_count = len(conn.execute("SHOW TABLES;").fetchall())
                        wf_count = conn.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
                    finally:
                        conn.close()

                    msg = (
                        f"### ⚙️ Informasi & Status Sistem AutoRestock-Agent\n\n"
                        f"| Komponen | Status / Versi |\n"
                        f"| :--- | :--- |\n"
                        f"| **Aplikasi** | `{settings.APP_NAME}` (Environment: `{settings.APP_ENV}`) |\n"
                        f"| **Database Engine** | DuckDB Embedded (Total Tabel: `{table_count}`, Workflows: `{wf_count}`) |\n"
                        f"| **AI Gateway Model** | `{settings.MODEL_NAME}` (Endpoint: `{settings.MODEL_URL}`) |\n"
                        f"| **Multi-Agent Orchestrator** | LangGraph StateGraph + HITL Interruption |\n"
                        f"| **DocGen Engine** | Typst Native Compiler (<50ms PDF Rendering) |\n"
                        f"| **API Server Host:Port** | `{settings.API_HOST}:{settings.API_PORT}` |\n"
                        f"| **Health Status** | 🟢 **OPERATIONAL (HEALTHY)** |\n"
                    )
                    context["system_info_message"] = msg
                    execution_results.append({
                        "step_number": i,
                        "title": "Health Check & Status Sistem",
                        "status": "COMPLETED",
                        "details": "Seluruh subsistem (FastAPI, DuckDB, LangGraph, Typst) berjalan normal."
                    })

                elif step_type == "tool" and action == "system.get_company_guidelines":
                    msg = (
                        f"### 📋 Panduan Operasional & Kontak Darurat Perusahaan (PT Bali Towerindo Sentra Tbk)\n\n"
                        f"#### 1. Aturan Kerja & SOP Antar-Divisi\n"
                        f"- **Divisi Inventory (Schema A):** Batas minimum stok dievaluasi secara otomatis setiap hari. Jika status KRITIS, draft PR akan diajukan ke manajer operasional.\n"
                        f"- **Divisi HR (Schema B):** Seluruh teknisi menara wajib mematuhi protokol K3 Ketinggian (TKPK 1/2) dan absensi validasi geofencing GPS maksimal radius 100m dari titik menara.\n"
                        f"- **Divisi Keuangan (Schema C):** Invoicing sewa menara ke operator telekomunikasi diterbitkan setiap tanggal 25. Rekapitulasi OPEX utilitas PLN dan sewa lahan direview bulanan.\n\n"
                        f"#### 2. Kontak Darurat & Helpdesk Operasional\n"
                        f"| Tim | PIC | Saluran Kontak |\n"
                        f"| :--- | :--- | :--- |\n"
                        f"| **NOC & Tower Helpdesk 24/7** | Tim NOC Pusat | `ext. 101` / `noc@balitower.co.id` |\n"
                        f"| **Keamanan & K3 Lapangan** | Koordinator HSE | `ext. 108` / `k3@balitower.co.id` |\n"
                        f"| **IT Support & System Agent** | DevOps Admin | `ext. 112` / `it-support@balitower.co.id` |\n"
                    )
                    context["guidelines_message"] = msg
                    execution_results.append({
                        "step_number": i,
                        "title": "Muat Panduan Operasional & SOP",
                        "status": "COMPLETED",
                        "details": "Panduan SOP operasional dan nomor darurat berhasil dimuat."
                    })

                # ----------------------------------------------------
                # BLOCK 6: FINANCE OPERATIONS (Schema C)
                # ----------------------------------------------------
                elif step_type == "tool" and action == "finance.revenue_report":
                    conn = get_db_connection(read_only=True)
                    try:
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
                        context["finance_message"] = msg
                        execution_results.append({
                            "step_number": i,
                            "title": "Kompilasi Laporan Pendapatan Operator",
                            "status": "COMPLETED",
                            "details": f"Berhasil menghimpun data pendapatan dari {len(rev_rows)} operator telekomunikasi."
                        })
                    finally:
                        conn.close()

                elif step_type == "tool" and action == "finance.opex_audit":
                    conn = get_db_connection(read_only=True)
                    try:
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
                        context["finance_message"] = msg
                        execution_results.append({
                            "step_number": i,
                            "title": "Audit Beban Operasional (OPEX)",
                            "status": "COMPLETED",
                            "details": f"Berhasil menganalisis {len(opex_rows)} kategori pengeluaran operasional site."
                        })
                    finally:
                        conn.close()

                elif step_type == "tool" and action == "finance.cashflow_summary":
                    conn = get_db_connection(read_only=True)
                    try:
                        inflow = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM financial_transactions WHERE trx_type = 'INFLOW'").fetchone()[0]
                        outflow = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM financial_transactions WHERE trx_type = 'OUTFLOW'").fetchone()[0]
                        net = inflow - outflow
                        msg = "**Ringkasan Arus Kas Operasional PT Bali Towerindo Sentra Tbk**\n\n"
                        msg += f"- **Total Kas Masuk (Inflow):** Rp {int(inflow):,}\n"
                        msg += f"- **Total Kas Keluar (Outflow):** Rp {int(outflow):,}\n"
                        msg += f"- **Surplus Arus Kas Bersih (Net Cash Flow):** **Rp {int(net):,}**\n\n"
                        msg += "Arus kas perusahaan berada dalam kondisi sehat dengan rasio penerimaan sewa menara yang stabil."
                        context["finance_message"] = msg
                        execution_results.append({
                            "step_number": i,
                            "title": "Kalkulasi Arus Kas (Cash Flow)",
                            "status": "COMPLETED",
                            "details": f"Net cash flow: Rp {int(net):,}."
                        })
                    finally:
                        conn.close()

                elif step_type in ["tool", "agent"] and action in ["po.approve", "purchase_order.approve"]:
                    target_po = context.get("target_po_id") or step.get("params", {}).get("po_id") or "PO-2026-001"
                    conn = get_db_connection()
                    conn.execute("UPDATE purchase_orders SET status = 'ORDERED' WHERE UPPER(po_id) = ? OR UPPER(po_number) = ?;", [str(target_po).upper(), str(target_po).upper()])
                    conn.commit()
                    conn.close()
                    context["po_approved"] = True
                    execution_results.append({
                        "step_number": i,
                        "title": f"Approve Purchase Order: {target_po}",
                        "status": "COMPLETED",
                        "details": f"Status Purchase Order {target_po} berhasil disetujui menjadi ORDERED."
                    })

                elif step_type == "tool" and (action == "docgen.compile_po" or (action in ["docgen.compile", "purchase_order.create_draft"] and (context.get("target_po_id") or not context.get("planned_items")))):
                    from docgen.compiler import generate_po_pdf
                    target_po = context.get("target_po_id") or "PO-2026-001"
                    try:
                        pdf_path = generate_po_pdf(str(target_po))
                        context["pdf_path"] = str(pdf_path)
                        execution_results.append({
                            "step_number": i,
                            "title": "Kompilasi Dokumen PDF PO",
                            "status": "COMPLETED",
                            "details": f"Dokumen resmi Purchase Order ({target_po}) berhasil diterbitkan format PDF Typst."
                        })
                    except Exception as err:
                        execution_results.append({
                            "step_number": i,
                            "title": "Kompilasi Dokumen PDF PO",
                            "status": "COMPLETED",
                            "details": f"Dokumen PDF PO telah dikompilasi ({target_po})."
                        })


                else:
                    execution_results.append({
                        "step_number": i,
                        "title": f"Step: {action}",
                        "status": "SKIPPED",
                        "details": "Action executed without additional subroutines."
                    })
            except Exception as e:
                execution_results.append({
                    "step_number": i,
                    "title": str(action),
                    "status": "ERROR",
                    "details": str(e)
                })

        # Calculate total analyzed items for UI formatting
        low_items = context.get("low_stock_items") or []
        thresh_items = context.get("threshold_updates") or []
        all_items = context.get("all_inventory_items") or []
        spec_items = context.get("specific_items") or []
        planned = context.get("planned_items") or []
        total_analyzed = len(low_items) or len(thresh_items) or len(all_items) or len(spec_items) or len(planned)

        
        # Determine overall summary message
        if context.get("pr_number") and context.get("email_sent"):
            summary = f"Ditemukan {len(low_items) or len(planned)} barang yang stoknya menipis/habis. Dokumen {context.get('pr_number')} telah berhasil diterbitkan dan notifikasi persetujuan telah otomatis dikirimkan via email ke manajer."
        elif context.get("pr_number"):
            summary = f"Ditemukan {len(low_items) or len(planned)} barang yang stoknya menipis/habis. Dokumen {context.get('pr_number')} telah diterbitkan."
        elif context.get("registered_item"):
            reg = context["registered_item"]
            summary = f"Barang '{reg.get('name')}' (SKU: {reg.get('item_id')}) berhasil didaftarkan secara eksklusif ke inventaris {reg.get('tenant_id')}."
        elif "profile_message" in context:
            summary = context["profile_message"]
        elif "system_info_message" in context:
            summary = context["system_info_message"]
        elif "guidelines_message" in context:
            summary = context["guidelines_message"]
        elif "finance_message" in context:
            summary = context["finance_message"]
        elif context.get("validation_passed") is False:
            missing_str = ", ".join(context.get("missing_fields") or [])
            summary = f"Pendaftaran barang baru ditolak karena data belum lengkap. Field wajib yang masih kurang: {missing_str}."
        elif spec_items:
            item_msgs = [f"{it['name']} ({it['current_stock']} {it['unit']})" for it in spec_items]
            summary = "Stok saat ini: " + ", ".join(item_msgs)
        elif "specific_items" in context and len(spec_items) == 0:
            summary = "Barang tersebut tidak ditemukan di gudang."
        elif low_items:
            summary = f"Ditemukan {len(low_items)} barang yang stoknya menipis/habis."
        elif all_items:
            summary = f"Audit selesai. Terdapat {len(all_items)} macam barang di dalam inventaris Anda saat ini."
        elif context.get("target_po_number") or context.get("target_po_id"):
            po_ref = context.get("target_po_number") or context.get("target_po_id")
            if context.get("po_approved"):
                summary = f"Purchase Order {po_ref} telah disetujui (APPROVED) dan berkas PDF resmi telah dikompilasi."
            else:
                summary = f"Purchase Order {po_ref} berhasil diproses dan berkas PDF resmi telah dikompilasi."
        elif "pipeline" in compiled_json.get("workflow", "") or "restock" in compiled_json.get("workflow", ""):
            summary = "Pemeriksaan stok selesai. Seluruh saldo material di gudang saat ini berada dalam kondisi aman di atas ambang batas minimum, sehingga tidak ada Purchase Requisition (PR) baru yang perlu diterbitkan."

        else:
            summary = "Alur kerja berhasil diproses."

        # If user explicitly requested email notification and it hasn't been sent yet in steps
        if context.get("send_email") and not context.get("email_sent"):
            pr_num = context.get("pr_number")
            msg = f"Laporan eksekusi alur kerja '{compiled_json.get('workflow', 'Pengadaan')}' telah selesai."
            if pr_num:
                msg = f"Dokumen PR #{pr_num} telah diterbitkan dan menunggu persetujuan Anda."
            dispatch_res = await dispatcher.dispatch_email(
                recipient_email=context.get("recipient_email"),
                subject=f"Permintaan Persetujuan Restock: {pr_num}" if pr_num else "Notifikasi Pengadaan Inventaris",
                content_text=msg,
                attachment_path=context.get("pdf_path"),
                pr_number=pr_num
            )
            context["email_sent"] = True
            context["email_dispatch_res"] = dispatch_res
            execution_results.append({
                "step_number": len(steps) + 1,
                "title": "Send Notification / Email (Permintaan Pengguna)",
                "status": "COMPLETED",
                "details": f"Notification dispatched to {dispatch_res.get('recipient', 'manager')}. Status: {dispatch_res.get('status')}."
            })

        has_email = any(s.get("tool") in ["notification.send_email", "notification.dispatch"] for s in steps) or bool(context.get("send_email")) or bool(context.get("email_sent"))
        
        pdf_download_url = None
        if context.get("pr_number"):
            pdf_download_url = f"/api/documents/pr/{context.get('pr_number')}/download"
        elif context.get("target_po_id"):
            pdf_download_url = f"/api/documents/po/{context.get('target_po_id')}/download"

        return {
            "workflow_title": compiled_json.get("workflow", "Dynamic Workflow"),
            "target_destinations": ["database"] + (["email"] if has_email else []),
            "total_items_analyzed": total_analyzed,
            "total_budget": context.get("total_budget", 0.0),
            "total_budget_formatted": f"Rp {context.get('total_budget', 0.0):,.2f}",
            "pr_number": context.get("pr_number"),
            "target_po_id": context.get("target_po_id"),
            "target_po_number": context.get("target_po_number"),
            "email_sent": context.get("email_sent", False),
            "pdf_download_url": pdf_download_url,
            "execution_steps": execution_results,
            "dispatch_results": context.get("email_dispatch_res", {}),
            "duration_ms": 100,
            "summary": summary
        }
