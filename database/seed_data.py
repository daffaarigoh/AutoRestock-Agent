import json
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
DATA_DIR = WORKSPACE_DIR / "data"
DB_PATH = STORAGE_DIR / "inventory.db"


def init_db(db_path: Path = DB_PATH):
    """Initialize DuckDB database and create relational tables with Multi-Tenant RLS & 3 Heterogeneous Schemas."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    db_path_str = db_path.as_posix() if isinstance(db_path, Path) else str(db_path).replace("\\", "/")
    print(f"Connecting to DuckDB at: {db_path_str}")
    conn = duckdb.connect(db_path_str)

    # 1. Create users table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR PRIMARY KEY,
            username VARCHAR NOT NULL UNIQUE,
            password_hash VARCHAR NOT NULL,
            role VARCHAR NOT NULL,
            tenant_id VARCHAR NOT NULL
        );
    """)

    # 2. Create system_settings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key VARCHAR PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    # 3. Create items table (Legacy / Shared table)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            item_id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            current_stock INTEGER NOT NULL,
            min_threshold INTEGER NOT NULL,
            max_threshold INTEGER NOT NULL,
            avg_daily_usage FLOAT NOT NULL,
            lead_time_days INTEGER NOT NULL,
            unit VARCHAR NOT NULL,
            tenant_id VARCHAR NOT NULL
        );
    """)

    # 4. Create vendors table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vendors (
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

    # 5. Create orders table (Polymorphic references across heterogeneous schemas)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id VARCHAR PRIMARY KEY,
            pr_number VARCHAR NOT NULL,
            item_id VARCHAR NOT NULL,
            vendor_id VARCHAR NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price FLOAT NOT NULL,
            total_price FLOAT NOT NULL,
            status VARCHAR NOT NULL,
            tenant_id VARCHAR NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 6. Create workflows table with tenant_id support
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description TEXT,
            business_instruction TEXT NOT NULL,
            compiled_json TEXT NOT NULL,
            tenant_id VARCHAR DEFAULT 'ALL'
        );
    """)

    # Check and migrate workflows table if tenant_id column is missing
    wf_cols = [d[0] for d in conn.execute("DESCRIBE workflows").fetchall()]
    if "tenant_id" not in wf_cols:
        conn.execute("ALTER TABLE workflows ADD COLUMN tenant_id VARCHAR DEFAULT 'ALL';")
        print("[MIGRATION] Added 'tenant_id' column to workflows table.")

    # -------------------------------------------------------------
    # 7. INGEST 3 HETEROGENEOUS REAL-WORLD SCHEMAS
    # -------------------------------------------------------------
    csv_electronics = (DATA_DIR / "raw_electronics_inventory.csv").as_posix()
    csv_pharma = (DATA_DIR / "raw_pharma_inventory.csv").as_posix()
    csv_fleet = (DATA_DIR / "raw_fleet_parts_inventory.csv").as_posix()

    # Schema 1: User A (TENANT_A) - Electronics Manufacturing
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS mfg_electronics_inventory AS 
        SELECT * FROM read_csv_auto('{csv_electronics}');
    """)

    # Schema 2: User B (TENANT_B) - Pharmaceutical & FMCG WMS
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS pharma_fmcg_inventory AS 
        SELECT * FROM read_csv_auto('{csv_pharma}');
    """)

    # Schema 3: User C (TENANT_C) - Fleet Logistics & Heavy Equipment
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS fleet_maintenance_parts AS 
        SELECT * FROM read_csv_auto('{csv_fleet}');
    """)

    print("[OK] Initialized 3 Heterogeneous Real Datasets in DuckDB.")
    return conn


def seed_data(conn: duckdb.DuckDBPyConnection):
    """Seed base users, system prompts, workflows, and multi-tenant assets."""
    admin_hash = "$2b$12$JOM29UUbKtItgDFOrcsjuOmRK0mOC9/agdo.RWmU1mzRX7aT/YV06"
    user_hash = "$2b$12$woqxbeUBVL7YRCLzBR1hEOQKPsBslbohqqbgv9Pl5vxvqwHCNcnVm"

    # Seed Users
    user_count = conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
    if user_count == 0:
        users_data = [
            ("USR-001", "admin", admin_hash, "ADMIN", "ALL"),
            ("USR-002", "usera", user_hash, "USER", "TENANT_A"),
            ("USR-003", "userb", user_hash, "USER", "TENANT_B"),
            ("USR-004", "userc", user_hash, "USER", "TENANT_C")
        ]
        conn.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?);", users_data)
        print("[OK] Users seeded.")

    # Seed Default System Prompt
    setting_count = conn.execute("SELECT COUNT(*) FROM system_settings WHERE key = 'system_prompt';").fetchone()[0]
    if setting_count == 0:
        default_prompt = (
            "Anda adalah AutoRestock-Agent, asisten AI spesialis manajemen rantai pasok.\n"
            "Anda bertugas menganalisis stok barang dari database. Anda HANYA menangani barang yang dimiliki oleh pengguna yang sedang meminta informasi.\n"
            "Gunakan bahasa Indonesia yang profesional, jelas, dan sangat membantu."
        )
        conn.execute("INSERT INTO system_settings VALUES ('system_prompt', ?)", [default_prompt])
        print("[OK] System Prompt seeded.")

    # Seed Workflows (Global + Tenant-Specific Workflows)
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
            {"type": "tool", "tool": "inventory.get_low_stock_products"}
        ]
    }
    wf_4_json = {
        "workflow": "audit_seluruh_gudang",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.get_all_products"}
        ]
    }
    wf_5_json = {
        "workflow": "cek_stok_spesifik",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.check_specific_stock"}
        ]
    }
    
    # Specific Workflows per Domain
    wf_a01_json = {
        "workflow": "restock_assembly_elektronik",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.get_low_stock_products"},
            {"type": "agent", "task": "calculate_reorder_quantity"},
            {"type": "tool", "tool": "purchase_order.create_draft"},
            {"type": "tool", "tool": "notification.dispatch"}
        ]
    }
    wf_b01_json = {
        "workflow": "audit_stok_obat_kritis",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.get_low_stock_products"},
            {"type": "agent", "task": "calculate_reorder_quantity"},
            {"type": "tool", "tool": "purchase_order.create_draft"},
            {"type": "tool", "tool": "notification.send_email"}
        ]
    }
    wf_c01_json = {
        "workflow": "pengadaan_sparepart_armada",
        "version": 1,
        "steps": [
            {"type": "tool", "tool": "inventory.get_low_stock_products"},
            {"type": "agent", "task": "calculate_reorder_quantity"},
            {"type": "tool", "tool": "purchase_order.create_draft"},
            {"type": "tool", "tool": "notification.dispatch"}
        ]
    }

    workflows_data = [
        ("WF-001", "Auto Restock (End-to-End)", "Memeriksa stok yang kurang dari batas minimum, menghitung ulang kebutuhan, dan membuat draf PR.", "Periksa stok produk. Jika ada yang kurang dari batas, hitung kebutuhan restock berdasarkan data. Buatkan draf Purchase Requisition dan kirim notifikasi email.", json.dumps(wf_1_json), "ALL"),
        ("WF-002", "Update Threshold Stok", "Memperbarui nilai batas minimum (threshold) untuk produk tertentu di database.", "Ubah threshold barang sesuai permintaan, lalu simpan kembali ke database.", json.dumps(wf_2_json), "ALL"),
        ("WF-003", "Laporan Stok Kritis (Audit)", "Menarik daftar barang yang sudah di bawah threshold dan mengirim email laporannya tanpa membeli.", "Tarik semua data barang yang stoknya menipis. Jangan beli apa-apa, cukup kirimkan daftar laporannya ke email operasional.", json.dumps(wf_3_json), "ALL"),
        ("WF-004", "Audit Seluruh Gudang", "Menarik data seluruh barang (termasuk yang stoknya aman) dan mengirimkan ke email manajer.", "Lakukan audit gudang dengan menarik seluruh data barang yang ada di sistem, lalu kirim email ke manajer.", json.dumps(wf_4_json), "ALL"),
        ("WF-005", "Cek Stok Barang Spesifik", "Menjawab pertanyaan user mengenai jumlah stok barang tertentu.", "Jika user menanyakan stok barang tertentu secara spesifik (misal: 'berapa stok kopi'), cek stok barang tersebut secara langsung dan kembalikan jawabannya.", json.dumps(wf_5_json), "ALL"),
        
        # Tenant Specific Workflows
        ("WF-A01", "Restock Komponen Assembly Elektronik", "Memeriksa komponen SMD/IC pabrik di bawah safety reorder point, kalkulasi kebutuhan lead time, dan buatkan PR reel.", "Periksa komponen elektronika assembly line yang berada di bawah safety reorder point. Hitung kebutuhan restock pabrikan dan buatkan draft PR.", json.dumps(wf_a01_json), "TENANT_A"),
        ("WF-B01", "Audit Stok Obat Kritis & Restock Farmasi", "Memeriksa stok obat gudang farmasi dengan shortage flag dan closing stock menipis, lalu buat PO farmasi.", "Tarik data persediaan obat dan kimia farmasi yang berstatus shortage atau stok penutupan menipis. Buatkan Purchase Order obat resmi.", json.dumps(wf_b01_json), "TENANT_B"),
        ("WF-C01", "Pengadaan Suku Cadang Kritis Bengkel Armada", "Scan stok suku cadang armada komersial/alat berat yang berada di bawah critical threshold workshop.", "Periksa stok sparepart armada kendaraan dan alat berat bengkel yang di bawah ambang batas kritis. Buatkan draf pemesanan suku cadang darurat.", json.dumps(wf_c01_json), "TENANT_C"),
    ]

    existing_wf_ids = set([r[0] for r in conn.execute("SELECT id FROM workflows;").fetchall()])
    new_wfs = [w for w in workflows_data if w[0] not in existing_wf_ids]
    if new_wfs:
        conn.executemany("INSERT INTO workflows (id, name, description, business_instruction, compiled_json, tenant_id) VALUES (?, ?, ?, ?, ?, ?);", new_wfs)
    print(f"[OK] Workflows seeded. (Total: {len(conn.execute('SELECT id FROM workflows').fetchall())})")

    # Seed Legacy Items & Vendors if items table is empty
    item_count = conn.execute("SELECT COUNT(*) FROM items;").fetchone()[0]
    if item_count == 0:
        items_data = [
            ("ITM-001", "Microcontroller STM32F401", "Electronics", 12, 50, 150, 8.5, 7, "pcs", "TENANT_A"),
            ("ITM-002", "ESP32-WROOM-32D Module", "Electronics", 8, 40, 120, 6.0, 5, "pcs", "TENANT_A"),
            ("ITM-003", "Thermal Paste Arctic MX-4 4g", "Consumables", 5, 25, 75, 3.2, 4, "tube", "TENANT_A"),
            ("ITM-004", "Cardboard Box 30x20x15cm", "Packaging", 35, 150, 450, 25.0, 3, "pcs", "TENANT_A"),
            ("ITM-005", "Bubble Wrap Roll 50m x 50cm", "Packaging", 4, 15, 45, 2.0, 3, "roll", "TENANT_A"),
            ("ITM-006", "Solder Wire Lead-Free 0.8mm 500g", "Consumables", 28, 20, 60, 1.5, 5, "spool", "TENANT_A"),
            ("ITM-007", "Lithium Polymer Battery 3.7V 1200mAh", "Electronics", 85, 50, 150, 5.0, 10, "pcs", "TENANT_A"),
            ("ITM-008", "Stepper Motor NEMA 17", "Mechanical", 45, 30, 90, 3.0, 8, "pcs", "TENANT_A"),
            ("ITM-009", "Linear Rail MGN12H 300mm", "Mechanical", 22, 15, 45, 1.2, 12, "set", "TENANT_A"),
            ("ITM-010", "PLA 3D Printer Filament 1kg", "Raw Materials", 60, 35, 105, 4.0, 4, "spool", "TENANT_B"),
            ("ITM-011", "PETG Filament Black 1kg", "Raw Materials", 32, 20, 60, 2.5, 4, "spool", "TENANT_B"),
            ("ITM-012", "Kapton Tape 20mm x 33m", "Consumables", 40, 25, 75, 2.0, 5, "roll", "TENANT_B"),
            ("ITM-013", "Industrial Isopropyl Alcohol 99% 5L", "Chemicals", 18, 10, 30, 1.0, 3, "canister", "TENANT_B"),
            ("ITM-014", "Anti-Static ESD Gloves (M)", "Safety", 120, 60, 180, 8.0, 3, "pair", "TENANT_B"),
            ("ITM-015", "Heat Shrink Tubing Assortment Box", "Consumables", 55, 30, 90, 3.5, 6, "box", "TENANT_B"),
            ("ITM-016", "USB-C to USB-A Cable 1m", "Cables", 90, 40, 120, 4.0, 5, "pcs", "TENANT_B"),
            ("ITM-017", "Silica Gel Desiccant Packets 5g", "Packaging", 450, 200, 600, 30.0, 2, "pack", "TENANT_B"),
            ("ITM-018", "M3 Hex Socket Screws Kit 500pcs", "Hardware", 25, 15, 45, 1.5, 4, "kit", "TENANT_C"),
            ("ITM-019", "Aluminum Heat Sink 20x20x6mm", "Electronics", 210, 100, 300, 12.0, 7, "pcs", "TENANT_C"),
            ("ITM-020", "DC Brushless Cooling Fan 12V 4010", "Electronics", 65, 30, 90, 3.0, 6, "pcs", "TENANT_C"),
            ("ITM-021", "Shipping Label Thermal Paper 100x150mm", "Packaging", 80, 50, 150, 6.0, 3, "roll", "TENANT_C"),
            ("ITM-022", "Flux Pen No-Clean 10ml", "Consumables", 35, 20, 60, 1.8, 5, "pcs", "TENANT_C"),
            ("ITM-023", "Multimeter Test Leads Probe Set", "Tools", 28, 15, 45, 0.8, 6, "set", "TENANT_C"),
            ("ITM-024", "Desoldering Wick Braid 2.5mm", "Consumables", 48, 25, 75, 2.2, 4, "roll", "TENANT_C"),
            ("ITM-025", "Barcoding Scanner Wireless 2.4G", "Equipment", 14, 8, 24, 0.4, 10, "unit", "TENANT_C")
        ]
        conn.executemany("""
            INSERT INTO items (item_id, name, category, current_stock, min_threshold, max_threshold, avg_daily_usage, lead_time_days, unit, tenant_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, items_data)
        print(f"[OK] Successfully inserted {len(items_data)} legacy items into 'items' table.")


if __name__ == "__main__":
    conn = init_db()
    seed_data(conn)
    conn.close()
    print("[SUCCESS] Database initialization and heterogeneous data ingestion completed.")
