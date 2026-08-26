from typing import Any, TypedDict

from pydantic import BaseModel, Field


class RestockItem(BaseModel):
    item_id: str = Field(..., description="Unique item identifier")
    name: str = Field(..., description="Name of the item")
    category: str = Field("General", description="Item category")
    current_stock: int = Field(0, description="Current stock level in inventory")
    min_threshold: int = Field(0, description="Minimum safety threshold")
    reorder_qty: int = Field(..., description="Calculated reorder quantity")
    unit: str = Field("pcs", description="Unit of measurement (pcs, spool, roll, etc.)")
    vendor_id: str = Field("VND-001", description="ID of the matched vendor")
    vendor_name: str = Field(..., description="Name of the matched vendor")
    unit_price: float = Field(..., description="Unit price offered by vendor")
    total_price: float = Field(..., description="Total price = unit_price * reorder_qty")
    reason: str = Field("", description="Reasoning / justification for purchase")



class PurchaseRequisition(BaseModel):
    pr_number: str = Field(..., description="Unique PR document number e.g. PR-20260819-001")
    created_at: str = Field(..., description="ISO timestamp of creation")
    items: list[RestockItem] = Field(default_factory=list, description="List of restocked items")
    total_budget: float = Field(0.0, description="Total budget required for requisition")
    auditor_status: str = Field("PASSED", description="Auditor status: PASSED or REVISED")
    auditor_notes: str = Field("", description="Audit notes and compliance evaluation from auditor")
    pdf_path: str | None = Field(None, description="Path to generated Typst PDF document")
    status: str = Field("PENDING", description="Requisition status: PENDING | APPROVED | REJECTED")
    thread_id: str | None = Field(None, description="LangGraph execution thread identifier")



class AgentState(TypedDict, total=False):
    thread_id: str
    low_stock_items: list[dict[str, Any]]
    planned_items: list[RestockItem]
    total_budget: float
    auditor_status: str
    auditor_notes: str
    pr_document: PurchaseRequisition | None
    pdf_path: str | None
    approval_action: str | None      # "APPROVE" | "REJECT"
    approver_name: str | None
    approval_notes: str | None
    is_approved: bool
    logs: list[str]
