import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont
from core.config import settings


def generate_sample_delivery_note():
    """
    Creates a realistic delivery note graphic for OCR testing.
    """
    img = Image.new("RGB", (800, 950), color="#FFFFFF")
    draw = ImageDraw.Draw(img)

    # Border
    draw.rectangle([20, 20, 780, 930], outline="#000000", width=2)

    # Header
    draw.text((40, 50), "PT. MITRA LOGISTIK UTAMA", fill="#1E3A8A")
    draw.text((40, 75), "Jl. Kawasan Industri No. 45, Cikarang Barat", fill="#4B5563")
    draw.text((40, 95), "Telp: (021) 8989-1234 | Email: info@mitralogistik.co.id", fill="#4B5563")
    draw.line([40, 125, 760, 125], fill="#1E3A8A", width=3)

    # Title
    draw.text((290, 145), "SURAT JALAN PENGIRIMAN", fill="#111827")
    draw.text((320, 170), "No: SJ-2026-0819-094", fill="#374151")

    # Meta
    draw.text((40, 210), "Tanggal Pengiriman : 19 Agustus 2026", fill="#111827")
    draw.text((40, 235), "Penerima           : Gudang Utama PT. Warehouse Nusantara", fill="#111827")
    draw.text((40, 260), "Ekspedisi          : Truk Internal Armada B-9812-XYZ", fill="#111827")

    # Table Header
    draw.rectangle([40, 300, 760, 335], fill="#E5E7EB", outline="#9CA3AF")
    draw.text((50, 310), "No", fill="#111827")
    draw.text((90, 310), "Kode SKU", fill="#111827")
    draw.text((250, 310), "Nama Barang & Spesifikasi", fill="#111827")
    draw.text((560, 310), "Qty Diterima", fill="#111827")
    draw.text((680, 310), "Satuan", fill="#111827")

    # Table Rows
    items = [
        ("1", "SKU-BAUT-M8", "Baut Baja Hitam M8 x 50mm Grade 8.8", "500", "pcs"),
        ("2", "SKU-OLI-ISO68", "Oli Hidrolik ISO VG 68 Drum 20L", "4", "pail"),
        ("3", "SKU-LAKBAN-2IN", "Lakban Coklat Heavy Duty 2 Inch 100m", "50", "roll"),
    ]

    y = 345
    for item in items:
        draw.line([40, y + 25, 760, y + 25], fill="#E5E7EB", width=1)
        draw.text((50, y), item[0], fill="#111827")
        draw.text((90, y), item[1], fill="#1F2937")
        draw.text((250, y), item[2], fill="#111827")
        draw.text((580, y), item[3], fill="#111827")
        draw.text((680, y), item[4], fill="#111827")
        y += 40

    # Signatures
    draw.text((80, 760), "Pengirim / Driver,", fill="#374151")
    draw.text((80, 840), "( Bambang Supriyadi )", fill="#111827")

    draw.text((550, 760), "Petugas Penerima Gudang,", fill="#374151")
    draw.text((550, 840), "( Muhammad Daffa )", fill="#111827")

    out_file = settings.SAMPLES_DIR / "sample_delivery_note.png"
    img.save(out_file)
    print(f"Created: {out_file}")


def generate_sample_stock_opname_card():
    """
    Creates a realistic physical stock opname card for OCR testing.
    """
    img = Image.new("RGB", (800, 950), color="#FEFCE8") # Light yellow physical card
    draw = ImageDraw.Draw(img)

    # Border
    draw.rectangle([20, 20, 780, 930], outline="#854D0E", width=2)

    # Header
    draw.text((40, 50), "KARTU PENGHITUNGAN STOK FISIK (STOCK OPNAME)", fill="#854D0E")
    draw.text((40, 75), "Lokasi Gudang: Sektor B - Rak Heavy Equipment", fill="#713F12")
    draw.line([40, 105, 760, 105], fill="#CA8A04", width=2)

    # Meta
    draw.text((40, 130), "No. Dokumen : OPNAME-2026-0819", fill="#111827")
    draw.text((40, 155), "Tanggal Cek : 19 Agustus 2026", fill="#111827")
    draw.text((40, 180), "Petugas Cek : Agus Setiawan (Warehouse Officer)", fill="#111827")

    # Table Header
    draw.rectangle([40, 220, 760, 255], fill="#FEF08A", outline="#CA8A04")
    draw.text((50, 230), "No", fill="#111827")
    draw.text((90, 230), "Kode SKU", fill="#111827")
    draw.text((250, 230), "Nama Barang Fisik", fill="#111827")
    draw.text((530, 230), "Stok Fisik", fill="#111827")
    draw.text((630, 230), "Kondisi / Catatan", fill="#111827")

    # Table Rows
    items = [
        ("1", "SKU-BAUT-M8", "Baut Baja Hitam M8 x 50mm", "12 pcs", "KRITIS (Menipis tajam)"),
        ("2", "SKU-OLI-ISO68", "Oli Hidrolik ISO VG 68 20L", "1 pail", "Tersisa 1 drum di lantai"),
        ("3", "SKU-LAKBAN-2IN", "Lakban Coklat 2 Inch", "3 roll", "Hampir habis di rak B2"),
    ]

    y = 265
    for item in items:
        draw.line([40, y + 30, 760, y + 30], fill="#FDE047", width=1)
        draw.text((50, y + 5), item[0], fill="#111827")
        draw.text((90, y + 5), item[1], fill="#1F2937")
        draw.text((250, y + 5), item[2], fill="#111827")
        draw.text((540, y + 5), item[3], fill="#DC2626")
        draw.text((630, y + 5), item[4], fill="#111827")
        y += 45

    # Verification Note
    draw.rectangle([40, 500, 760, 580], fill="#FFFFFF", outline="#E2E8F0")
    draw.text((50, 515), "Catatan Khusus Pengawas:", fill="#1E3A8A")
    draw.text((50, 540), "Seluruh stok kritis di atas berada jauh di bawah safety threshold.", fill="#4B5563")

    # Signatures
    draw.text((80, 760), "Petugas Penghitung Lapangan,", fill="#374151")
    draw.text((80, 840), "( Agus Setiawan )", fill="#111827")

    draw.text((550, 760), "Kepala Gudang,", fill="#374151")
    draw.text((550, 840), "( Hendra Kusuma )", fill="#111827")

    out_file = settings.SAMPLES_DIR / "sample_kartu_stok.png"
    img.save(out_file)
    print(f"Created: {out_file}")


if __name__ == "__main__":
    generate_sample_delivery_note()
    generate_sample_stock_opname_card()
