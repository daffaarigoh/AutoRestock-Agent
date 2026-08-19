from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# -------------------------------------------------------------
# Document & OCR Ingestion Schemas (Powered by ocr-lighton)
# -------------------------------------------------------------

class DocumentType(str, Enum):
    SURAT_JALAN = "SURAT_JALAN"
    INVOICE = "INVOICE"
    KARTU_STOK_OPNAME = "KARTU_STOK_OPNAME"


class OCRDocumentItem(BaseModel):
    line_no: int
    item_name: str
    sku: Optional[str] = "N/A"
    qty_recorded: int = Field(default=0, description="Quantity recorded on the physical document")
    unit: str = "pcs"
    unit_price: Optional[float] = 0.0
    total_price: Optional[float] = 0.0
    condition_notes: Optional[str] = "Baik / Sesuai"

    @property
    def qty_received(self) -> int:
        return self.qty_recorded


class OCRDocumentResult(BaseModel):
    doc_type: DocumentType = DocumentType.SURAT_JALAN
    doc_number: str
    vendor_or_issuer: str
    date_recorded: str
    inspector_name: Optional[str] = "Petugas Gudang"
    items: List[OCRDocumentItem]
    total_amount: float = 0.0
    extraction_confidence: float = 0.96
    summary: str = "Dokumen fisik berhasil diekstrak dan siap disinkronkan ke database."

    @property
    def vendor_name(self) -> str:
        return self.vendor_or_issuer


# -------------------------------------------------------------
# Visual Shelf Audit Schemas (Powered by qwen-35b-vision)
# -------------------------------------------------------------

class StockStatus(str, Enum):
    CRITICAL_EMPTY = "CRITICAL_EMPTY"
    LOW = "LOW"
    NORMAL = "NORMAL"
    DAMAGED = "DAMAGED"


class BoundingBox(BaseModel):
    ymin: float = 0.0
    xmin: float = 0.0
    ymax: float = 1.0
    xmax: float = 1.0


class DetectedShelfItem(BaseModel):
    slot_id: str
    item_label: str
    status: StockStatus = StockStatus.NORMAL
    confidence: float = 0.9
    bbox: BoundingBox
    notes: Optional[str] = None


class VisionAuditResult(BaseModel):
    image_filename: str = "shelf.jpg"
    total_slots_scanned: int
    empty_slots_count: int
    low_stock_count: int
    detected_items: List[DetectedShelfItem]
    annotated_image_url: Optional[str] = None
    audit_summary: str = "Visual shelf scan completed."


# -------------------------------------------------------------
# Multi-Agent Inventory & Procurement Schemas (Shared Contract)
# -------------------------------------------------------------

class InventoryItem(BaseModel):
    item_id: str
    name: str
    category: str
    current_stock: int
    min_threshold: int
    unit: str = "pcs"
    avg_daily_usage: float
    lead_time_days: int
    unit_price: float


class PurchaseItemRequest(BaseModel):
    item_id: str
    name: str
    reorder_qty: int
    unit: str = "pcs"
    vendor_id: str
    vendor_name: str
    unit_price: float
    total_price: float
    reason: str


class PurchaseRequisitionDoc(BaseModel):
    pr_number: str
    created_at: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    items: List[PurchaseItemRequest]
    total_budget: float
    auditor_status: str = "PASSED"              # PASSED | REVISED
    auditor_notes: str = "Compliance & budget verified by nemotron-35."
    pdf_path: Optional[str] = None
    status: str = "PENDING"                     # PENDING | APPROVED | REJECTED


