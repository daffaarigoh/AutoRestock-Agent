from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field




# -------------------------------------------------------------
# Multi-Agent Inventory & Procurement Schemas (Shared Contract)
# -------------------------------------------------------------

class InventoryItem(BaseModel):
    item_id: str
    name: str
    category: str
    current_stock: int
    min_threshold: int
    max_threshold: int
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
    items: list[PurchaseItemRequest]
    total_budget: float
    auditor_status: str = "PASSED"              # PASSED | REVISED
    auditor_notes: str = "Compliance & budget verified by nemotron-35."
    pdf_path: str | None = None
    status: str = "PENDING"                     # PENDING | APPROVED | REJECTED
    tenant_id: str = "ALL"


