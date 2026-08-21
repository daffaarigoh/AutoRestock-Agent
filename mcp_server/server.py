"""
Official FastMCP Server for AutoRestock-V2
Exposes inventory, procurement, and warehouse tools over Model Context Protocol (MCP).
"""

from mcp.server.fastmcp import FastMCP
from typing import Optional, List, Dict, Any
from mcp_server.tools import (
    query_inventory_tool,
    update_stock_tool,
    update_threshold_tool,
    add_item_tool,
    delete_item_tool,
    manage_category_tool,
    approve_prs_tool,
    calculate_financials_tool,
    dispatch_notification_tool
)

mcp = FastMCP("AutoRestock-V2")


@mcp.tool()
async def query_inventory(category: Optional[str] = None, search: Optional[str] = None, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query inventory items by category, search query, or status ('low', 'out', 'normal')."""
    return await query_inventory_tool(category=category, search=search, status_filter=status_filter)


@mcp.tool()
async def update_stock(sku: str, change_amount: int, reason: str = "Manual stock update via AI Tool") -> Dict[str, Any]:
    """Update stock quantity balance for a specific product SKU in the warehouse database."""
    return await update_stock_tool(sku=sku, change_amount=change_amount, reason=reason)


@mcp.tool()
async def update_threshold(sku: str, min_stock: Optional[int] = None, max_stock: Optional[int] = None) -> Dict[str, Any]:
    """Update minimum and maximum stock threshold boundaries for a product."""
    return await update_threshold_tool(sku=sku, min_stock=min_stock, max_stock=max_stock)


@mcp.tool()
async def add_item(
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
    """Register and save a new product into the catalog database."""
    return await add_item_tool(
        name=name, category=category, unit_price=unit_price,
        current_stock=current_stock, min_stock=min_stock, max_stock=max_stock,
        unit=unit, supplier_name=supplier_name, sku=sku
    )


@mcp.tool()
async def delete_item(sku: str) -> Dict[str, Any]:
    """Delete a product item from the warehouse catalog."""
    return await delete_item_tool(sku=sku)


@mcp.tool()
async def manage_category(action: str, category_name: str) -> Dict[str, Any]:
    """Add or delete a product category in the database (action: 'add' or 'delete')."""
    return await manage_category_tool(action=action, category_name=category_name)


@mcp.tool()
async def approve_prs(
    filter_status: str = "pending_approval",
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    pr_number: Optional[str] = None
) -> Dict[str, Any]:
    """Approve Purchase Requisitions (batch or targeted by ID/amount) and replenish stock."""
    return await approve_prs_tool(
        filter_status=filter_status, min_amount=min_amount,
        max_amount=max_amount, pr_number=pr_number
    )


@mcp.tool()
async def calculate_financials(target: str = "prs") -> Dict[str, Any]:
    """Calculate total financial metrics: PR cost liabilities, pending amounts, and inventory asset valuation."""
    return await calculate_financials_tool(target=target)


@mcp.tool()
async def dispatch_notification(channel: str, recipient: str, message: str, subject: str = "AutoRestock Alert") -> Dict[str, Any]:
    """Dispatch email, Telegram, or WhatsApp notification through n8n automation."""
    return await dispatch_notification_tool(channel=channel, recipient=recipient, message=message, subject=subject)


if __name__ == "__main__":
    mcp.run(transport="stdio")
