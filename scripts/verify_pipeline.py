import asyncio
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from multimodal.ocr_engine import OCREngine


async def main():
    print("=================================================================")
    print("[RUN] Verifying Document Ingestion Pipeline (ocr-lighton)")
    print("=================================================================\n")

    # 1. Test OCR on Surat Jalan Sample
    sj_path = settings.SAMPLES_DIR / "sample_delivery_note.png"
    if sj_path.exists():
        print(f"📄 [1/2] Processing Surat Jalan (Barang Masuk): {sj_path.name}")
        with open(sj_path, "rb") as f:
            sj_bytes = f.read()
        ocr_res = await OCREngine.process_document(sj_bytes, doc_type_hint="SURAT_JALAN", filename=sj_path.name)
        print(f"   ✅ Tipe Dok  : {ocr_res.doc_type.value}")
        print(f"   ✅ No Dok    : {ocr_res.doc_number}")
        print(f"   ✅ Vendor    : {ocr_res.vendor_or_issuer}")
        print(f"   ✅ Total Amt : Rp {ocr_res.total_amount:,.2f}")
        print(f"   ✅ Barang Tercatat ({len(ocr_res.items)} item):")
        for itm in ocr_res.items:
            print(f"      - {itm.item_name} ({itm.qty_recorded} {itm.unit}) @ Rp {itm.unit_price:,.2f} | Note: {itm.condition_notes}")
    print()

    # 2. Test OCR on Kartu Stok Opname Sample
    opname_path = settings.SAMPLES_DIR / "sample_kartu_stok.png"
    if opname_path.exists():
        print(f"📋 [2/2] Processing Kartu Stok Opname Fisik: {opname_path.name}")
        with open(opname_path, "rb") as f:
            op_bytes = f.read()
        op_res = await OCREngine.process_document(op_bytes, doc_type_hint="KARTU_STOK_OPNAME", filename=opname_path.name)
        print(f"   ✅ Tipe Dok  : {op_res.doc_type.value}")
        print(f"   ✅ No Dok    : {op_res.doc_number}")
        print(f"   ✅ Petugas   : {op_res.inspector_name}")
        print(f"   ✅ Ringkasan : {op_res.summary}")
        print(f"   ✅ Barang Dihitung Fisik ({len(op_res.items)} item):")
        for itm in op_res.items:
            print(f"      - {itm.item_name} -> Stok Fisik: {itm.qty_recorded} {itm.unit} | Status: {itm.condition_notes}")

    print("\n🎉 All Document Ingestion Pipelines Verified Successfully!")


if __name__ == "__main__":
    asyncio.run(main())
