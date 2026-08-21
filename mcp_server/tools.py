"""
Model Context Protocol (MCP) Server Tools Module
Exposes official, typed inventory & procurement tools for AI Agents and MCP Clients.
"""

from typing import Dict, Any, List, Optional
from database.db import db
from core.schemas import PRStatus, InventoryItem
from core.observability import log_agent_step
from docgen.pdf_generator import pdf_generator
from datetime import datetime


async def query_inventory_tool(category: Optional[str] = None, search: Optional[str] = None, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Tool: Returns inventory catalog items filtered by category, search query, or stock status ('low', 'out', 'normal').
    """
    items = db.get_items(category=category, search=search)
    results = []
    for it in items:
        status = "normal"
        if it.current_stock <= 0:
            status = "out"
        elif it.current_stock <= it.min_stock:
            status = "low"
            
        if status_filter and status_filter != status:
            continue
            
        results.append({
            "sku": it.sku,
            "name": it.name,
            "category": it.category,
            "current_stock": it.current_stock,
            "min_stock": it.min_stock,
            "max_stock": it.max_stock,
            "unit": it.unit,
            "unit_price": it.unit_price,
            "supplier_name": it.supplier_name,
            "status": status
        })
    return results


async def update_stock_tool(sku: str, change_amount: int, reason: str = "Manual stock update via AI Tool") -> Dict[str, Any]:
    """
    Tool: Updates the stock balance (positive to add, negative to deduct) for a specific SKU in the database.
    """
    item = db.update_stock(
        sku=sku,
        change=change_amount,
        transaction_type="ai_tool_adjustment",
        notes=reason
    )
    if not item:
        return {"status": "error", "message": f"Product with SKU '{sku}' was not found in catalog."}
    return {
        "status": "success",
        "sku": item.sku,
        "name": item.name,
        "new_stock": item.current_stock,
        "unit": item.unit,
        "message": f"Stock for '{item.name}' successfully updated to {item.current_stock} {item.unit}."
    }


async def update_threshold_tool(sku: str, min_stock: Optional[int] = None, max_stock: Optional[int] = None) -> Dict[str, Any]:
    """
    Tool: Updates minimum and/or maximum stock threshold boundaries for a specific product SKU.
    """
    item = db.get_item_by_sku(sku)
    if not item:
        # Try searching by product name
        matched = db.get_items(search=sku)
        if matched:
            item = matched[0]
            sku = item.sku
        else:
            return {"status": "error", "message": f"Product '{sku}' was not found."}

    desc = []
    if min_stock is not None:
        item.min_stock = min_stock
        desc.append(f"Min Stock = {min_stock}")
    if max_stock is not None:
        item.max_stock = max_stock
        desc.append(f"Max Stock = {max_stock}")

    db.upsert_item(item)
    return {
        "status": "success",
        "sku": item.sku,
        "name": item.name,
        "min_stock": item.min_stock,
        "max_stock": item.max_stock,
        "message": f"Threshold for '{item.name}' updated ({', '.join(desc)})."
    }


async def add_item_tool(
    name: str,
    category: str,
    unit_price: float,
    current_stock: int = 0,
    min_stock: int = 10,
    max_stock: int = 50,
    unit: str = "pcs",
    supplier_name: str = "Supplier Rekanan",
    sku: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tool: Registers and saves a new product item into the warehouse database.
    """
    if not sku:
        prefix = category.upper()[:4].replace(" ", "")
        sku = f"{prefix}-{name.upper()[:6].replace(' ', '')}-{len(db.get_items()) + 1:02d}"

    new_item = InventoryItem(
        sku=sku,
        name=name,
        category=category,
        current_stock=current_stock,
        min_stock=min_stock,
        max_stock=max_stock,
        unit=unit,
        unit_price=unit_price,
        supplier_id="SUP-001",
        supplier_name=supplier_name,
        location_bin="RAK-A-01"
    )
    db.upsert_item(new_item)
    db.add_category(category)
    return {
        "status": "success",
        "item": new_item.model_dump(),
        "message": f"Product '{new_item.name}' ({new_item.sku}) successfully registered in database."
    }


async def delete_item_tool(sku: str) -> Dict[str, Any]:
    """
    Tool: Deletes an existing product item from the catalog database.
    """
    deleted = db.delete_item(sku)
    if not deleted:
        return {"status": "error", "message": f"Product with SKU '{sku}' not found or could not be deleted."}
    return {"status": "success", "sku": sku, "message": f"Product {sku} successfully deleted from database."}


async def manage_category_tool(action: str, category_name: str) -> Dict[str, Any]:
    """
    Tool: Adds or removes a product category in the database. action: 'add' or 'delete'.
    """
    if action.lower() in ["add", "tambah"]:
        res = db.add_category(category_name)
        return {"status": "success", "action": "add", "category": res, "message": f"Category '{res}' added."}
    else:
        success = db.delete_category(category_name)
        return {
            "status": "success" if success else "error",
            "action": "delete",
            "category": category_name,
            "message": f"Category '{category_name}' {'deleted' if success else 'not found'}."
        }


async def approve_prs_tool(
    filter_status: str = "pending_approval",
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    pr_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Tool: Approves one or multiple Purchase Requisitions, updates SQLite status to 'APPROVED', and replenishes warehouse stock.
    """
    if pr_number:
        target_prs = [db.get_pr_by_number(pr_number)] if db.get_pr_by_number(pr_number) else []
    else:
        all_prs = db.get_purchase_requisitions(status=filter_status)
        target_prs = []
        for p in all_prs:
            if min_amount is not None and p.grand_total < min_amount:
                continue
            if max_amount is not None and p.grand_total > max_amount:
                continue
            target_prs.append(p)

    approved = []
    total_val = 0.0
    for p in target_prs:
        up = db.update_pr_status(
            pr_number=p.pr_number,
            status=PRStatus.APPROVED,
            approver_name="Manager (AI Tool Execution)",
            notes="Approved via MCP Tool"
        )
        if up:
            for pit in up.items:
                db.update_stock(
                    sku=pit.sku,
                    change=pit.quantity,
                    transaction_type="mcp_approval_replenishment",
                    ref_doc=up.pr_number,
                    notes=f"Stock replenished via PR {up.pr_number}"
                )
            approved.append(up.model_dump())
            total_val += up.grand_total

    return {
        "status": "success",
        "approved_count": len(approved),
        "total_approved_idr": total_val,
        "approved_prs": approved,
        "message": f"Successfully approved {len(approved)} PR(s) totaling Rp {total_val:,.0f}."
    }


async def calculate_financials_tool(target: str = "prs") -> Dict[str, Any]:
    """
    Tool: Computes comprehensive financial totals: total PR liabilities, pending amounts, approved PO amounts, and total warehouse stock valuation.
    """
    all_prs = db.get_purchase_requisitions()
    pending_prs = [p for p in all_prs if p.status.value == "pending_approval"]
    approved_prs = [p for p in all_prs if p.status.value == "approved"]
    stats = db.get_dashboard_stats()

    total_all = sum(p.grand_total for p in all_prs)
    total_pending = sum(p.grand_total for p in pending_prs)
    total_approved = sum(p.grand_total for p in approved_prs)

    return {
        "status": "success",
        "total_pr_count": len(all_prs),
        "total_pr_value_idr": total_all,
        "pending_pr_count": len(pending_prs),
        "pending_pr_value_idr": total_pending,
        "approved_pr_count": len(approved_prs),
        "approved_pr_value_idr": total_approved,
        "inventory_total_value_idr": stats.total_inventory_value_idr,
        "formatted_summary": (
            f"Financial Summary:\n"
            f"• Total PR Liabilities ({len(all_prs)} docs): Rp {total_all:,.0f}\n"
            f"• Pending Approval ({len(pending_prs)} docs): Rp {total_pending:,.0f}\n"
            f"• Approved POs ({len(approved_prs)} docs): Rp {total_approved:,.0f}\n"
            f"• Total Inventory Asset Value: Rp {stats.total_inventory_value_idr:,.0f}"
        )
    }


async def dispatch_notification_tool(channel: str, recipient: str, message: str, subject: str = "AutoRestock Alert") -> Dict[str, Any]:
    """
    Tool: Dispatches an external notification via n8n webhook (channel: 'email', 'telegram', 'whatsapp').
    """
    from core.n8n_client import n8n_client
    res = await n8n_client.dispatch_notification(
        channel=channel,
        recipient=recipient,
        message=message,
        subject=subject
    )
    return res
