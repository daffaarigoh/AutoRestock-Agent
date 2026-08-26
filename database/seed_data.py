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
    """Initialize DuckDB database and create relational tables with Multi-Tenant RLS."""
    # Ensure storage directory exists
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    db_path_str = db_path.as_posix() if isinstance(db_path, Path) else str(db_path).replace("\\", "/")
    print(f"Connecting to DuckDB at: {db_path_str}")
    conn = duckdb.connect(db_path_str)

    # Drop existing tables to allow clean re-seeding
    conn.execute("DROP TABLE IF EXISTS orders;")
    conn.execute("DROP TABLE IF EXISTS vendors;")
    conn.execute("DROP TABLE IF EXISTS items;")
    conn.execute("DROP TABLE IF EXISTS system_settings;")
    conn.execute("DROP TABLE IF EXISTS users;")
    conn.execute("DROP TABLE IF EXISTS workflows;")

    # 1. Create users table
    conn.execute("""
        CREATE TABLE users (
            user_id VARCHAR PRIMARY KEY,
            username VARCHAR NOT NULL UNIQUE,
            password_hash VARCHAR NOT NULL,
            role VARCHAR NOT NULL,
            tenant_id VARCHAR NOT NULL
        );
    """)

    # 2. Create system_settings table (For Admin prompts)
    conn.execute("""
        CREATE TABLE system_settings (
            key VARCHAR PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    # 3. Create items table (Added tenant_id)
    conn.execute("""
        CREATE TABLE items (
            item_id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            current_stock INTEGER NOT NULL,
            min_threshold INTEGER NOT NULL,
            avg_daily_usage FLOAT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            unit VARCHAR NOT NULL,
            tenant_id VARCHAR NOT NULL
        );
    """)

    # 4. Create vendors table (Added tenant_id)
    conn.execute("""
        CREATE TABLE vendors (
            vendor_id VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            item_id VARCHAR NOT NULL,
            unit_price FLOAT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            rating FLOAT DEFAULT 5.0,
            tenant_id VARCHAR NOT NULL,
            PRIMARY KEY (vendor_id, item_id),
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        );
    """)

    # 5. Create orders table (Added tenant_id)
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
            tenant_id VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(item_id)
        );
    """)

    # 6. Create workflows table
    conn.execute("""
        CREATE TABLE workflows (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description TEXT,
            business_instruction TEXT NOT NULL,
            compiled_json TEXT NOT NULL
        );
    """)

    return conn


