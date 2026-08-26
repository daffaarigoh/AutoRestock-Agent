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
    Executes a compiled JSON workflow sequentially.
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
                if step_type == "tool" and action == "inventory.get_low_stock_products":
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
                    
                elif step_type == "tool" and action == "purchase_order.create_draft":
                    planned_items = context.get("planned_items", [])
                    if not planned_items:
                        execution_results.append({
                            "step_number": i,
                            "title": "Create PR Draft",
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
                    pdf_path = generate_pr_pdf(pr_doc)
                    context["pr_number"] = pr_number
                    context["pdf_path"] = str(pdf_path)
                    
                    # Sync DB
                    conn = get_db_connection()
                    for it in planned_items:
                        order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
                        conn.execute("INSERT INTO orders (order_id, pr_number, item_id, vendor_id, quantity, unit_price, total_price, status, tenant_id) VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?);", 
                                     [order_id, pr_number, it.item_id, it.vendor_id, it.reorder_qty, it.unit_price, it.total_price, tenant_id])
                    
                    # Sync to PR_STORE for web dashboard preview
                    from api.routers.approval_routes import PR_STORE
                    from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
                    clean_filename = f"{pr_number.replace('-', '_')}.pdf"
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
                        total_budget=context["total_budget"],
                        auditor_status="PASSED",
                        auditor_notes="Audit passed.",
                        pdf_path=f"/storage/documents/{clean_filename}",
                        status="PENDING",
                        tenant_id=tenant_id
                    )

                    conn.close()
                    
                    execution_results.append({
                        "step_number": i,
                        "title": "Create PR Draft",
                        "status": "COMPLETED",
                        "details": f"Draft {pr_number} created and saved to orders."
                    })
                    
                elif step_type == "tool" and action == "notification.send_email":
                    if not context.get("send_email", False):
                        execution_results.append({
                            "step_number": i,
                            "title": "Send Email Notification",
                            "status": "SKIPPED",
                            "details": "User did not explicitly request an email notification."
                        })
                        continue

                    pr_number = context.get("pr_number")
                    items_len = len(context.get("planned_items", []))
                    all_len = len(context.get("all_inventory_items", []))
                    low_len = len(context.get("low_stock_items", []))
                    
                    if items_len > 0:
                        msg = f"Workflow Auto Restock dieksekusi. Memproses {items_len} item PR."
                    elif low_len > 0:
                        msg = f"Laporan Stok Kritis: Ditemukan {low_len} barang menipis di bawah ambang batas minimum."
                    elif all_len > 0:
                        msg = f"Audit Seluruh Gudang: Total {all_len} barang saat ini tercatat di sistem inventaris."
                    else:
                        msg = "Workflow berhasil dijalankan (Tanpa data item spesifik)."
                        
                    await dispatcher.dispatch_email(
                        recipient_email=None,
                        subject="Laporan Workflow: " + compiled_json.get("workflow", "Sistem"),
                        content_text=msg,
                        attachment_path=context.get("pdf_path"),
                        pr_number=pr_number
                    )
                    execution_results.append({
                        "step_number": i,
                        "title": "Send Email Notification",
                        "status": "COMPLETED",
                        "details": "Notification dispatched."
                    })

                elif step_type == "tool" and action == "inventory.update_threshold":
                    # Update threshold logic based on context (from intent)
                    updates = context.get("threshold_updates", [])
                    if updates:
                        conn = get_db_connection()
                        for upd in updates:
                            identifier = upd.get("item_name") or upd.get("item_id")
                            if not identifier:
                                continue
                            conn.execute("""
                                UPDATE items 
                                SET min_threshold = ? 
                                WHERE (item_id = ? OR lower(name) LIKE ?) AND (tenant_id = ? OR ? = 'ALL')
                            """, [upd["new_threshold"], identifier, f"%{str(identifier).lower()}%", tenant_id, tenant_id])
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
                else:
                    execution_results.append({
                        "step_number": i,
                        "title": f"Unknown Step: {action}",
                        "status": "SKIPPED",
                        "details": "Action not mapped in execution engine."
                    })
            except Exception as e:
                execution_results.append({
                    "step_number": i,
                    "title": action,
                    "status": "ERROR",
                    "details": str(e)
                })

        # Calculate total analyzed items for UI formatting
        total_analyzed = len(context.get("low_stock_items", [])) or len(context.get("threshold_updates", [])) or len(context.get("all_inventory_items", [])) or len(context.get("specific_items", []))
        
        summary = "Workflow executed successfully."
        if context.get("specific_items"):
            item_msgs = [f"{it['name']} ({it['current_stock']} {it['unit']})" for it in context["specific_items"]]
            summary = "Stok saat ini: " + ", ".join(item_msgs)
        elif len(context.get("specific_items", [])) == 0 and "specific_items" in context:
            summary = "Barang tersebut tidak ditemukan di gudang."
        elif context.get("low_stock_items"):
            summary = f"Ditemukan {len(context['low_stock_items'])} barang yang stoknya menipis."
        
        return {
            "workflow_title": compiled_json.get("workflow", "Dynamic Workflow"),
            "target_destinations": ["database"] + (["email"] if "notification.send_email" in str(steps) else []),
            "total_items_analyzed": total_analyzed,
            "total_budget": context.get("total_budget", 0.0),
            "total_budget_formatted": f"Rp {context.get('total_budget', 0.0):,.2f}",
            "pr_number": context.get("pr_number"),
            "pdf_download_url": f"/api/documents/pr/{context.get('pr_number')}/download" if context.get("pr_number") else None,
            "execution_steps": execution_results,
            "dispatch_results": {},
            "duration_ms": 100, # Mock duration for now
            "summary": summary
        }
