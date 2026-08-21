"""
Sample Document Generator for AutoRestock-V2
Creates realistic synthetic warehouse document images (Surat Jalan, Kartu Stok, Faktur) for testing.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from core.config import settings


def create_document_image(
    doc_title: str,
    doc_number: str,
    date_str: str,
    company_from: str,
    company_to: str,
    items: list,
    output_filename: str
):
    w, h = 850, 1100
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("arialbd.ttf", 20)
        bold_font = ImageFont.truetype("arialbd.ttf", 13)
        font = ImageFont.truetype("arial.ttf", 12)
        mono_font = ImageFont.truetype("cour.ttf", 12)
    except Exception:
        title_font = font = bold_font = mono_font = ImageFont.load_default()

    # Border
    draw.rectangle([(20, 20), (w - 20, h - 20)], outline=(200, 200, 200), width=1)

    # Header
    draw.text((40, 40), company_from.upper(), fill=(15, 23, 42), font=title_font)
    draw.text((40, 68), "Kawasan Industri Terpadu, Jakarta | Telp: (021) 500-1234", fill=(100, 116, 139), font=font)
    draw.line([(40, 95), (w - 40, 95)], fill=(15, 23, 42), width=2)

    # Document Title Block
    draw.text((w // 2 - 80, 110), doc_title.upper(), fill=(15, 23, 42), font=title_font)
    draw.text((w // 2 - 60, 138), f"No: {doc_number}", fill=(37, 99, 235), font=bold_font)

    # Meta Info
    draw.text((40, 170), f"Kepada Yth: {company_to}", fill=(30, 41, 59), font=bold_font)
    draw.text((40, 190), "Alamat: Gudang Pusat Distribusi", fill=(100, 116, 139), font=font)
    draw.text((w - 240, 170), f"Tanggal: {date_str}", fill=(30, 41, 59), font=font)
    draw.text((w - 240, 190), "Status: Inbound Delivery", fill=(30, 41, 59), font=font)

    # Table Header
    y_start = 230
    draw.rectangle([(40, y_start), (w - 40, y_start + 30)], fill=(241, 245, 249), outline=(203, 213, 225))
    draw.text((50, y_start + 8), "No", fill=(15, 23, 42), font=bold_font)
    draw.text((90, y_start + 8), "Deskripsi Barang / Material", fill=(15, 23, 42), font=bold_font)
    draw.text((450, y_start + 8), "Jumlah", fill=(15, 23, 42), font=bold_font)
    draw.text((550, y_start + 8), "Satuan", fill=(15, 23, 42), font=bold_font)
    draw.text((650, y_start + 8), "Catatan Gudang", fill=(15, 23, 42), font=bold_font)

    # Table Rows
    curr_y = y_start + 30
    for idx, it in enumerate(items):
        draw.rectangle([(40, curr_y), (w - 40, curr_y + 40)], outline=(226, 232, 240))
        draw.text((50, curr_y + 12), str(idx + 1), fill=(30, 41, 59), font=font)
        draw.text((90, curr_y + 12), it["name"], fill=(15, 23, 42), font=bold_font)
        draw.text((450, curr_y + 12), str(it["qty"]), fill=(15, 23, 42), font=bold_font)
        draw.text((550, curr_y + 12), it["unit"], fill=(100, 116, 139), font=font)
        draw.text((650, curr_y + 12), it.get("note", "Lolos QC"), fill=(22, 101, 52), font=font)
        curr_y += 40

    # Signature Block
    curr_y += 80
    draw.text((80, curr_y), "Diterima Oleh (Gudang):", fill=(71, 85, 105), font=font)
    draw.text((w - 260, curr_y), "Diserahkan Oleh (Driver):", fill=(71, 85, 105), font=font)

    curr_y += 70
    draw.line([(80, curr_y), (220, curr_y)], fill=(148, 163, 184), width=1)
    draw.line([(w - 260, curr_y), (w - 120, curr_y)], fill=(148, 163, 184), width=1)
    draw.text((80, curr_y + 6), "(Petugas Logistik)", fill=(100, 116, 139), font=font)
    draw.text((w - 260, curr_y + 6), "(Pengemudi Ekspedisi)", fill=(100, 116, 139), font=font)

    # Save to samples directory
    out_dir = settings.DATA_DIR / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_path = out_dir / output_filename
    img.save(str(save_path))
    print(f"Generated sample asset: {save_path}")
    return str(save_path)


def generate_all_samples():
    print("Generating synthetic sample warehouse assets...")

    # 1. Surat Jalan
    create_document_image(
        doc_title="Surat Jalan Pengiriman",
        doc_number="SJ/2026/08/8821",
        date_str="2026-08-20",
        company_from="PT Sumber Alfaria Distribusi",
        company_to="PT Retail Logistik Nusantara",
        items=[
            {"name": "Minyak Goreng Bimoli Klasik 2 Liter Pouch", "qty": 30, "unit": "pouch", "note": "Kondisi Baik"},
            {"name": "Beras Setra Ramos Premium 5 Kg", "qty": 25, "unit": "sak", "note": "Kondisi Baik"},
            {"name": "Air Mineral Aqua Botol 600ml (Karton 24 btl)", "qty": 20, "unit": "karton", "note": "Kondisi Baik"}
        ],
        output_filename="surat_jalan_inbound.png"
    )

    # 2. Kartu Stok
    create_document_image(
        doc_title="Kartu Stok Gudang Fisik",
        doc_number="KS/WH-01/104",
        date_str="2026-08-20",
        company_from="Gudang Sentral Retailindo",
        company_to="Audit Logistik Internal",
        items=[
            {"name": "Minyak Goreng Bimoli Klasik 2 Liter Pouch", "qty": 12, "unit": "pouch", "note": "Selisih Tercatat"},
            {"name": "Beras Setra Ramos Premium 5 Kg", "qty": 10, "unit": "sak", "note": "Selisih Tercatat"}
        ],
        output_filename="kartu_stok_warehouse.png"
    )

    # 3. Faktur Pembelian
    create_document_image(
        doc_title="Faktur Pembelian & Tagihan",
        doc_number="INV/202608/4419",
        date_str="2026-08-20",
        company_from="PT Indofood CBP Sukses Makmur Tbk",
        company_to="PT Retail Logistik Nusantara",
        items=[
            {"name": "Indomie Mi Instan Goreng Spesial (Karton 40 pcs)", "qty": 40, "unit": "karton", "note": "Faktur Resmi"},
            {"name": "Kopi Kapal Api Special Mix 20x25gr", "qty": 20, "unit": "pack", "note": "Faktur Resmi"}
        ],
        output_filename="faktur_pembelian.png"
    )


if __name__ == "__main__":
    generate_all_samples()
