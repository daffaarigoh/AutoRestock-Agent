from database.db import get_db_connection

def apply_low_and_out_of_stock():
    conn = get_db_connection(read_only=False)

    print("Mengupdate stok material usera...")

    # 1. BLT-INV-005 (Baterai Lithium LiFePO4): HABIS TOTAL (0 unit)
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 0, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-005';")
    conn.execute("UPDATE items SET current_stock = 0 WHERE item_id = 'BLT-INV-005';")

    # 2. BLT-INV-004 (ODC 144 Port Outdoor): HABIS TOTAL (0 unit)
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 0, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-004';")
    conn.execute("UPDATE items SET current_stock = 0 WHERE item_id = 'BLT-INV-004';")

    # 3. BLT-INV-023 (Genset Silent Portable 5kVA): HABIS TOTAL (0 unit)
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 0, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-023';")
    conn.execute("UPDATE items SET current_stock = 0 WHERE item_id = 'BLT-INV-023';")

    # 4. BLT-INV-006 (Rectifier Module 48V 50A): MENIPIS KRITIS (Total 2 unit, min: 12)
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 1, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-006' AND warehouse_id IN ('WH-JKT-01', 'WH-BDG-01');")
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 0, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-006' AND warehouse_id NOT IN ('WH-JKT-01', 'WH-BDG-01');")
    conn.execute("UPDATE items SET current_stock = 2 WHERE item_id = 'BLT-INV-006';")

    # 5. BLT-INV-003 (Optical Splice Closure 48 Core): MENIPIS (Total 4 unit, min: 25)
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 2, stock_status = 'LOW_STOCK' WHERE item_id = 'BLT-INV-003' AND warehouse_id = 'WH-JKT-01';")
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 1, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-003' AND warehouse_id = 'WH-BDG-01';")
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 1, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-003' AND warehouse_id = 'WH-JKB-01';")
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 0, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-003' AND warehouse_id NOT IN ('WH-JKT-01', 'WH-BDG-01', 'WH-JKB-01');")
    conn.execute("UPDATE items SET current_stock = 4 WHERE item_id = 'BLT-INV-003';")

    # 6. BLT-INV-001 (Kabel Fiber Optic ADSS 24 Core): MENIPIS (Total 450 meter, min: 2000)
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 150, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-001' AND warehouse_id = 'WH-JKT-01';")
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 150, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-001' AND warehouse_id = 'WH-BDG-01';")
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 150, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-001' AND warehouse_id = 'WH-DPS-01';")
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 0, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-001' AND warehouse_id NOT IN ('WH-JKT-01', 'WH-BDG-01', 'WH-DPS-01');")
    conn.execute("UPDATE items SET current_stock = 450 WHERE item_id = 'BLT-INV-001';")

    # 7. BLT-INV-011 (Inverter Pure Sine Wave 3kVA): HABIS TOTAL (0 unit, min: 10)
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 0, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-011';")
    conn.execute("UPDATE items SET current_stock = 0 WHERE item_id = 'BLT-INV-011';")

    # 8. BLT-INV-021 (Solar Panel Monocrystalline 450Wp): MENIPIS (Total 3 unit, min: 20)
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 2, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-021' AND warehouse_id = 'WH-DPS-01';")
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 1, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-021' AND warehouse_id = 'WH-JKB-01';")
    conn.execute("UPDATE stock_balances SET quantity_on_hand = 0, stock_status = 'CRITICAL' WHERE item_id = 'BLT-INV-021' AND warehouse_id NOT IN ('WH-DPS-01', 'WH-JKB-01');")
    conn.execute("UPDATE items SET current_stock = 3 WHERE item_id = 'BLT-INV-021';")

    conn.commit()

    rows = conn.execute("""
        SELECT 
            i.item_id, 
            i.name, 
            i.current_stock, 
            i.min_threshold, 
            i.unit,
            CASE WHEN i.current_stock = 0 THEN 'HABIS' ELSE 'MENIPIS' END as status
        FROM items i
        WHERE i.current_stock <= i.min_threshold
        ORDER BY i.current_stock ASC;
    """).fetchall()

    print("\nHasil Update Material usera (Menipis & Habis):")
    for r in rows:
        print(f"  [{r[0]}] {r[1]} -> Stok: {r[2]} {r[4]} (Batas Min: {r[3]} {r[4]}) -> Status: {r[5]}")

    conn.close()

if __name__ == "__main__":
    apply_low_and_out_of_stock()
