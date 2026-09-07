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
    
    # 2. Show 3 Real Heterogeneous Tenant Tables
    print("\n" + "-" * 90)
    print("3 SKEMA REAL-WORLD HETEROGEN (Multi-Tenant):")
    print("-" * 90)
    try:
        cnt_a = conn.execute("SELECT COUNT(*) FROM mfg_electronics_inventory;").fetchone()[0]
        crit_a = conn.execute("SELECT COUNT(*) FROM mfg_electronics_inventory WHERE Stock_Quantity <= Min_Safety_Stock;").fetchone()[0]
        print(f"1. User A (TENANT_A - Electronics Manufacturing): {cnt_a} SKU ({crit_a} Kritis)")
        df_a = conn.execute("SELECT Part_Number, Component_Name, Stock_Quantity, Min_Safety_Stock FROM mfg_electronics_inventory LIMIT 3;").df()
        print(df_a.to_string(index=False))
    except Exception as e:
        print(f"Error loading User A table: {e}")

    try:
        cnt_b = conn.execute("SELECT COUNT(*) FROM pharma_fmcg_inventory;").fetchone()[0]
        crit_b = conn.execute("SELECT COUNT(*) FROM pharma_fmcg_inventory WHERE Shortage_Flag = 1 OR Closing_Stock <= 150;").fetchone()[0]
        print(f"\n2. User B (TENANT_B - Pharma & FMCG WMS): {cnt_b} SKU ({crit_b} Kritis)")
        df_b = conn.execute("SELECT Drug_Name, Brand_Name, Closing_Stock, Shortage_Flag FROM pharma_fmcg_inventory LIMIT 3;").df()
        print(df_b.to_string(index=False))
    except Exception as e:
        print(f"Error loading User B table: {e}")

    try:
        cnt_c = conn.execute("SELECT COUNT(*) FROM fleet_maintenance_parts;").fetchone()[0]
        crit_c = conn.execute("SELECT COUNT(*) FROM fleet_maintenance_parts WHERE Stock_On_Shelf <= Critical_Threshold;").fetchone()[0]
        print(f"\n3. User C (TENANT_C - Fleet Logistics & Heavy Equipment): {cnt_c} SKU ({crit_c} Kritis)")
        df_c = conn.execute("SELECT Vehicle_Model, Invoice_Line_Text, Stock_On_Shelf, Critical_Threshold FROM fleet_maintenance_parts LIMIT 3;").df()
        print(df_c.to_string(index=False))
    except Exception as e:
        print(f"Error loading User C table: {e}")

    # 3. Show Orders summary
    print("\n" + "-" * 90)
    try:
        cnt_orders = conn.execute("SELECT COUNT(*) FROM orders;").fetchone()[0]
        print(f"TABEL 'orders' (Total: {cnt_orders} order lines):")
        df_orders = conn.execute("SELECT order_id, pr_number, item_id, quantity, total_price, status, tenant_id FROM orders ORDER BY created_at DESC LIMIT 5;").df()
        print(df_orders.to_string(index=False))
    except Exception as e:
        print(f"Orders table error: {e}")
    print("=" * 90 + "\n")
    
    conn.close()

if __name__ == "__main__":
    view_database()
