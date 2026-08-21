"""
Model Context Protocol (MCP) Server Tools
Provides tool definitions for external agent orchestrators to interact with AutoRestock-V2.
"""

from typing import Dict, Any, List, Optional
from database.db import db
from agents.workflow import workflow
from core.schemas import PRStatus


async def query_inventory_tool(category: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    """Tool: Returns inventory catalog items with current stock, thresholds, and suppliers."""
    items = db.get_items(category=category, search=search)
    return [it.model_dump() for it in items]


async def trigger_restock_prompt_tool(prompt: str, auto_execute: bool = True) -> Dict[str, Any]:
    """Tool: Processes a natural language restock command and creates Purchase Requisitions."""
    result = await workflow.execute_prompt_restock(prompt, auto_execute=auto_execute)
    return {
        "status": result.get("status"),
        "prs_created": len(result.get("generated_prs", [])),
        "message": result.get("message")
    }


async def get_pending_approvals_tool() -> List[Dict[str, Any]]:
    """Tool: Fetches all Purchase Requisitions waiting for managerial approval."""
    prs = db.get_purchase_requisitions(status="pending_approval")
    return [p.model_dump() for p in prs]


async def approve_pr_tool(pr_number: str, approver_name: str, notes: Optional[str] = None) -> Dict[str, Any]:
    """Tool: Approves a pending Purchase Requisition."""
    updated = db.update_pr_status(pr_number=pr_number, status=PRStatus.APPROVED, approver_name=approver_name, notes=notes)
    return {"status": "success" if updated else "failed", "pr_number": pr_number}


async def audit_warehouse_doc_tool(file_path: str) -> Dict[str, Any]:
    """Tool: Ingests and audits a warehouse document file path."""
    result = await workflow.execute_document_ingest(file_path)
    return {
        "status": result.get("status"),
        "discrepancies_count": result.get("discrepancy_report").total_discrepancies if result.get("discrepancy_report") else 0,
        "prs_created": len(result.get("generated_prs", []))
    }
