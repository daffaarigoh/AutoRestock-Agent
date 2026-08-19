import logging
from typing import Optional
from core.llm_client import gateway
from core.schemas import DocumentType, OCRDocumentItem, OCRDocumentResult

logger = logging.getLogger(__name__)


class OCREngine:
    """
    Ingests scanned physical documents:
    1. Surat Jalan / Delivery Notes (Barang Masuk)
    2. Kartu Stok Opname Fisik (Penghitungan Stok Fisik Manual)
    3. Invoices / Faktur Pembelian

    Powered by 'ocr-lighton'.
    """

    @classmethod
    async def process_document(
        cls,
        image_bytes: bytes,
        doc_type_hint: str = "SURAT_JALAN",
        filename: Optional[str] = "document.jpg"
    ) -> OCRDocumentResult:
        """
        Parses document image into validated OCRDocumentResult schema.
        """
        raw_data = await gateway.ocr_document_extraction(image_bytes, doc_type_hint=doc_type_hint)

        items_list = []
        for raw_item in raw_data.get("items", []):
            items_list.append(
                OCRDocumentItem(
                    line_no=raw_item.get("line_no", 1),
                    item_name=raw_item.get("item_name", "Unknown Item"),
                    sku=raw_item.get("sku", "N/A"),
                    qty_recorded=int(raw_item.get("qty_recorded", raw_item.get("qty_received", 0))),
                    unit=raw_item.get("unit", "pcs"),
                    unit_price=float(raw_item.get("unit_price", 0.0)),
                    total_price=float(raw_item.get("total_price", 0.0)),
                    condition_notes=raw_item.get("condition_notes", "Baik"),
                )
            )

        doc_type_str = raw_data.get("doc_type", doc_type_hint).upper()
        try:
            doc_type_enum = DocumentType(doc_type_str)
        except ValueError:
            doc_type_enum = DocumentType.SURAT_JALAN

        result = OCRDocumentResult(
            doc_type=doc_type_enum,
            doc_number=raw_data.get("doc_number", "DOC-UNKNOWN"),
            vendor_or_issuer=raw_data.get("vendor_or_issuer", "Unknown"),
            date_recorded=raw_data.get("date_recorded", "2026-08-19"),
            inspector_name=raw_data.get("inspector_name", "Petugas Gudang"),
            items=items_list,
            total_amount=float(raw_data.get("total_amount", 0.0)),
            extraction_confidence=float(raw_data.get("extraction_confidence", 0.96)),
            summary=raw_data.get("summary", "Dokumen fisik berhasil diekstrak."),
        )

        return result
