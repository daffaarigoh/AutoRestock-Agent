import os
import sys
from pathlib import Path
import duckdb

# Fix console encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = WORKSPACE_DIR / "storage"
DB_PATH = STORAGE_DIR / "inventory.db"


def init_db(db_path: Path = DB_PATH):
    """Initialize DuckDB database and create relational tables."""
    # Ensure storage directory exists
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    db_path_str = db_path.as_posix() if isinstance(db_path, Path) else str(db_path).replace("\\", "/")
    print(f"Connecting to DuckDB at: {db_path_str}")
    conn = duckdb.connect(db_path_str)

    # Drop existing tables to allow clean re-seeding
    conn.execute("DROP TABLE IF EXISTS orders;")
    conn.execute("DROP TABLE IF EXISTS vendors;")
    conn.execute("DROP TABLE IF EXISTS items;")

    # 1. Create items table
    conn.execute("""
        CREATE TABLE items (
            item_id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            current_stock INTEGER NOT NULL,
            min_threshold INTEGER NOT NULL,
            avg_daily_usage FLOAT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            unit VARCHAR NOT NULL
        );
    """)

    # 2. Create vendors table
    conn.execute("""
        CREATE TABLE vendors (
            vendor_id VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            item_id VARCHAR NOT NULL,
            unit_price FLOAT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            rating FLOAT DEFAULT 5.0,
            PRIMARY KEY (vendor_id, item_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        );
    """)

    # 3. Create orders table
    conn.execute("""
        CREATE TABLE orders (
            order_id VARCHAR PRIMARY KEY,
            pr_number VARCHAR NOT NULL,
            item_id VARCHAR NOT NULL,
            vendor_id VARCHAR NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price FLOAT NOT NULL,
            total_price FLOAT NOT NULL,
            status VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        );
    """)

    return conn


