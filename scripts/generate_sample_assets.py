from pathlib import Path

from PIL import Image, ImageDraw

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
SAMPLES_DIR = WORKSPACE_DIR / "data" / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def create_sample_surat_jalan():
    img = Image.new("RGB", (900, 1150), color="#FFFFFF")
    draw = ImageDraw.Draw(img)

    # Frame border
    draw.rectangle([25, 25, 875, 1125], outline="#0f172a", width=2)
    draw.rectangle([28, 28, 872, 1122], outline="#e2e8f0", width=1)

    # Header Company
    draw.rectangle([25, 25, 875, 130], fill="#f8fafc")
    draw.text((50, 45), "PT. ELEKTRONIKA JAYA PRIMA & LOGISTIK", fill="#1e3a8a")
    draw.text((50, 72), "Kawasan Industri MM2100 Blok B-12, Cikarang Barat, Bekasi", fill="#475569")
    draw.text((50, 95), "Telepon: (021) 8989-1234  |  Email: delivery@elektronikajaya.co.id", fill="#64748b")
    draw.line([25, 130, 875, 130], fill="#0f172a", width=2)

    # Title & Doc Info
    draw.text((320, 155), "SURAT JALAN PENGIRIMAN", fill="#0f172a")
    draw.text((350, 185), "No: SJ-2026-0819-094", fill="#2563eb")

    # Meta Info Section
    draw.rectangle([50, 225, 850, 315], fill="#ffffff", outline="#cbd5e1", width=1)
    draw.text((65, 240), "Tanggal Pengiriman : 19 Agustus 2026", fill="#1e293b")
    draw.text((65, 265), "Penerima (Tujuan)  : Gudang Utama PT. Warehouse Nusantara", fill="#1e293b")
    draw.text((65, 290), "Armada Kendaraan   : Truk Isuzu Box B-9812-XYZ (Driver: Bambang)", fill="#1e293b")

    draw.text((550, 240), "PO Reff  : PO-RESTOCK-2026-08", fill="#475569")
    draw.text((550, 265), "Gudang   : Sektor A-1 (Electronics)", fill="#475569")
    draw.text((550, 290), "Status   : Pengiriman Resmi", fill="#059669")

    # Table Header
    draw.rectangle([50, 345, 850, 385], fill="#f1f5f9", outline="#cbd5e1")
    draw.text((65, 357), "No", fill="#334155")
    draw.text((105, 357), "Kode SKU", fill="#334155")
    draw.text((240, 357), "Nama Item Barang & Spesifikasi", fill="#334155")
    draw.text((610, 357), "Qty Fisik", fill="#334155")
    draw.text((730, 357), "Satuan", fill="#334155")

    # Table Rows matching DuckDB
    items = [
        ("1", "ITM-001", "Microcontroller STM32F401 Development Board", "76", "pcs", "Packing Anti-Statik Utuh"),
        ("2", "ITM-002", "ESP32-WROOM-32D Module SMD WiFi BLE", "52", "pcs", "Tape Reel Tersegel"),
        ("3", "ITM-003", "Thermal Paste Arctic MX-4 4g High Performance", "33", "tube", "Dus packing aman"),
        ("4", "ITM-004", "Cardboard Box 30x20x15cm Double Wall", "190", "pcs", "Bandel karton 10x19"),
        ("5", "ITM-005", "Bubble Wrap Roll 50m x 50cm Premium", "17", "roll", "Plastik bening utuh")
    ]

    y = 395
    for item in items:
        draw.line([50, y + 42, 850, y + 42], fill="#e2e8f0", width=1)
        draw.text((65, y + 8), item[0], fill="#0f172a")
        draw.text((105, y + 8), item[1], fill="#2563eb")
        draw.text((240, y + 2), item[2], fill="#0f172a")
        draw.text((240, y + 22), f"Kondisi: {item[5]}", fill="#64748b")
        draw.text((630, y + 8), item[3], fill="#0f172a")
        draw.text((735, y + 8), item[4], fill="#475569")
        y += 52

    # Summary box
    draw.rectangle([50, 740, 850, 810], fill="#f8fafc", outline="#e2e8f0")
    draw.text((65, 755), "Catatan Khusus Penerimaan:", fill="#334155")
    draw.text((65, 780), "Barang telah diverifikasi fisik dan kuantitas sesuai dengan Purchase Requisition resmi.", fill="#475569")

    # Signatures
    draw.rectangle([70, 850, 290, 1010], outline="#cbd5e1", fill="#ffffff")
    draw.text((95, 865), "Pengirim / Supir,", fill="#475569")
    draw.text((95, 975), "( Bambang Supriyadi )", fill="#0f172a")
    draw.text((95, 992), "Tgl: 19/08/2026", fill="#94a3b8")

    draw.rectangle([590, 850, 830, 1010], outline="#cbd5e1", fill="#ffffff")
    draw.text((615, 865), "Petugas Penerima Gudang,", fill="#475569")
    draw.text((615, 975), "( Muhammad Daffa )", fill="#0f172a")
    draw.text((615, 992), "Tgl: 19/08/2026", fill="#94a3b8")

    # Footer note
    draw.text((50, 1090), "Dokumen Resmi Pengiriman - AutoRestock Agent Enterprise Verification", fill="#94a3b8")

    out_path = SAMPLES_DIR / "surat_jalan_resmi_pengiriman.png"
    img.save(out_path, quality=95)
    print(f"Created: {out_path}")


