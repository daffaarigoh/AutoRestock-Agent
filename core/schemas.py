"""
AutoRestock-V2 Data Schemas
Comprehensive Pydantic models for inventory, multimodal documents, agents, and restock operations.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class DocumentType(str, Enum):
    SURAT_JALAN = "surat_jalan"
    KARTU_STOK = "kartu_stok"
    FAKTUR_PEMBELIAN = "faktur_pembelian"
    PHYSICAL_AUDIT = "physical_audit"
    PURCHASE_ORDER = "purchase_order"
    UNKNOWN = "unknown"


class PRStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    FULFILLED = "fulfilled"


class DiscrepancySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Supplier(BaseModel):
    id: str
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    lead_time_days: int = 3
    rating: float = 4.8


class InventoryItem(BaseModel):
    sku: str
    name: str
    category: str
    current_stock: int
    min_stock: int
    max_stock: int
    safety_stock: int = 5
    unit: str = "pcs"
    unit_price: float = 0.0
    supplier_id: str
    supplier_name: Optional[str] = None
    lead_time_days: int = 3
    location_bin: str = "A-01-01"
    last_restocked_at: Optional[str] = None
    status: str = "normal"  # normal, low_stock, out_of_stock, overstocked


class InventoryUpdate(BaseModel):
    sku: str
    quantity_change: int
    transaction_type: str  # in, out, adjustment, audit
    reference_doc: Optional[str] = None
    notes: Optional[str] = None


class ExtractedLineItem(BaseModel):
    item_name: str
    sku_guess: Optional[str] = None
    quantity: int
    unit: str = "pcs"
    unit_price: float = 0.0
    total_price: float = 0.0
    confidence: float = 0.95
    bbox: Optional[List[int]] = None  # [x, y, width, height]


class ExtractedDocument(BaseModel):
    doc_type: DocumentType = DocumentType.SURAT_JALAN
    doc_number: str
    doc_date: str
    sender_supplier: Optional[str] = None
    recipient: Optional[str] = None
    line_items: List[ExtractedLineItem] = Field(default_factory=list)
    raw_text: Optional[str] = None
    confidence_score: float = 0.92
    source_file: Optional[str] = None
    annotated_file: Optional[str] = None


class DiscrepancyItem(BaseModel):
    sku: str
    item_name: str
    doc_quantity: int
    recorded_stock: int
    physical_count: Optional[int] = None
    diff_quantity: int
    severity: DiscrepancySeverity = DiscrepancySeverity.MEDIUM
    reason: str
    suggested_action: str


class DiscrepancyReport(BaseModel):
    doc_number: str
    doc_type: DocumentType
    discrepancies: List[DiscrepancyItem] = Field(default_factory=list)
    total_discrepancies: int = 0
    requires_manager_review: bool = False
    summary: str = ""


class PurchaseRequisitionItem(BaseModel):
    sku: str
    item_name: str
    quantity: int
    unit: str = "pcs"
    unit_price: float = 0.0
    total_price: float = 0.0
    current_stock: int = 0
    min_stock: int = 0
    reason: str = "Automatic restock threshold triggered"


class PurchaseRequisition(BaseModel):
    pr_number: str
    created_at: str
    supplier_id: str
    supplier_name: str
    items: List[PurchaseRequisitionItem] = Field(default_factory=list)
    subtotal: float = 0.0
    tax_rate: float = 0.11  # 11% PPN in Indonesia
    tax_amount: float = 0.0
    grand_total: float = 0.0
    status: PRStatus = PRStatus.PENDING_APPROVAL
    urgency: str = "NORMAL"  # LOW, NORMAL, HIGH, URGENT
    notes: Optional[str] = None
    pdf_path: Optional[str] = None
    approver_name: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    auto_approved: bool = False


class PromptRestockRequest(BaseModel):
    prompt: str = Field(..., description="Natural language prompt for restock or inventory query")
    auto_execute: bool = Field(True, description="Whether to automatically generate the PR")
    filter_category: Optional[str] = None
    supplier_preference: Optional[str] = None


class ParsedPromptIntent(BaseModel):
    intent_type: str = "restock"  # restock, add_item, update_stock, check_stock, audit_check, summary, notify_email, notify_telegram, sync_export
    target_skus: List[str] = Field(default_factory=list)
    target_categories: List[str] = Field(default_factory=list)
    target_supplier: Optional[str] = None
    quantity_specified: Optional[int] = None
    quantity_strategy: str = "auto_to_max"  # auto_to_max, fixed_amount, safety_buffer
    urgency: str = "NORMAL"
    reasoning: str = ""
    # n8n notification parameters
    notification_channel: Optional[str] = None  # "email", "telegram", "whatsapp"
    notification_recipient: Optional[str] = None
    notification_message: Optional[str] = None
    # Dynamic Item Creation / Stock Adjustment / Threshold / Delete / Category / UI parameters
    new_item_data: Optional[Dict[str, Any]] = None
    stock_adjustment_data: Optional[Dict[str, Any]] = None
    threshold_data: Optional[Dict[str, Any]] = None
    edit_item_data: Optional[Dict[str, Any]] = None
    delete_item_data: Optional[Dict[str, Any]] = None
    category_data: Optional[Dict[str, Any]] = None
    ui_action_data: Optional[Dict[str, Any]] = None
    approve_pr_data: Optional[Dict[str, Any]] = None
    financial_calc_data: Optional[Dict[str, Any]] = None


class PromptRestockResponse(BaseModel):
    status: str
    prompt: str
    parsed_intent: ParsedPromptIntent
    affected_items: List[Dict[str, Any]] = Field(default_factory=list)
    generated_prs: List[PurchaseRequisition] = Field(default_factory=list)
    action_type: str = "general"
    action_summary: str = ""
    message: str = ""
    logs: List[str] = Field(default_factory=list)


class ApprovalActionRequest(BaseModel):
    pr_number: str
    action: str = Field(..., description="'approve' or 'reject'")
    approver_name: str = "Manager Logistik"
    notes: Optional[str] = None


class DashboardStats(BaseModel):
    total_items: int = 0
    low_stock_items: int = 0
    out_of_stock_items: int = 0
    total_suppliers: int = 0
    pending_prs: int = 0
    approved_prs: int = 0
    rejected_prs: int = 0
    total_inventory_value_idr: float = 0.0
    total_pending_pr_value_idr: float = 0.0
    active_discrepancies: int = 0


class AgentLogEvent(BaseModel):
    timestamp: str
    step_name: str
    agent_name: str
    status: str  # info, success, warning, error, running
    message: str
    details: Optional[Dict[str, Any]] = None
