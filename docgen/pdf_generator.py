import logging
from pathlib import Path

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
        output_filename: str | None = None
    ) -> Path:
        """
        Compiles Typst template into a formal PDF Purchase Requisition document.
        """
        if not output_filename:
            output_filename = f"{pr.pr_number.replace('-', '_')}.pdf"

        output_path = settings.DOCUMENTS_DIR / output_filename
        settings.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

        from docgen.compiler import generate_pr_pdf
        payload = pr.model_dump()
        generated_file = generate_pr_pdf(payload, output_path=output_path)
        return Path(generated_file)

pdf_generator = TypstPDFGenerator()