def create_sample_kartu_stok():
    img = Image.new("RGB", (900, 1150), color="#FFFFFF")
    draw = ImageDraw.Draw(img)

    # Frame border
    draw.rectangle([25, 25, 875, 1125], outline="#b45309", width=2)
    draw.rectangle([28, 28, 872, 1122], outline="#fef3c7", width=1)

    # Header Card
    draw.rectangle([25, 25, 875, 125], fill="#fffbeb")
    draw.text((50, 45), "KARTU PENGHITUNGAN STOK FISIK GUDANG (STOCK OPNAME)", fill="#92400e")
    draw.text((50, 72), "Divisi Logistik & Manajemen Inventaris - PT. Warehouse Nusantara", fill="#78350f")
    draw.text((50, 95), "Audit Berkala: Mingguan Sektor B (Electronics, Consumables & Packaging)", fill="#92400e")
    draw.line([25, 125, 875, 125], fill="#b45309", width=2)

    # Meta Details
    draw.rectangle([50, 150, 850, 240], fill="#ffffff", outline="#fde68a")
    draw.text((65, 165), "No. Dokumen     : OPNAME-2026-0819", fill="#0f172a")
    draw.text((65, 190), "Tanggal Audit   : 19 Agustus 2026 (Pukul 09:30 WIB)", fill="#0f172a")
    draw.text((65, 215), "Petugas Auditor : Agus Setiawan (Warehouse Lead Inspector)", fill="#0f172a")

    draw.text((550, 165), "Lokasi  : Sektor A & B Gudang", fill="#475569")
    draw.text((550, 190), "Siklus  : Stock Opname Q3", fill="#475569")
    draw.text((550, 215), "Status  : Fisik Diverifikasi", fill="#b45309")

    # Table Header
    draw.rectangle([50, 265, 850, 305], fill="#fef3c7", outline="#fde68a")
    draw.text((65, 277), "No", fill="#92400e")
    draw.text((105, 277), "Kode SKU", fill="#92400e")
    draw.text((240, 277), "Deskripsi Item Barang Fisik", fill="#92400e")
    draw.text((560, 277), "Stok Fisik", fill="#92400e")
    draw.text((680, 277), "Status / Catatan Lapangan", fill="#92400e")

    # Table Rows matching DuckDB
    items = [
        ("1", "ITM-001", "Microcontroller STM32F401", "12 pcs", "KRITIS (Batas min 50 pcs, sisa 12)"),
        ("2", "ITM-002", "ESP32-WROOM-32D Module", "8 pcs", "KRITIS (Batas min 40 pcs, sisa 8)"),
        ("3", "ITM-003", "Thermal Paste Arctic MX-4 4g", "5 tube", "KRITIS (Batas min 25 tube, sisa 5)"),
        ("4", "ITM-004", "Cardboard Box 30x20x15cm", "35 pcs", "KRITIS (Batas min 150 pcs, sisa 35)"),
        ("5", "ITM-005", "Bubble Wrap Roll 50m x 50cm", "4 roll", "KRITIS (Batas min 15 roll, sisa 4)")
    ]

    y = 315
    for item in items:
        draw.line([50, y + 42, 850, y + 42], fill="#fef3c7", width=1)
        draw.text((65, y + 10), item[0], fill="#0f172a")
        draw.text((105, y + 10), item[1], fill="#b45309")
        draw.text((240, y + 10), item[2], fill="#0f172a")
        draw.text((570, y + 10), item[3], fill="#dc2626")
        draw.text((680, y + 10), item[4], fill="#475569")
        y += 52

    # Summary
    draw.rectangle([50, 640, 850, 750], fill="#fffbeb", outline="#fde68a")
    draw.text((65, 660), "Hasil Rekomendasi Petugas Lapangan:", fill="#92400e")
    draw.text((65, 685), "1. Ke-5 barang di atas berada di bawah safety threshold dan membutuhkan Purchase Requisition darurat.", fill="#475569")
    draw.text((65, 710), "2. Data fisik ini siap disinkronisasikan ke DuckDB untuk memicu Multi-Agent AutoRestock.", fill="#475569")

    # Signatures
    draw.rectangle([70, 830, 290, 990], outline="#fde68a", fill="#ffffff")
    draw.text((95, 845), "Petugas Penghitung Lapangan,", fill="#475569")
    draw.text((95, 955), "( Agus Setiawan )", fill="#0f172a")

    draw.rectangle([590, 830, 830, 990], outline="#fde68a", fill="#ffffff")
    draw.text((615, 845), "Kepala Gudang Logistik,", fill="#475569")
    draw.text((615, 955), "( Hendra Kusuma )", fill="#0f172a")

    draw.text((50, 1090), "Dokumen Hasil Penghitungan Fisik Gudang - Valid untuk Restock Otomatis", fill="#94a3b8")

    out_path = SAMPLES_DIR / "kartu_stok_opname_lapangan.png"
    img.save(out_path, quality=95)
    print(f"Created: {out_path}")


if __name__ == "__main__":
    create_sample_surat_jalan()
    create_sample_kartu_stok()