def seed_data(conn: duckdb.DuckDBPyConnection):
    """Seed items and vendors data with 25 items (including critical stock items)."""
    # 25 Items (Items 1-5 have critical stock levels: current_stock < min_threshold)
    items_data = [
        # (item_id, name, category, current_stock, min_threshold, avg_daily_usage, lead_time_days, unit)
        ("ITM-001", "Microcontroller STM32F401", "Electronics", 12, 50, 8.5, 7, "pcs"),     # CRITICAL (12 < 50)
        ("ITM-002", "ESP32-WROOM-32D Module", "Electronics", 8, 40, 6.0, 5, "pcs"),         # CRITICAL (8 < 40)
        ("ITM-003", "Thermal Paste Arctic MX-4 4g", "Consumables", 5, 25, 3.2, 4, "tube"),    # CRITICAL (5 < 25)
        ("ITM-004", "Cardboard Box 30x20x15cm", "Packaging", 35, 150, 25.0, 3, "pcs"),       # CRITICAL (35 < 150)
        ("ITM-005", "Bubble Wrap Roll 50m x 50cm", "Packaging", 4, 15, 2.0, 3, "roll"),      # CRITICAL (4 < 15)
        ("ITM-006", "Solder Wire Lead-Free 0.8mm 500g", "Consumables", 28, 20, 1.5, 5, "spool"),
        ("ITM-007", "Lithium Polymer Battery 3.7V 1200mAh", "Electronics", 85, 50, 5.0, 10, "pcs"),
        ("ITM-008", "Stepper Motor NEMA 17", "Mechanical", 45, 30, 3.0, 8, "pcs"),
        ("ITM-009", "Linear Rail MGN12H 300mm", "Mechanical", 22, 15, 1.2, 12, "set"),
        ("ITM-010", "PLA 3D Printer Filament 1.75mm 1kg", "Raw Materials", 60, 35, 4.0, 4, "spool"),
        ("ITM-011", "PETG Filament 1.75mm Black 1kg", "Raw Materials", 32, 20, 2.5, 4, "spool"),
        ("ITM-012", "Kapton Tape 20mm x 33m", "Consumables", 40, 25, 2.0, 5, "roll"),
        ("ITM-013", "Industrial Isopropyl Alcohol 99% 5L", "Chemicals", 18, 10, 1.0, 3, "canister"),
        ("ITM-014", "Anti-Static ESD Gloves (M)", "Safety", 120, 60, 8.0, 3, "pair"),
        ("ITM-015", "Heat Shrink Tubing Assortment Box", "Consumables", 55, 30, 3.5, 6, "box"),
        ("ITM-016", "USB-C to USB-A Cable 1m", "Cables", 90, 40, 4.0, 5, "pcs"),
        ("ITM-017", "Silica Gel Desiccant Packets 5g", "Packaging", 450, 200, 30.0, 2, "pack"),
        ("ITM-018", "M3 Hex Socket Screws Kit 500pcs", "Hardware", 25, 15, 1.5, 4, "kit"),
        ("ITM-019", "Aluminum Heat Sink 20x20x6mm", "Electronics", 210, 100, 12.0, 7, "pcs"),
        ("ITM-020", "DC Brushless Cooling Fan 12V 4010", "Electronics", 65, 30, 3.0, 6, "pcs"),
        ("ITM-021", "Shipping Label Thermal Paper 100x150mm", "Packaging", 80, 50, 6.0, 3, "roll"),
        ("ITM-022", "Flux Pen No-Clean 10ml", "Consumables", 35, 20, 1.8, 5, "pcs"),
        ("ITM-023", "Multimeter Test Leads Probe Set", "Tools", 28, 15, 0.8, 6, "set"),
        ("ITM-024", "Desoldering Wick Braid 2.5mm", "Consumables", 48, 25, 2.2, 4, "roll"),
        ("ITM-025", "Barcoding Scanner Wireless 2.4G", "Equipment", 14, 8, 0.4, 10, "unit")
    ]

    conn.executemany("""
        INSERT INTO items (item_id, name, category, current_stock, min_threshold, avg_daily_usage, lead_time_days, unit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, items_data)
    print(f"[OK] Successfully inserted {len(items_data)} items into 'items' table.")

    # Vendors data (Multiple competitive vendors for key items to support AI vendor selection)
    vendors_data = [
        # (vendor_id, name, item_id, unit_price, lead_time_days, rating)
        # Vendors for ITM-001 (STM32)
        ("VND-001", "Semicon Global Indo", "ITM-001", 65000.0, 5, 4.9),
        ("VND-002", "Nusantara Micro Components", "ITM-001", 68000.0, 3, 4.7),
        # Vendors for ITM-002 (ESP32)
        ("VND-001", "Semicon Global Indo", "ITM-002", 42000.0, 4, 4.9),
        ("VND-003", "TechParts Asia Direct", "ITM-002", 39500.0, 7, 4.5),
        # Vendors for ITM-003 (Thermal Paste)
        ("VND-004", "CoolingTech Solutions", "ITM-003", 85000.0, 3, 4.8),
        ("VND-005", "Mitra Hardware Industri", "ITM-003", 90000.0, 2, 4.6),
        # Vendors for ITM-004 (Cardboard Box)
        ("VND-006", "Surya Packindo Perkasa", "ITM-004", 4500.0, 2, 4.9),
        ("VND-007", "Karya Box Nusantara", "ITM-004", 4200.0, 5, 4.4),
        # Vendors for ITM-005 (Bubble Wrap)
        ("VND-006", "Surya Packindo Perkasa", "ITM-005", 95000.0, 2, 4.9),
        ("VND-008", "Prima Pack Indonesia", "ITM-005", 92000.0, 4, 4.7),
        # Vendors for ITM-006 (Solder Wire)
        ("VND-005", "Mitra Hardware Industri", "ITM-006", 175000.0, 3, 4.6),
        ("VND-009", "Solderindo Mandiri", "ITM-006", 168000.0, 5, 4.8),
        # Vendors for ITM-007 (LiPo Battery)
        ("VND-010", "PowerCell Prima", "ITM-007", 55000.0, 8, 4.7),
        # Vendors for ITM-008 (Stepper Motor)
        ("VND-011", "Maju Mekatronika", "ITM-008", 135000.0, 6, 4.8),
        # Vendors for ITM-009 (Linear Rail)
        ("VND-011", "Maju Mekatronika", "ITM-009", 220000.0, 10, 4.8),
        # Vendors for ITM-010 (PLA Filament)
        ("VND-012", "Cipta 3D Polymer", "ITM-010", 145000.0, 3, 4.9),
        # Vendors for ITM-011 (PETG Filament)
        ("VND-012", "Cipta 3D Polymer", "ITM-011", 160000.0, 3, 4.9),
        # Vendors for ITM-012 (Kapton Tape)
        ("VND-005", "Mitra Hardware Industri", "ITM-012", 45000.0, 3, 4.6),
        # Vendors for ITM-013 (IPA 99%)
        ("VND-013", "Kimia Murni Sejahtera", "ITM-013", 185000.0, 2, 4.8),
        # Vendors for ITM-014 (ESD Gloves)
        ("VND-014", "Safetindo Proteksi", "ITM-014", 15000.0, 2, 4.7),
        # Vendors for ITM-015 (Heat Shrink Tubing)
        ("VND-005", "Mitra Hardware Industri", "ITM-015", 65000.0, 4, 4.6),
        # Vendors for ITM-016 (USB-C Cable)
        ("VND-003", "TechParts Asia Direct", "ITM-016", 25000.0, 5, 4.5),
        # Vendors for ITM-017 (Silica Gel)
        ("VND-008", "Prima Pack Indonesia", "ITM-017", 450.0, 2, 4.7),
        # Vendors for ITM-018 (M3 Screws Kit)
        ("VND-005", "Mitra Hardware Industri", "ITM-018", 75000.0, 3, 4.6),
        # Vendors for ITM-019 (Heat Sink)
        ("VND-004", "CoolingTech Solutions", "ITM-019", 3500.0, 5, 4.8),
        # Vendors for ITM-020 (Cooling Fan)
        ("VND-004", "CoolingTech Solutions", "ITM-020", 28000.0, 4, 4.8),
        # Vendors for ITM-021 (Shipping Labels)
        ("VND-006", "Surya Packindo Perkasa", "ITM-021", 52000.0, 2, 4.9),
        # Vendors for ITM-022 (Flux Pen)
        ("VND-009", "Solderindo Mandiri", "ITM-022", 35000.0, 4, 4.8),
        # Vendors for ITM-023 (Multimeter Probes)
        ("VND-015", "Instrumenta Graha", "ITM-023", 95000.0, 5, 4.6),
        # Vendors for ITM-024 (Desoldering Wick)
        ("VND-009", "Solderindo Mandiri", "ITM-024", 28000.0, 3, 4.8),
        # Vendors for ITM-025 (Barcode Scanner)
        ("VND-016", "Optima AutoID Solution", "ITM-025", 380000.0, 7, 4.9)
    ]

    conn.executemany("""
        INSERT INTO vendors (vendor_id, name, item_id, unit_price, lead_time_days, rating)
        VALUES (?, ?, ?, ?, ?, ?);
    """, vendors_data)
    print(f"[OK] Successfully inserted {len(vendors_data)} vendor relations into 'vendors' table.")


def test_critical_items_query(conn: duckdb.DuckDBPyConnection):
    """Query and display items with stock below minimum threshold."""
    print("\n" + "=" * 95)
    print("CRITICAL INVENTORY ITEMS REPORT (current_stock < min_threshold)")
    print("Formula: Safety Stock = Lead Time * Daily Usage * 1.5")
    print("Formula: Reorder Qty = (Daily Usage * Lead Time) + Safety Stock - Current Stock")
    print("=" * 95)

    query = """
        SELECT 
            i.item_id,
            i.name,
            i.category,
            i.current_stock,
            i.min_threshold,
            i.avg_daily_usage,
            i.lead_time_days,
            ROUND(i.lead_time_days * i.avg_daily_usage * 1.5, 0) AS safety_stock,
            ROUND((i.avg_daily_usage * i.lead_time_days) + (i.lead_time_days * i.avg_daily_usage * 1.5) - i.current_stock, 0) AS dynamic_reorder_qty,
            i.unit,
            COUNT(v.vendor_id) AS available_vendors,
            MIN(v.unit_price) AS lowest_price
        FROM items i
        LEFT JOIN vendors v ON i.item_id = v.item_id
        WHERE i.current_stock < i.min_threshold
        GROUP BY 
            i.item_id, i.name, i.category, i.current_stock, 
            i.min_threshold, i.avg_daily_usage, i.lead_time_days, i.unit
        ORDER BY (i.min_threshold - i.current_stock) DESC;
    """

    df = conn.execute(query).df()
    print(df.to_string(index=False))
    print("=" * 95)
    print(f"Total Critical Items Found: {len(df)}")
    print("=" * 95 + "\n")


if __name__ == "__main__":
    conn = init_db()
    seed_data(conn)
    test_critical_items_query(conn)
    conn.close()
    print("[SUCCESS] Database seeding completed successfully.")
