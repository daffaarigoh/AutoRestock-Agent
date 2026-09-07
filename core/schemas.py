from datetime import datetime

from pydantic import BaseModel, Field




from agents.state import PurchaseRequisition, RestockItem

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
    tenant_id: str = "ALL"


# Canonical schema aliases ensuring unified Pydantic contracts across system
PurchaseItemRequest = RestockItem
PurchaseRequisitionDoc = PurchaseRequisition


