import asyncio
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.telegram_bot import telegram_bot

from core.config import settings
from core.observability import tracer
from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
from docgen.pdf_generator import pdf_generator
from multimodal.ocr_engine import OCREngine


async def run_full_autonomous_cycle():
    print("==========================================================================")
    print("🚀 AUTORESTOCK-AGENT: END-TO-END AUTONOMOUS PROCUREMENT SIMULATION")
    print("==========================================================================\n")

    trace_id = "trace-demo-full-001"
    trace = tracer.start_trace(trace_id=trace_id)

    # -------------------------------------------------------------
    # Step 1: Document Ingestion (OCR LightOn)
    # -------------------------------------------------------------
    print("📂 [STEP 1/5] Ingesting Physical Stock Opname Card (ocr-lighton)...")
    span_ocr = tracer.start_span("span-1", "OCR-Ingestion", "ocr-lighton")
    
    opname_file = settings.SAMPLES_DIR / "sample_kartu_stok.png"
    if not opname_file.exists():
        print("   ⚠️ Sample card not found, please run scripts/generate_sample_assets.py first.")
        return

    with open(opname_file, "rb") as f:
        img_bytes = f.read()

    ocr_result = await OCREngine.process_document(img_bytes, doc_type_hint="KARTU_STOK_OPNAME")
    tracer.end_span(span_ocr, output_payload={"doc_number": ocr_result.doc_number}, tokens=180)

    print(f"   ✅ Dokumen: {ocr_result.doc_number} | Petugas: {ocr_result.inspector_name}")
    for itm in ocr_result.items:
        print(f"      • {itm.item_name} -> Stok Fisik: {itm.qty_recorded} {itm.unit} ({itm.condition_notes})")
    print()

    # -------------------------------------------------------------
    # Step 2: Multi-Agent Decision & Planning (qwen-35b)
    # -------------------------------------------------------------
    print("🧠 [STEP 2/5] Running Multi-Agent Procurement Planning (qwen-35b)...")
    span_plan = tracer.start_span("span-2", "Procurement-Planner", "qwen-35b")
    await asyncio.sleep(0.5)

    purchase_items = [
        PurchaseItemRequest(
            item_id="ITEM-BAUT-M8",
            name="Baut Baja Hitam M8 x 50mm Grade 8.8",
            reorder_qty=500,
            unit="pcs",
            vendor_id="VEND-001",
            vendor_name="PT. Sumber Makmur Fastener",
            unit_price=2500.0,
            total_price=1250000.0,
            reason="Stok fisik tersisa 12 pcs (di bawah threshold 100 pcs). Burn rate 25 pcs/hari."
        ),
        PurchaseItemRequest(
            item_id="ITEM-OLI-68",
            name="Oli Hidrolik ISO VG 68 Drum 20L",
            reorder_qty=4,
            unit="pail",
            vendor_id="VEND-002",
            vendor_name="PT. Pelumas Nusantara Jaya",
            unit_price=875000.0,
            total_price=3500000.0,
            reason="Stok tersisa 1 pail. Lead time supplier 3 hari kerja."
        )
    ]
    total_budget = sum(i.total_price for i in purchase_items)
    tracer.end_span(span_plan, output_payload={"reorder_count": len(purchase_items)}, tokens=320)

    print(f"   ✅ qwen-35b merekomendasikan pembelian 2 SKU dengan total: Rp {total_budget:,.2f}")
    for p in purchase_items:
        print(f"      • Pesan {p.reorder_qty} {p.unit} '{p.name}' via {p.vendor_name}")
    print()

    # -------------------------------------------------------------
    # Step 3: Compliance & Budget Auditing (nemotron-35)
    # -------------------------------------------------------------
    print("🛡️ [STEP 3/5] Compliance & Budget Auditing (nemotron-35)...")
    span_audit = tracer.start_span("span-3", "Compliance-Auditor", "nemotron-35")
    await asyncio.sleep(0.4)

    auditor_status = "PASSED"
    auditor_notes = "Audit lolos: Kuantitas restock sesuai kebutuhan 14 hari kerja dan masih dalam alokasi anggaran belanja gudang."
    tracer.end_span(span_audit, output_payload={"verdict": auditor_status}, tokens=190)

    print(f"   ✅ Verdict: {auditor_status}")
    print(f"   ✅ Catatan: {auditor_notes}\n")

    # -------------------------------------------------------------
    # Step 4: Typesetting Purchase Requisition PDF (Typst)
    # -------------------------------------------------------------
    print("📄 [STEP 4/5] Compiling Formal Purchase Requisition (Typst Engine)...")
    pr_doc = PurchaseRequisitionDoc(
        pr_number="PR-2026-0819-001",
        items=purchase_items,
        total_budget=total_budget,
        auditor_status=auditor_status,
        auditor_notes=auditor_notes,
        status="PENDING_APPROVAL"
    )

    pdf_path = pdf_generator.generate_purchase_requisition_pdf(pr_doc, output_filename="PR_2026_0819_001.pdf")
    print(f"   ✅ PDF Dokumen Resmi Terbit: {pdf_path.name} ({pdf_path.stat().st_size} bytes)\n")

    # -------------------------------------------------------------
    # Step 5: Human-In-The-Loop Approval (Telegram & Dashboard)
    # -------------------------------------------------------------
    print("📲 [STEP 5/5] Dispatching Human-In-The-Loop Approval Alert...")
    notify_res = await telegram_bot.send_restock_approval_request(pr_doc)
    print(f"   ✅ Status Notifikasi: {notify_res['status'].upper()}")
    print("   ✅ Simulasi Respon Manajer: Menekan tombol [ ✅ Approve PR ]...")
    
    pr_doc.status = "APPROVED"
    tracer.end_trace(trace, verdict="APPROVED")

    print("\n==========================================================================")
    print(f"🎉 SUKSES! Dokumen {pr_doc.pr_number} telah disetujui.")
    print(f"📊 Total Eksekusi Selesai: {trace.total_duration_ms:.1f}ms | Total Tokens: {trace.total_tokens_estimated}")
    print("🌐 Dashboard UI siap dibuka di: http://localhost:8000/")
    print("==========================================================================")


if __name__ == "__main__":
    asyncio.run(run_full_autonomous_cycle())
