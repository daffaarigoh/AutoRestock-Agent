import json
import logging
from pathlib import Path
from typing import Optional

from core.config import settings
from core.schemas import PurchaseRequisitionDoc

logger = logging.getLogger(__name__)


class TypstPDFGenerator:
    """
    High-Speed PDF Generator using Typst typesetting engine (<50ms compilation).
    Includes resilient fallback rendering.
    """

    @classmethod
    def generate_purchase_requisition_pdf(
        cls,
        pr: PurchaseRequisitionDoc,
        output_filename: Optional[str] = None
    ) -> Path:
        """
        Compiles Typst template into a formal PDF Purchase Requisition document.
        """
        if not output_filename:
            output_filename = f"{pr.pr_number.replace('-', '_')}.pdf"

        output_path = settings.DOCUMENTS_DIR / output_filename
        settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

        from docgen.compiler import generate_pr_pdf
        try:
            payload = pr.model_dump()
            generated_file = generate_pr_pdf(payload, output_path=output_path)
            return Path(generated_file)
        except Exception as e:
            logger.warning(f"Typst compile exception: {e}. Using fallback renderer.")
            cls._render_fallback_pdf(pr, output_path)
            return output_path


    @classmethod
    def _render_fallback_pdf(cls, pr: PurchaseRequisitionDoc, output_path: Path):
        """
        Fallback renderer using PyMuPDF (fitz) or pure PDF generation.
        """
        try:
            import pymupdf
            doc = pymupdf.open()
            page = doc.new_page(width=595, height=842) # A4 points

            # Title & Header
            page.insert_text((50, 60), "PT. WAREHOUSE NUSANTARA", fontsize=14, fontname="helv", color=(0.1, 0.2, 0.5))
            page.insert_text((50, 80), "PURCHASE REQUISITION (PR)", fontsize=18, fontname="hebo", color=(0.1, 0.2, 0.5))
            page.insert_text((50, 105), f"Dokumen No: {pr.pr_number}  |  Tanggal: {pr.created_at}", fontsize=10)

            # Divider
            page.draw_line(pymupdf.Point(50, 115), pymupdf.Point(545, 115), color=(0.1, 0.2, 0.5), width=2)

            # Items Header
            page.insert_text((50, 145), "Daftar Item Barang Restock:", fontsize=12, fontname="hebo")
            y = 170
            for idx, item in enumerate(pr.items, start=1):
                page.insert_text((60, y), f"{idx}. {item.name}", fontsize=10, fontname="hebo")
                page.insert_text((75, y + 15), f"Qty: {item.reorder_qty} {item.unit}  |  Vendor: {item.vendor_name}", fontsize=9, color=(0.3, 0.3, 0.3))
                page.insert_text((420, y), f"Rp {item.total_price:,.2f}", fontsize=10, fontname="hebo", color=(0.1, 0.5, 0.2))
                y += 40

            # Total
            page.draw_line(pymupdf.Point(50, y + 10), pymupdf.Point(545, y + 10), color=(0.8, 0.8, 0.8), width=1)
            page.insert_text((350, y + 30), f"Total Biaya: Rp {pr.total_budget:,.2f}", fontsize=12, fontname="hebo", color=(0.1, 0.2, 0.5))

            # Audit Box
            page.draw_rect(pymupdf.Rect(50, y + 60, 545, y + 120), color=(0.2, 0.4, 0.8), fill=(0.95, 0.97, 1.0), width=1)
            page.insert_text((60, y + 80), f"Audit Kepatuhan ({pr.auditor_status}):", fontsize=10, fontname="hebo", color=(0.1, 0.3, 0.7))
            page.insert_text((60, y + 100), f"{pr.auditor_notes}", fontsize=8.5, color=(0.2, 0.2, 0.2))

            # Signatures
            page.insert_text((80, 750), "Dibuat Oleh: AutoRestock AI", fontsize=9)
            page.insert_text((380, 750), f"Status: {pr.status}", fontsize=9, fontname="hebo")

            doc.save(str(output_path))
            doc.close()
            logger.info(f"Fallback PDF generated at: {output_path}")
        except Exception as e:
            logger.error(f"Fallback PDF generation error: {e}")
            output_path.write_text(f"Purchase Requisition: {pr.pr_number}\nTotal: Rp {pr.total_budget}\nStatus: {pr.status}")


pdf_generator = TypstPDFGenerator()
