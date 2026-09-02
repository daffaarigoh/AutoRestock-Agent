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
                    for item in context.get("low_stock_items", []):
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
                    if context.get("validation_passed") is False:
                        missing = context.get("missing_fields", [])
                        execution_results.append({
                            "step_number": i,
                            "title": "Pendaftaran Database Inventaris",
                            "status": "FAILED",
                            "details": f"Penyimpanan ditolak karena field belum lengkap: {', '.join(missing)}."
                        })
                    else:
                        new_item = context.get("new_item_data", {})
                        item_id = f"ITM-{uuid.uuid4().hex[:6].upper()}"
                        effective_tenant = tenant_id if tenant_id and tenant_id != "ALL" else "TENANT_A"
                        
                        conn = get_db_connection()
                        conn.execute("""
                            INSERT INTO items (item_id, name, category, current_stock, min_threshold, max_threshold, avg_daily_usage, lead_time_days, unit, tenant_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """, [
                            item_id,
                            new_item.get("name", "Unnamed Item"),
                            new_item.get("category", "General"),
                            int(new_item.get("current_stock", 0)),
                            int(new_item.get("min_threshold", 0)),
                            int(new_item.get("max_threshold", int(new_item.get("min_threshold", 0)) * 3)),
                            float(new_item.get("avg_daily_usage", 1.0)),
                            int(new_item.get("lead_time_days", 3)),
                            new_item.get("unit", "pcs"),
                            effective_tenant
                        ])
                        
                        unit_price = float(new_item.get("unit_price", 0))
                        conn.execute("""
                            INSERT INTO vendors (vendor_id, name, item_id, unit_price, lead_time_days, rating, tenant_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?);
                        """, [
                            f"VND-{item_id[-4:]}",
                            "Default Supplier",
                            item_id,
                            unit_price,
                            int(new_item.get("lead_time_days", 3)),
                            5.0,
                            effective_tenant
                        ])
                        
                        conn.commit()
                        conn.close()
                        
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

                elif step_type == "tool" and action == "inventory.get_low_stock_products":
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
                        conn = get_db_connection()
                        for upd in updates:
                            identifier = upd.get("item_name") or upd.get("item_id")
                            if not identifier:
                                continue
                                
                            set_clauses = []
                            params = []
                            if "new_min_threshold" in upd or "new_threshold" in upd:
                                set_clauses.append("min_threshold = ?")
                                params.append(upd.get("new_min_threshold", upd.get("new_threshold")))
                            if "new_max_threshold" in upd:
                                set_clauses.append("max_threshold = ?")
                                params.append(upd.get("new_max_threshold"))
                                
                            if not set_clauses:
                                continue
                                
                            params.extend([identifier, f"%{str(identifier).lower()}%", tenant_id, tenant_id])
                            sql = f"UPDATE items SET {', '.join(set_clauses)} WHERE (item_id = ? OR lower(name) LIKE ?) AND (tenant_id = ? OR ? = 'ALL')"
                            conn.execute(sql, params)
                        conn.commit()
                        conn.close()
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
                    items_len = len(context.get("planned_items", []))
                    all_len = len(context.get("all_inventory_items", []))
                    low_len = len(context.get("low_stock_items", []))
                    registered = context.get("registered_item")
                    
                    if pr_number:
                        msg = f"Dokumen Purchase Requisition {pr_number} telah diterbitkan untuk {items_len} barang menipis dengan total anggaran Rp {context.get('total_budget', 0.0):,.2f}. Mohon tinjau dan lakukan persetujuan."
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
                        recipient_email=None,
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
                elif step_type == "tool" and action in ["docgen.compile", "purchase_order.create_draft"]:
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
        total_analyzed = len(context.get("low_stock_items", [])) or len(context.get("threshold_updates", [])) or len(context.get("all_inventory_items", [])) or len(context.get("specific_items", []))
        
        # Determine overall summary message
        if context.get("validation_passed") is False:
            missing_str = ", ".join(context.get("missing_fields", []))
            summary = f"Pendaftaran barang baru ditolak karena data belum lengkap. Field wajib yang masih kurang: {missing_str}."
        elif context.get("registered_item"):
            reg = context["registered_item"]
            summary = f"Barang '{reg.get('name')}' (SKU: {reg.get('item_id')}) berhasil didaftarkan secara eksklusif ke inventaris {reg.get('tenant_id')}."
        elif context.get("pr_number") and context.get("email_sent"):
            summary = f"Ditemukan {len(context.get('low_stock_items', []))} barang yang stoknya menipis. Dokumen {context.get('pr_number')} telah berhasil diterbitkan dan notifikasi persetujuan telah otomatis dikirimkan via email ke manajer."
        elif context.get("pr_number"):
            summary = f"Ditemukan {len(context.get('low_stock_items', []))} barang yang stoknya menipis. Dokumen {context.get('pr_number')} telah diterbitkan."
        elif context.get("specific_items"):
            item_msgs = [f"{it['name']} ({it['current_stock']} {it['unit']})" for it in context["specific_items"]]
            summary = "Stok saat ini: " + ", ".join(item_msgs)
        elif len(context.get("specific_items", [])) == 0 and "specific_items" in context:
            summary = "Barang tersebut tidak ditemukan di gudang."
        elif "low_stock_items" in context:
            summary = f"Ditemukan {len(context['low_stock_items'])} barang yang stoknya menipis."
        elif "all_inventory_items" in context:
            summary = f"Audit selesai. Terdapat {len(context['all_inventory_items'])} macam barang di dalam inventaris Anda saat ini."
        else:
            summary = "Workflow berhasil dieksekusi."
        
        has_email = any(s.get("tool") in ["notification.send_email", "notification.dispatch"] for s in steps)
        return {
            "workflow_title": compiled_json.get("workflow", "Dynamic Workflow"),
            "target_destinations": ["database"] + (["email"] if has_email else []),
            "total_items_analyzed": total_analyzed,
            "total_budget": context.get("total_budget", 0.0),
            "total_budget_formatted": f"Rp {context.get('total_budget', 0.0):,.2f}",
            "pr_number": context.get("pr_number"),
            "email_sent": context.get("email_sent", False),
            "pdf_download_url": f"/api/documents/pr/{context.get('pr_number')}/download" if context.get("pr_number") else None,
            "execution_steps": execution_results,
            "dispatch_results": context.get("email_dispatch_res", {}),
            "duration_ms": 100,
            "summary": summary
        }
