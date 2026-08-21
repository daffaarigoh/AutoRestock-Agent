"""
Multi-Agent Workflow State Definitions
Defines state schemas passed between autonomous agent nodes.
"""

from typing import TypedDict, List, Dict, Any, Optional
from core.schemas import (
    ExtractedDocument,
    DiscrepancyReport,
    PurchaseRequisition,
    InventoryItem,
    ParsedPromptIntent
)


class RestockAgentState(TypedDict, total=False):
    # Inputs
    file_path: Optional[str]
    user_prompt: Optional[str]
    auto_execute: bool
    trigger_source: str  # "document_upload", "prompt_command", "scheduled_audit", "manual_trigger"
    
    # Intermediate State
    extracted_doc: Optional[ExtractedDocument]
    annotated_image_path: Optional[str]
    discrepancy_report: Optional[DiscrepancyReport]
    parsed_intent: Optional[ParsedPromptIntent]
    restock_candidates: List[Dict[str, Any]]
    
    # Outputs
    generated_prs: List[PurchaseRequisition]
    requires_approval: bool
    status: str
    message: str
    logs: List[str]
    error: Optional[str]
