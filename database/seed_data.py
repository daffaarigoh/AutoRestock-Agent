"""
Seed Data Script for AutoRestock-V2
Populates realistic enterprise inventory items, suppliers, and baseline restock triggers.
"""

from database.db import db
from core.schemas import Supplier, InventoryItem
from datetime import datetime


def seed_database():
    print("Populating suppliers...")
    suppliers = [
        Supplier(
            id="SUP-001",
            name="PT Indofood CBP Sukses Makmur Tbk",
            contact_person="Budi Santoso (Key Account Mgr)",
            email="budi.santoso@indofood.co.id",
            phone="+62 21 5795 8822",
            address="Kawasan Industri Pulogadung Kav. 12, Jakarta Timur",
            lead_time_days=2,
            rating=4.9
        ),
        Supplier(
            id="SUP-002",
            name="PT Sumber Alfaria Distribusi",
            contact_person="Siti Rahmawati (Procurement Head)",
            email="siti.rahmawati@alfamart.co.id",
            phone="+62 21 5575 5959",
            address="Jl. MH Thamrin No. 9, Cikokol, Tangerang",
            lead_time_days=3,
            rating=4.8
        ),
        Supplier(
            id="SUP-003",
            name="PT Sinarmas Pulp & Paper Supply",
            contact_person="Hendra Wijaya (Sales Director)",
            email="hendra.wijaya@sinarmas.com",
            phone="+62 21 3929 266",
            address="Plaza BII Tower 2, Jl. MH Thamrin 51, Jakarta Pusat",
            lead_time_days=3,
            rating=4.7
        ),
        Supplier(
            id="SUP-004",
            name="PT Kawan Lama Solusi Industri",
            contact_person="Agus Setiawan (Industrial Engineer)",
            email="agus.setiawan@kawanlama.com",
            phone="+62 21 5828 282",
            address="Jl. Puri Kencana No. 1, Meruya Kembangan, Jakarta Barat",
            lead_time_days=4,
            rating=4.9
        ),
        Supplier(
            id="SUP-005",
            name="PT Surya Graha IT & Elektronika",
            contact_person="Dewi Lestari (Enterprise Solutions)",
            email="dewi.lestari@suryagraha.co.id",
            phone="+62 22 730 4588",
            address="Kompleks Ruko Asia Afrika No. 45, Bandung",
            lead_time_days=2,
            rating=4.6
        )
    ]

    for sup in suppliers:
        db.upsert_supplier(sup)

    print("Populating inventory catalog...")
    items = [
        # FMCG & Sembako
        InventoryItem(
            sku="FMCG-MINYAK-01",
            name="Minyak Goreng Bimoli Klasik 2 Liter Pouch",
            category="FMCG",
            current_stock=8,      # Low stock! Trigger restock
            min_stock=25,
            max_stock=120,
            safety_stock=10,
            unit="pouch",
            unit_price=36500.0,
            supplier_id="SUP-002",
            supplier_name="PT Sumber Alfaria Distribusi",
            lead_time_days=3,
            location_bin="RAK-A-01",
            status="low_stock"
        ),
        InventoryItem(
            sku="FMCG-BERAS-01",
            name="Beras Setra Ramos Premium 5 Kg",
            category="FMCG",
            current_stock=4,      # Critical low stock!
            min_stock=20,
            max_stock=80,
            safety_stock=8,
            unit="sak",
            unit_price=74000.0,
            supplier_id="SUP-002",
            supplier_name="PT Sumber Alfaria Distribusi",
            lead_time_days=3,
            location_bin="PALLET-B-01",
            status="low_stock"
        ),
        InventoryItem(
            sku="FMCG-GULA-01",
            name="Gula Pasir Gulaku Premium Tebu 1 Kg",
            category="FMCG",
            current_stock=45,
            min_stock=30,
            max_stock=150,
            safety_stock=15,
            unit="kg",
            unit_price=17500.0,
            supplier_id="SUP-002",
            supplier_name="PT Sumber Alfaria Distribusi",
            lead_time_days=3,
            location_bin="RAK-A-02",
            status="normal"
        ),
        InventoryItem(
            sku="FMCG-INDOMIE-01",
            name="Indomie Mi Instan Goreng Spesial (Karton 40 pcs)",
            category="FMCG",
            current_stock=3,      # Critical low stock!
            min_stock=15,
            max_stock=100,
            safety_stock=5,
            unit="karton",
            unit_price=118000.0,
            supplier_id="SUP-001",
            supplier_name="PT Indofood CBP Sukses Makmur Tbk",
            lead_time_days=2,
            location_bin="PALLET-C-02",
            status="low_stock"
        ),
        InventoryItem(
            sku="FMCG-SUSU-01",
            name="Susu UHT Ultra Milk Plain 1000ml (Karton 12 pcs)",
            category="FMCG",
            current_stock=18,
            min_stock=12,
            max_stock=60,
            safety_stock=4,
            unit="karton",
            unit_price=215000.0,
            supplier_id="SUP-002",
            supplier_name="PT Sumber Alfaria Distribusi",
            lead_time_days=3,
            location_bin="RAK-A-04",
            status="normal"
        ),

        # Food & Beverage
        InventoryItem(
            sku="FNB-KOPI-01",
            name="Kopi Kapal Api Special Mix 20x25gr",
            category="Food & Beverage",
            current_stock=6,      # Low stock!
            min_stock=15,
            max_stock=70,
            safety_stock=5,
            unit="pack",
            unit_price=24500.0,
            supplier_id="SUP-001",
            supplier_name="PT Indofood CBP Sukses Makmur Tbk",
            lead_time_days=2,
            location_bin="RAK-B-01",
            status="low_stock"
        ),
        InventoryItem(
            sku="FNB-AQUA-01",
            name="Air Mineral Aqua Botol 600ml (Karton 24 btl)",
            category="Food & Beverage",
            current_stock=2,      # Out of stock imminent!
            min_stock=20,
            max_stock=100,
            safety_stock=8,
            unit="karton",
            unit_price=54000.0,
            supplier_id="SUP-002",
            supplier_name="PT Sumber Alfaria Distribusi",
            lead_time_days=3,
            location_bin="PALLET-C-01",
            status="low_stock"
        ),

        # Office Supplies
        InventoryItem(
            sku="ATK-KERTAS-A4",
            name="Kertas HVS PaperOne A4 80 GSM (Box 5 Rim)",
            category="Office Supplies",
            current_stock=5,      # Low stock!
            min_stock=15,
            max_stock=60,
            safety_stock=5,
            unit="box",
            unit_price=245000.0,
            supplier_id="SUP-003",
            supplier_name="PT Sinarmas Pulp & Paper Supply",
            lead_time_days=3,
            location_bin="RAK-D-01",
            status="low_stock"
        ),
        InventoryItem(
            sku="ATK-KERTAS-F4",
            name="Kertas HVS Sinar Dunia F4 75 GSM (Box 5 Rim)",
            category="Office Supplies",
            current_stock=12,
            min_stock=10,
            max_stock=50,
            safety_stock=4,
            unit="box",
            unit_price=238000.0,
            supplier_id="SUP-003",
            supplier_name="PT Sinarmas Pulp & Paper Supply",
            lead_time_days=3,
            location_bin="RAK-D-02",
            status="normal"
        ),
        InventoryItem(
            sku="ATK-PEN-01",
            name="Ballpoint Faster C600 Black 0.7mm (Pack 12 pcs)",
            category="Office Supplies",
            current_stock=0,      # Out of stock!
            min_stock=10,
            max_stock=50,
            safety_stock=5,
            unit="pack",
            unit_price=38500.0,
            supplier_id="SUP-003",
            supplier_name="PT Sinarmas Pulp & Paper Supply",
            lead_time_days=3,
            location_bin="LACI-D-05",
            status="out_of_stock"
        ),

        # Industrial Hardware
        InventoryItem(
            sku="IND-BEARING-01",
            name="Deep Groove Ball Bearing SKF 6205-2RSH",
            category="Industrial Spare Parts",
            current_stock=2,      # Low stock
            min_stock=8,
            max_stock=30,
            safety_stock=3,
            unit="pcs",
            unit_price=85000.0,
            supplier_id="SUP-004",
            supplier_name="PT Kawan Lama Solusi Industri",
            lead_time_days=4,
            location_bin="BIN-E-12",
            status="low_stock"
        ),
        InventoryItem(
            sku="IND-LUBE-01",
            name="WD-40 Multi-Use Smart Straw Spray 412ml",
            category="Industrial Spare Parts",
            current_stock=14,
            min_stock=10,
            max_stock=40,
            safety_stock=4,
            unit="kaleng",
            unit_price=89000.0,
            supplier_id="SUP-004",
            supplier_name="PT Kawan Lama Solusi Industri",
            lead_time_days=4,
            location_bin="RAK-E-03",
            status="normal"
        ),

        # Electronics & IT
        InventoryItem(
            sku="IT-TONER-85A",
            name="Toner Cartridge Original HP Laserjet 85A CE285A",
            category="IT & Electronics",
            current_stock=1,      # Low stock!
            min_stock=4,
            max_stock=15,
            safety_stock=2,
            unit="unit",
            unit_price=980000.0,
            supplier_id="SUP-005",
            supplier_name="PT Surya Graha IT & Elektronika",
            lead_time_days=2,
            location_bin="LEMARI-IT-01",
            status="low_stock"
        ),
        InventoryItem(
            sku="IT-UTP-CAT6",
            name="Kabel UTP Cat6 Belden Original 1000ft (Roll 305m)",
            category="IT & Electronics",
            current_stock=3,
            min_stock=2,
            max_stock=10,
            safety_stock=1,
            unit="roll",
            unit_price=1850000.0,
            supplier_id="SUP-005",
            supplier_name="PT Surya Graha IT & Elektronika",
            lead_time_days=2,
            location_bin="LEMARI-IT-02",
            status="normal"
        )
    ]

    for item in items:
        db.upsert_item(item)

    print("Populating initial categories...")
    base_cats = ["FMCG", "Food & Beverage", "Office Supplies", "Industrial Spare Parts", "IT & Electronics"]
    for c in base_cats:
        db.add_category(c)

    print(f"Database seeded successfully with {len(suppliers)} suppliers, {len(items)} catalog items, and {len(base_cats)} categories.")


if __name__ == "__main__":
    seed_database()
