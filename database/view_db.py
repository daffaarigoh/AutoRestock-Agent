import sys
from pathlib import Path

# Fix console encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from database.db import get_db_connection


def view_database():
    conn = get_db_connection(read_only=True)
    
    print("=" * 90)
    print("DUCKDB INVENTORY VIEWER")
    print("=" * 90)
    
    # 1. Show Tables
    tables = conn.execute("SHOW TABLES;").df()
    print("\nDAFTAR TABEL:")
    print(tables.to_string(index=False))
    
    # 2. Show Items summary
    print("\n" + "-" * 90)
    print("TABEL 'items' (Total: {} baris)".format(conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]))
    print("-" * 90)
    df_items = conn.execute("SELECT item_id, name, category, current_stock, min_threshold, avg_daily_usage, lead_time_days, unit FROM items LIMIT 10").df()
    print(df_items.to_string(index=False))
    print("... (menampilkan 10 dari 25 barang)")
    
    # 3. Show Vendors summary
    print("\n" + "-" * 90)
    print("TABEL 'vendors' (Total: {} relasi)".format(conn.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]))
    print("-" * 90)
    df_vendors = conn.execute("SELECT vendor_id, name, item_id, unit_price, lead_time_days, rating FROM vendors LIMIT 10").df()
    print(df_vendors.to_string(index=False))
    print("... (menampilkan 10 dari 31 vendor)")
    
    # 4. Critical Stock Alert
    print("\n" + "=" * 90)
    print("BARANG KRITIS PERLU RESTOCK (current_stock < min_threshold):")
    print("=" * 90)
    critical_query = """
        SELECT 
            item_id,
            name,
            current_stock,
            min_threshold,
            (min_threshold - current_stock) AS deficit,
            unit
        FROM items
        WHERE current_stock < min_threshold
        ORDER BY deficit DESC;
    """
    df_critical = conn.execute(critical_query).df()
    print(df_critical.to_string(index=False))
    print("=" * 90 + "\n")
    
    conn.close()

if __name__ == "__main__":
    view_database()
