import math
from typing import Any

from database.db import get_db_connection


def calculate_safety_stock(min_threshold: int) -> int:
    """
    Legacy function, now just returns min_threshold.
    """
    return min_threshold


def calculate_reorder_quantity(
    current_stock: int,
    max_threshold: int
) -> int:
    """
    Formula: Reorder Qty = Max Threshold - Current Stock
    """
    reorder_qty = max_threshold - current_stock
    return max(reorder_qty, 1)


def get_low_stock_items(tenant_id: str = "ALL") -> list[dict[str, Any]]:
    """
    Queries DuckDB to retrieve items with stock below the minimum threshold,
    filtered by tenant_id.
    """
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                item_id, name, category, current_stock, min_threshold, max_threshold, avg_daily_usage, lead_time_days, unit
            FROM items
            WHERE current_stock <= min_threshold
            AND (tenant_id = ? OR ? = 'ALL')
            ORDER BY (min_threshold - current_stock) DESC;
        """
        rows = conn.execute(query, [tenant_id, tenant_id]).fetchall()
        columns = [desc[0] for desc in conn.description]
        
        low_stock_items = []
        for row in rows:
            item_dict = dict(zip(columns, row))
            stock = int(item_dict["current_stock"])
            min_threshold = int(item_dict["min_threshold"])
            max_threshold = int(item_dict["max_threshold"])
            
            safety_stock = calculate_safety_stock(min_threshold)
            reorder_qty = calculate_reorder_quantity(stock, max_threshold)
            
            item_dict["safety_stock"] = safety_stock
            item_dict["reorder_qty"] = reorder_qty
            low_stock_items.append(item_dict)
            
        return low_stock_items
    finally:
        conn.close()

def get_specific_item_stock(item_name: str, tenant_id: str = "ALL") -> list[dict[str, Any]]:
    """
    Queries DuckDB to retrieve items matching the item_name.
    """
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                item_id, name, category, current_stock, min_threshold, max_threshold, avg_daily_usage, lead_time_days, unit
            FROM items
            WHERE lower(name) LIKE ? AND (tenant_id = ? OR ? = 'ALL')
        """
        rows = conn.execute(query, [f"%{item_name.lower()}%", tenant_id, tenant_id]).fetchall()
        columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, r)) for r in rows]
    finally:
        conn.close()


def get_best_vendors(item_id: str, tenant_id: str = "ALL") -> dict[str, Any] | None:
    """
    Queries DuckDB vendors table to find the best vendor for a given item_id.
    """
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT vendor_id, name, item_id, unit_price, lead_time_days, rating
            FROM vendors
            WHERE item_id = ? AND (tenant_id = ? OR ? = 'ALL')
            ORDER BY unit_price ASC, lead_time_days ASC, rating DESC
            LIMIT 1;
        """
        result = conn.execute(query, [item_id, tenant_id, tenant_id]).fetchone()
        if not result:
            return None
        
        columns = [desc[0] for desc in conn.description]
        return dict(zip(columns, result))
    finally:
        conn.close()


def get_all_vendors_for_item(item_id: str, tenant_id: str = "ALL") -> list[dict[str, Any]]:
    """Get all available vendors offering a specific item."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT vendor_id, name, item_id, unit_price, lead_time_days, rating
            FROM vendors
            WHERE item_id = ? AND (tenant_id = ? OR ? = 'ALL')
            ORDER BY unit_price ASC, lead_time_days ASC;
        """
        rows = conn.execute(query, [item_id, tenant_id, tenant_id]).fetchall()
        columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, r)) for r in rows]
    finally:
        conn.close()


def get_all_inventory_items(tenant_id: str = "ALL") -> list[dict[str, Any]]:
    """Retrieve all inventory items from DuckDB, filtered by tenant_id."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                i.item_id, i.name, i.category, i.current_stock, i.min_threshold, i.max_threshold,
                i.avg_daily_usage, i.lead_time_days, i.unit, i.tenant_id,
                COALESCE(MIN(v.unit_price), 0.0) AS unit_price
            FROM items i
            LEFT JOIN vendors v ON i.item_id = v.item_id
            WHERE i.tenant_id = ? OR ? = 'ALL'
            GROUP BY i.item_id, i.name, i.category, i.current_stock, i.min_threshold, i.max_threshold,
                     i.avg_daily_usage, i.lead_time_days, i.unit, i.tenant_id
            ORDER BY i.item_id ASC;
        """
        rows = conn.execute(query, [tenant_id, tenant_id]).fetchall()
        columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, r)) for r in rows]
    finally:
        conn.close()
