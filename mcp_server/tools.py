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
    Queries DuckDB to retrieve items with stock below the minimum threshold,
    and computes dynamic safety stock and reorder quantity using Python formulas.
    """
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                item_id,
                name,
                category,
                current_stock,
                min_threshold,
                avg_daily_usage,
                lead_time_days,
                unit
            FROM items
            WHERE current_stock < min_threshold
            ORDER BY (min_threshold - current_stock) DESC;
        """
        rows = conn.execute(query).fetchall()
        columns = [desc[0] for desc in conn.description]
        
        low_stock_items = []
        for row in rows:
            item_dict = dict(zip(columns, row))
            lead_time = int(item_dict["lead_time_days"])
            daily_usage = float(item_dict["avg_daily_usage"])
            stock = int(item_dict["current_stock"])
            
            # Python formula calculation
            safety_stock = calculate_safety_stock(lead_time, daily_usage)
            reorder_qty = calculate_reorder_quantity(lead_time, daily_usage, stock, safety_stock)
            
            item_dict["safety_stock"] = safety_stock
            item_dict["reorder_qty"] = reorder_qty
            low_stock_items.append(item_dict)
            
        return low_stock_items
    finally:
        conn.close()


def get_best_vendors(item_id: str) -> Optional[Dict[str, Any]]:
    """
    Queries DuckDB vendors table to find the best vendor for a given item_id.
    Prioritizes: Lowest unit_price ASC, fastest lead_time_days ASC, highest rating DESC.
    """
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                vendor_id,
                name,
                item_id,
                unit_price,
                lead_time_days,
                rating
            FROM vendors
            WHERE item_id = ?
            ORDER BY unit_price ASC, lead_time_days ASC, rating DESC
            LIMIT 1;
        """
        result = conn.execute(query, [item_id]).fetchone()
        if not result:
            return None
        
        columns = [desc[0] for desc in conn.description]
        return dict(zip(columns, result))
    finally:
        conn.close()


def get_all_vendors_for_item(item_id: str) -> List[Dict[str, Any]]:
    """Get all available vendors offering a specific item."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                vendor_id,
                name,
                item_id,
                unit_price,
                lead_time_days,
                rating
            FROM vendors
            WHERE item_id = ?
            ORDER BY unit_price ASC, lead_time_days ASC;
        """
        rows = conn.execute(query, [item_id]).fetchall()
        columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, r)) for r in rows]
    finally:
        conn.close()


def get_all_inventory_items() -> List[Dict[str, Any]]:
    """Retrieve all inventory items from DuckDB."""
    conn = get_db_connection(read_only=True)
    try:
        query = """
            SELECT 
                item_id,
                name,
                category,
                current_stock,
                min_threshold,
                avg_daily_usage,
                lead_time_days,
                unit
            FROM items
            ORDER BY item_id ASC;
        """
        rows = conn.execute(query).fetchall()
        columns = [desc[0] for desc in conn.description]
        return [dict(zip(columns, r)) for r in rows]
    finally:
        conn.close()