def seed_data(conn: duckdb.DuckDBPyConnection):
    """Seed base multi-tenant data."""
    # Passwords: admin123 and user123
    admin_hash = "$2b$12$JOM29UUbKtItgDFOrcsjuOmRK0mOC9/agdo.RWmU1mzRX7aT/YV06"
    user_hash = "$2b$12$woqxbeUBVL7YRCLzBR1hEOQKPsBslbohqqbgv9Pl5vxvqwHCNcnVm"

    # Seed Users
    users_data = [
        ("USR-001", "admin", admin_hash, "ADMIN", "ALL"),
        ("USR-002", "usera", user_hash, "USER", "TENANT_A"),
        ("USR-003", "userb", user_hash, "USER", "TENANT_B"),
        ("USR-004", "userc", user_hash, "USER", "TENANT_C")
    ]
    conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?);", users_data)
    print("[OK] Users seeded.")

    # Seed Default System Prompt
    default_prompt = (
        "Anda adalah AutoRestock-Agent, asisten AI spesialis manajemen rantai pasok.\n"
        "Anda bertugas menganalisis stok barang dari database. Anda HANYA menangani barang yang dimiliki oleh pengguna yang sedang meminta informasi.\n"
        "Gunakan bahasa Indonesia yang profesional, jelas, dan sangat membantu."
    )
    conn.execute("INSERT INTO system_settings VALUES ('system_prompt', ?)", [default_prompt])
    print("[OK] System Prompt seeded.")

    # Seed Workflows
    import json
    wf_1_json = {
        "workflow": "auto_restock",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.get_low_stock_products"},
            {"type": "agent", "task": "calculate_reorder_quantity"},
            {"type": "tool", "tool": "purchase_order.create_draft"},
            {"type": "tool", "tool": "notification.send_email"}
        ]
    }
    wf_2_json = {
        "workflow": "update_threshold",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.update_threshold"}
        ]
    }
    
    wf_3_json = {
        "workflow": "laporan_stok_kritis",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.get_low_stock_products"},
            {"type": "tool", "tool": "notification.send_email"}
        ]
    }
    wf_4_json = {
        "workflow": "audit_seluruh_gudang",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.get_all_products"},
            {"type": "tool", "tool": "notification.send_email"}
        ]
    }
    
    wf_5_json = {
        "workflow": "cek_stok_spesifik",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.check_specific_stock"}
        ]
    }
    
    workflows_data = [
        ("WF-001", "Auto Restock (End-to-End)", "Memeriksa stok yang kurang dari batas minimum, menghitung ulang kebutuhan, dan membuat draf PR.", "Periksa stok produk. Jika ada yang kurang dari batas, hitung kebutuhan restock berdasarkan data. Buatkan draf Purchase Requisition dan kirim notifikasi email.", json.dumps(wf_1_json)),
        ("WF-002", "Update Threshold Stok", "Memperbarui nilai batas minimum (threshold) untuk produk tertentu di database.", "Ubah threshold barang sesuai permintaan, lalu simpan kembali ke database.", json.dumps(wf_2_json)),
        ("WF-003", "Laporan Stok Kritis (Audit)", "Menarik daftar barang yang sudah di bawah threshold dan mengirim email laporannya tanpa membeli.", "Tarik semua data barang yang stoknya menipis. Jangan beli apa-apa, cukup kirimkan daftar laporannya ke email operasional.", json.dumps(wf_3_json)),
        ("WF-004", "Audit Seluruh Gudang", "Menarik data seluruh barang (termasuk yang stoknya aman) dan mengirimkan ke email manajer.", "Lakukan audit gudang dengan menarik seluruh data barang yang ada di sistem, lalu kirim email ke manajer.", json.dumps(wf_4_json)),
        ("WF-005", "Cek Stok Barang Spesifik", "Menjawab pertanyaan user mengenai jumlah stok barang tertentu.", "Jika user menanyakan stok barang tertentu secara spesifik (misal: 'berapa stok kopi'), cek stok barang tersebut secara langsung dan kembalikan jawabannya.", json.dumps(wf_5_json))
    ]
    conn.executemany("INSERT INTO workflows VALUES (?, ?, ?, ?, ?);", workflows_data)
    print("[OK] Workflows seeded.")

    # 25 Items distributed across Tenants
    items_data = [
        # (item_id, name, category, current_stock, min_threshold, avg_daily_usage, lead_time_days, unit, tenant_id)
        # TENANT_A (Items 1-9)
        ("ITM-001", "Microcontroller STM32F401", "Electronics", 12, 50, 8.5, 7, "pcs", "TENANT_A"),
        ("ITM-002", "ESP32-WROOM-32D Module", "Electronics", 8, 40, 6.0, 5, "pcs", "TENANT_A"),
        ("ITM-003", "Thermal Paste Arctic MX-4 4g", "Consumables", 5, 25, 3.2, 4, "tube", "TENANT_A"),
        ("ITM-004", "Cardboard Box 30x20x15cm", "Packaging", 35, 150, 25.0, 3, "pcs", "TENANT_A"),
        ("ITM-005", "Bubble Wrap Roll 50m x 50cm", "Packaging", 4, 15, 2.0, 3, "roll", "TENANT_A"),
        ("ITM-006", "Solder Wire Lead-Free 0.8mm 500g", "Consumables", 28, 20, 1.5, 5, "spool", "TENANT_A"),
        ("ITM-007", "Lithium Polymer Battery 3.7V 1200mAh", "Electronics", 85, 50, 5.0, 10, "pcs", "TENANT_A"),
        ("ITM-008", "Stepper Motor NEMA 17", "Mechanical", 45, 30, 3.0, 8, "pcs", "TENANT_A"),
        ("ITM-009", "Linear Rail MGN12H 300mm", "Mechanical", 22, 15, 1.2, 12, "set", "TENANT_A"),
        
        # TENANT_B (Items 10-17)
        ("ITM-010", "PLA 3D Printer Filament 1kg", "Raw Materials", 60, 35, 4.0, 4, "spool", "TENANT_B"),
        ("ITM-011", "PETG Filament Black 1kg", "Raw Materials", 32, 20, 2.5, 4, "spool", "TENANT_B"),
        ("ITM-012", "Kapton Tape 20mm x 33m", "Consumables", 40, 25, 2.0, 5, "roll", "TENANT_B"),
        ("ITM-013", "Industrial Isopropyl Alcohol 99% 5L", "Chemicals", 18, 10, 1.0, 3, "canister", "TENANT_B"),
        ("ITM-014", "Anti-Static ESD Gloves (M)", "Safety", 120, 60, 8.0, 3, "pair", "TENANT_B"),
        ("ITM-015", "Heat Shrink Tubing Assortment Box", "Consumables", 55, 30, 3.5, 6, "box", "TENANT_B"),
        ("ITM-016", "USB-C to USB-A Cable 1m", "Cables", 90, 40, 4.0, 5, "pcs", "TENANT_B"),
        ("ITM-017", "Silica Gel Desiccant Packets 5g", "Packaging", 450, 200, 30.0, 2, "pack", "TENANT_B"),
        
        # TENANT_C (Items 18-25)
        ("ITM-018", "M3 Hex Socket Screws Kit 500pcs", "Hardware", 25, 15, 1.5, 4, "kit", "TENANT_C"),
        ("ITM-019", "Aluminum Heat Sink 20x20x6mm", "Electronics", 210, 100, 12.0, 7, "pcs", "TENANT_C"),
        ("ITM-020", "DC Brushless Cooling Fan 12V 4010", "Electronics", 65, 30, 3.0, 6, "pcs", "TENANT_C"),
        ("ITM-021", "Shipping Label Thermal Paper 100x150mm", "Packaging", 80, 50, 6.0, 3, "roll", "TENANT_C"),
        ("ITM-022", "Flux Pen No-Clean 10ml", "Consumables", 35, 20, 1.8, 5, "pcs", "TENANT_C"),
        ("ITM-023", "Multimeter Test Leads Probe Set", "Tools", 28, 15, 0.8, 6, "set", "TENANT_C"),
        ("ITM-024", "Desoldering Wick Braid 2.5mm", "Consumables", 48, 25, 2.2, 4, "roll", "TENANT_C"),
        ("ITM-025", "Barcoding Scanner Wireless 2.4G", "Equipment", 14, 8, 0.4, 10, "unit", "TENANT_C")
    ]
    conn.executemany("""
        INSERT INTO items (item_id, name, category, current_stock, min_threshold, avg_daily_usage, lead_time_days, unit, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, items_data)
    print(f"[OK] Successfully inserted {len(items_data)} items into 'items' table.")

    # Vendors data mapped to the same tenant as the item
    vendors_data = [
        ("VND-001", "Semicon Global Indo", "ITM-001", 65000.0, 5, 4.9, "TENANT_A"),
        ("VND-002", "Nusantara Micro Components", "ITM-001", 68000.0, 3, 4.7, "TENANT_A"),
        ("VND-001", "Semicon Global Indo", "ITM-002", 42000.0, 4, 4.9, "TENANT_A"),
        ("VND-003", "TechParts Asia Direct", "ITM-002", 39500.0, 7, 4.5, "TENANT_A"),
        ("VND-004", "CoolingTech Solutions", "ITM-003", 85000.0, 3, 4.8, "TENANT_A"),
        ("VND-005", "Mitra Hardware Industri", "ITM-003", 90000.0, 2, 4.6, "TENANT_A"),
        ("VND-006", "Surya Packindo Perkasa", "ITM-004", 4500.0, 2, 4.9, "TENANT_A"),
        ("VND-007", "Karya Box Nusantara", "ITM-004", 4200.0, 5, 4.4, "TENANT_A"),
        ("VND-006", "Surya Packindo Perkasa", "ITM-005", 95000.0, 2, 4.9, "TENANT_A"),
        ("VND-008", "Prima Pack Indonesia", "ITM-005", 92000.0, 4, 4.7, "TENANT_A"),
        ("VND-005", "Mitra Hardware Industri", "ITM-006", 175000.0, 3, 4.6, "TENANT_A"),
        ("VND-009", "Solderindo Mandiri", "ITM-006", 168000.0, 5, 4.8, "TENANT_A"),
        ("VND-010", "PowerCell Prima", "ITM-007", 55000.0, 8, 4.7, "TENANT_A"),
        ("VND-011", "Maju Mekatronika", "ITM-008", 135000.0, 6, 4.8, "TENANT_A"),
        ("VND-011", "Maju Mekatronika", "ITM-009", 220000.0, 10, 4.8, "TENANT_A"),

        ("VND-012", "Cipta 3D Polymer", "ITM-010", 145000.0, 3, 4.9, "TENANT_B"),
        ("VND-012", "Cipta 3D Polymer", "ITM-011", 160000.0, 3, 4.9, "TENANT_B"),
        ("VND-005", "Mitra Hardware Industri", "ITM-012", 45000.0, 3, 4.6, "TENANT_B"),
        ("VND-013", "Kimia Murni Sejahtera", "ITM-013", 185000.0, 2, 4.8, "TENANT_B"),
        ("VND-014", "Safetindo Proteksi", "ITM-014", 15000.0, 2, 4.7, "TENANT_B"),
        ("VND-005", "Mitra Hardware Industri", "ITM-015", 65000.0, 4, 4.6, "TENANT_B"),
        ("VND-003", "TechParts Asia Direct", "ITM-016", 25000.0, 5, 4.5, "TENANT_B"),
        ("VND-008", "Prima Pack Indonesia", "ITM-017", 450.0, 2, 4.7, "TENANT_B"),

        ("VND-005", "Mitra Hardware Industri", "ITM-018", 75000.0, 3, 4.6, "TENANT_C"),
        ("VND-004", "CoolingTech Solutions", "ITM-019", 3500.0, 5, 4.8, "TENANT_C"),
        ("VND-004", "CoolingTech Solutions", "ITM-020", 28000.0, 4, 4.8, "TENANT_C"),
        ("VND-006", "Surya Packindo Perkasa", "ITM-021", 52000.0, 2, 4.9, "TENANT_C"),
        ("VND-009", "Solderindo Mandiri", "ITM-022", 35000.0, 4, 4.8, "TENANT_C"),
        ("VND-015", "Instrumenta Graha", "ITM-023", 95000.0, 5, 4.6, "TENANT_C"),
        ("VND-009", "Solderindo Mandiri", "ITM-024", 28000.0, 3, 4.8, "TENANT_C"),
        ("VND-016", "Optima AutoID Solution", "ITM-025", 380000.0, 7, 4.9, "TENANT_C")
    ]
    conn.executemany("""
        INSERT INTO vendors (vendor_id, name, item_id, unit_price, lead_time_days, rating, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """, vendors_data)
    print(f"[OK] Successfully inserted {len(vendors_data)} vendors.")


def test_critical_items_query(conn: duckdb.DuckDBPyConnection):
    """Test query to ensure schema works."""
    query = """
        SELECT i.item_id, i.tenant_id
        FROM items i
        WHERE i.current_stock < i.min_threshold
    """
    df = conn.execute(query).df()
    print(f"Total Critical Items Found: {len(df)}")


if __name__ == "__main__":
    conn = init_db()
    seed_data(conn)
    test_critical_items_query(conn)
    conn.close()
    print("[SUCCESS] Database seeding completed successfully.")
