import math
from typing import List, Dict, Any, Optional
from database.db import get_db_connection


def calculate_safety_stock(lead_time_days: int, avg_daily_usage: float) -> int:
    """
    Formula: Safety Stock = Lead Time * Daily Usage * 1.5
    """
    return int(math.ceil(lead_time_days * avg_daily_usage * 1.5))


def calculate_reorder_quantity(
    lead_time_days: int,
    avg_daily_usage: float,
    current_stock: int,
    safety_stock: Optional[int] = None
) -> int:
    """
    Formula: Reorder Qty = (Daily Usage * Lead Time) + Safety Stock - Current Stock
    """
    if safety_stock is None:
        safety_stock = calculate_safety_stock(lead_time_days, avg_daily_usage)
        
    expected_usage = avg_daily_usage * lead_time_days
    reorder_qty = int(math.ceil(expected_usage + safety_stock - current_stock))
    return max(reorder_qty, 1)


def get_low_stock_items() -> List[Dict[str, Any]]:
    """
    Queries DuckDB to retrieve items with stock at or below the minimum threshold.
    """
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                sku,
                name,
                category,
                current_stock,
                min_stock,
                max_stock,
                safety_stock,
                unit,
                unit_price,
                supplier_id,
                supplier_name,
                lead_time_days
            FROM items
            WHERE current_stock <= min_stock
            ORDER BY (min_stock - current_stock) DESC;
        """
        rows = conn.execute(query).fetchall()
        columns = [desc[0] for desc in conn.description]
        
        low_stock_items = []
        for row in rows:
            item_dict = dict(zip(columns, row))
            lead_time = int(item_dict.get("lead_time_days") or 3)
            stock = int(item_dict.get("current_stock") or 0)
            min_s = int(item_dict.get("min_stock") or 5)
            daily_usage = max(1.0, min_s / max(lead_time, 1))
            
            safety_stock = int(item_dict.get("safety_stock") or calculate_safety_stock(lead_time, daily_usage))
            reorder_qty = calculate_reorder_quantity(lead_time, daily_usage, stock, safety_stock)
            
            item_dict["safety_stock"] = safety_stock
            item_dict["reorder_qty"] = reorder_qty
            low_stock_items.append(item_dict)
            
        return low_stock_items
    finally:
        conn.close()


def get_best_vendors(sku_or_item_id: str) -> Optional[Dict[str, Any]]:
    """
    Queries DuckDB suppliers table or item supplier.
    """
    conn = get_db_connection(read_only=True)
    try:
        # Check supplier for this item in items table
        item_query = "SELECT supplier_id, supplier_name, unit_price FROM items WHERE sku = ?"
        res = conn.execute(item_query, [sku_or_item_id]).fetchone()
        if res:
            sup_id, sup_name, price = res
            return {
                "vendor_id": sup_id or "SUP-001",
                "name": sup_name or "PT Sumber Alfaria Distribusi",
                "unit_price": price or 25000.0,
                "lead_time_days": 3,
                "rating": 4.8
            }
        
        sup_query = "SELECT supplier_id, name, lead_time_days, rating FROM suppliers LIMIT 1;"
        s_res = conn.execute(sup_query).fetchone()
        if s_res:
            cols = [d[0] for d in conn.description]
            return dict(zip(cols, s_res))
        return None
    finally:
        conn.close()


def get_all_vendors_for_item(sku_or_item_id: str) -> List[Dict[str, Any]]:
    """Get suppliers for a specific item."""
    v = get_best_vendors(sku_or_item_id)
    return [v] if v else []


def get_all_inventory_items() -> List[Dict[str, Any]]:
    """Retrieve all inventory items from DuckDB."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                sku,
                name,
                category,
                current_stock,
                min_stock,
                max_stock,
                safety_stock,
                unit,
                unit_price,
                supplier_id,
                supplier_name,
                lead_time_days,
                location_bin,
                status
            FROM items
            ORDER BY sku ASC;
        """
        rows = conn.execute(query).fetchall()
        columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, r)) for r in rows]
    finally:
        conn.close()
