import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Fix console encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

import asyncio
import json

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.state import AgentState, PurchaseRequisition, RestockItem
from core.llm_client import ModelGateway
from database.db import get_db_connection
from docgen.compiler import generate_pr_pdf
from mcp_server.tools import get_best_vendors, get_low_stock_items

# Global in-memory checkpointer for thread persistence
memory_checkpointer = MemorySaver()


def record_orders_to_db(pr: PurchaseRequisition, status: str = "PENDING"):
    """Insert or update order records into DuckDB orders table."""

    conn = get_db_connection()
    try:
        update_params = []
        insert_params = []
        tenant_val = getattr(pr, "tenant_id", None) or "TENANT_A"

        for item in pr.items:
            order_id = f"ORD-{pr.pr_number}-{item.item_id}"
            existing = conn.execute("SELECT order_id FROM orders WHERE order_id = ?", [order_id]).fetchone()
            if existing:
                update_params.append((status, order_id))
            else:
                insert_params.append((
                    order_id, pr.pr_number, item.item_id, item.vendor_id,
                    item.reorder_qty, item.unit_price, item.total_price, status, tenant_val
                ))
        
        if update_params:
            conn.executemany("""
                UPDATE orders 
                SET status = ?
                WHERE order_id = ?;
            """, update_params)
            
        if insert_params:
            conn.executemany("""
                INSERT INTO orders (order_id, pr_number, item_id, vendor_id, quantity, unit_price, total_price, status, tenant_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
            """, insert_params)
    finally:
        conn.commit()
        conn.close()


def update_db_orders_status(pr_number: str, status: str):
    """Update all orders under a PR number to a new status (e.g. APPROVED, REJECTED) and update stock on APPROVE."""
    conn = get_db_connection()
    try:
        if status.upper() == "APPROVED":
            rows = conn.execute("SELECT item_id, quantity FROM orders WHERE pr_number = ?;", [pr_number]).fetchall()
            if rows:
                update_items_params = [(r[1], r[0]) for r in rows]
                conn.executemany("""
                    UPDATE items
                    SET current_stock = GREATEST(current_stock + ?, min_threshold + 5)
                    WHERE item_id = ?;
                """, update_items_params)

        conn.execute("""
            UPDATE orders 
            SET status = ?
            WHERE pr_number = ?;
        """, [status, pr_number])
    finally:
        conn.commit()
        conn.close()


def scan_node(state: AgentState) -> dict[str, Any]:
    """
    Node 1: Scan Node
    Scans DuckDB inventory database to detect items below safety stock threshold.
    """
    print("\n[AGENT] [STEP 1: SCAN] Scanning inventory database for low stock items...")
    low_stock_items = get_low_stock_items()
    print(f"[AGENT] Found {len(low_stock_items)} items requiring replenishment.")
    
    return {
        "low_stock_items": low_stock_items,
        "logs": state.get("logs", []) + [f"Scanned inventory: identified {len(low_stock_items)} critical items."]
    }


def planner_node(state: AgentState) -> dict[str, Any]:
    """
    Node 2: Planner Node (qwen-35b Planner & Vendor Matcher)
    Analyzes safety stock deficits, selects optimal vendors, and drafts line item justifications.
    """
    print("[AGENT] [STEP 2: PLANNER] Running Planner Node (qwen-35b) - Vendor matching & budget calculation via LLM...")
    low_stock_items = state.get("low_stock_items", [])
    
    planned_items: list[RestockItem] = []
    total_budget = 0.0
    
    if not low_stock_items:
        return {"planned_items": [], "total_budget": 0.0, "logs": state.get("logs", []) + ["Planner: No items to plan."]}

    # Prepare data for LLM
    items_data = []
    for item in low_stock_items:
        vendor = get_best_vendors(item["item_id"]) or {
            "vendor_id": "VND-DEFAULT", "name": "Standard Supplier",
            "unit_price": 10000.0, "lead_time_days": 7, "rating": 4.0
        }
        items_data.append({
            "item_id": item["item_id"],
            "name": item["name"],
            "current_stock": item["current_stock"],
            "min_threshold": item["min_threshold"],
            "reorder_qty": item["reorder_qty"],
            "unit": item["unit"],
            "vendor": vendor
        })

    prompt = f"""
You are an expert Procurement Planner AI.
Analyze the following low stock items and their available vendors.
Calculate the 'line_total' (reorder_qty * vendor.unit_price) for each item.
Write a clear, professional 'reason' in Indonesian explaining why this restock is necessary and why this vendor was chosen.

Data:
{json.dumps(items_data, indent=2)}

Output format must be a JSON object with a key 'items' containing a list of objects. Each object must have:
- item_id (string)
- vendor_id (string)
- vendor_name (string)
- unit_price (float)
- line_total (float)
- reason (string, professional Indonesian)
"""
    
    gateway = ModelGateway()
    messages = [
        {"role": "system", "content": "You are a Procurement AI. Always output valid JSON."},
        {"role": "user", "content": prompt}
    ]
    
    llm_items = {}
    try:
        # We use a new event loop because this runs in a FastAPI threadpool
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response_str = loop.run_until_complete(
            gateway.chat_completion("qwen-35b", messages, temperature=0.1, response_format_json=True)
        )
        loop.close()
        
        if response_str.startswith("```json"):
            response_str = response_str.strip("`").removeprefix("json").strip()
            
        llm_output = json.loads(response_str)
        llm_items = {i["item_id"]: i for i in llm_output.get("items", [])}
    except Exception as e:
        print(f"[AGENT] LLM Planner failed: {e}. Falling back to default.")

    # Reconstruct items safely
    for item in low_stock_items:
        item_id = item["item_id"]
        llm_item = llm_items.get(item_id, {})
        
        vendor_id = llm_item.get("vendor_id", "VND-DEFAULT")
        vendor_name = llm_item.get("vendor_name", "Standard Supplier")
        unit_price = float(llm_item.get("unit_price", 10000.0))
        line_total = float(llm_item.get("line_total", unit_price * item["reorder_qty"]))
        reason = llm_item.get("reason", f"Stok kritis. Restock via {vendor_name}.")
        
        total_budget += line_total
        
        planned_items.append(RestockItem(
            item_id=item_id,
            name=item["name"],
            category=item["category"],
            current_stock=item["current_stock"],
            min_threshold=item["min_threshold"],
            reorder_qty=item["reorder_qty"],
            unit=item["unit"],
            vendor_id=vendor_id,
            vendor_name=vendor_name,
            unit_price=unit_price,
            total_price=line_total,
            reason=reason
        ))
        
    print(f"[AGENT] Planned {len(planned_items)} line items via LLM. Subtotal budget: Rp {total_budget:,.0f}")
    
    return {
        "planned_items": planned_items,
        "total_budget": total_budget,
        "logs": state.get("logs", []) + [f"Planner (LLM): Matched {len(planned_items)} vendors with subtotal Rp {total_budget:,.0f}."]
    }


def audit_node(state: AgentState) -> dict[str, Any]:
    """
    Node 3: Audit Node (nemotron-35 Auditor & Compliance Guardrail)
    Validates budget ceilings, pricing sanity, and vendor procurement compliance.
    """
    print("[AGENT] [STEP 3: AUDIT] Running Audit Node (nemotron-35) - Compliance & budget guardrail via LLM...")
    total_budget = state.get("total_budget", 0.0)
    planned_items = state.get("planned_items", [])
    
    BUDGET_CEILING = 100_000_000.0
    
    prompt = f"""
You are a strict Compliance Auditor AI.
Evaluate the following procurement plan.
Rules:
1. The total_budget MUST NOT exceed Rp {BUDGET_CEILING:,.0f}.
2. If total_budget <= {BUDGET_CEILING:,.0f}, status is 'PASSED'.
3. If total_budget > {BUDGET_CEILING:,.0f}, status is 'REVISED'.
4. Write a professional auditor_notes in Indonesian explaining the decision.

Data:
total_budget: {total_budget}
num_items: {len(planned_items)}

Output format must be a JSON object with:
- auditor_status (string: 'PASSED' or 'REVISED')
- auditor_notes (string, professional Indonesian)
"""

    gateway = ModelGateway()
    messages = [
        {"role": "system", "content": "You are an Auditor AI. Always output valid JSON."},
        {"role": "user", "content": prompt}
    ]
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response_str = loop.run_until_complete(
            gateway.chat_completion("nemotron-35", messages, temperature=0.1, response_format_json=True)
        )
        loop.close()
        
        if response_str.startswith("```json"):
            response_str = response_str.strip("`").removeprefix("json").strip()
            
        llm_output = json.loads(response_str)
        auditor_status = llm_output.get("auditor_status", "REVISED")
        auditor_notes = llm_output.get("auditor_notes", "Audit failed to parse response.")
    except Exception as e:
        print(f"[AGENT] LLM Audit failed: {e}. Falling back to default.")
        if total_budget <= BUDGET_CEILING and len(planned_items) > 0:
            auditor_status = "PASSED"
            auditor_notes = f"Evaluasi lolos (Fallback). Anggaran Rp {total_budget:,.0f} aman."
        else:
            auditor_status = "REVISED"
            auditor_notes = "Peringatan Anggaran (Fallback). Melebihi batas atau tidak ada item."
        
    print(f"[AGENT] Audit Result (LLM): {auditor_status} - {auditor_notes}")
    
    return {
        "auditor_status": auditor_status,
        "auditor_notes": auditor_notes,
        "logs": state.get("logs", []) + [f"Auditor (LLM): Status={auditor_status}."]
    }


def typst_node(state: AgentState) -> dict[str, Any]:
    """
    Node 4: Typst Node
    Compiles initial Purchase Requisition into a PDF and logs pending orders.
    """
    print("[AGENT] [STEP 4: TYPST] Running Typst Node - Generating Initial Purchase Requisition...")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pr_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    pr_number = f"PR-{pr_timestamp}"
    thread_id = state.get("thread_id", f"thread-{pr_timestamp}")
    
    items = state.get("planned_items", [])
    total_budget = state.get("total_budget", 0.0)
    auditor_status = state.get("auditor_status", "PASSED")
    auditor_notes = state.get("auditor_notes", "")
    
    pr_doc = PurchaseRequisition(
        pr_number=pr_number,
        created_at=now_str,
        items=items,
        total_budget=total_budget,
        auditor_status=auditor_status,
        auditor_notes=auditor_notes,
        status="PENDING",
        thread_id=thread_id
    )
    
    pdf_path = generate_pr_pdf(pr_doc)
    pr_doc.pdf_path = pdf_path
    
    # Save pending orders to DuckDB
    record_orders_to_db(pr_doc, status="PENDING")
    
    print(f"[AGENT] Initial Document Generated: {pdf_path}")
    print(f"[AGENT] PR #{pr_number} created with status 'PENDING'. Pausing before Wait Approval Node...")

    
    return {
        "pr_document": pr_doc,
        "pdf_path": pdf_path,
        "thread_id": thread_id,
        "logs": state.get("logs", []) + [f"Typst Node: Generated document {pr_number} at {pdf_path} (Pending Approval)."]
    }


def wait_approval_node(state: AgentState) -> dict[str, Any]:
    """
    Node 5: Wait Approval Node (Human-In-The-Loop)
    Reads manager decision (APPROVE / REJECT).
    Updates DuckDB orders table and compiles the final stamped PDF (_APPROVED.pdf or _REJECTED.pdf).
    """
    pr_doc = state.get("pr_document")
    raw_action = str(state.get("approval_action", "APPROVE")).strip().upper()
    approver = state.get("approver_name", "Operations Manager")
    notes = state.get("approval_notes", "")
    
    is_approve = raw_action in ["APPROVE", "APPROVED", "Y", "YES"]
    final_status = "APPROVED" if is_approve else "REJECTED"
    
    print(f"\n[AGENT] [STEP 5: HITL APPROVAL] Processing decision: '{final_status}' by '{approver}'...")
    
    if pr_doc:
        pr_doc.status = final_status
        if not is_approve:
            pr_doc.auditor_notes = f"[REJECTED by {approver}]: {notes or 'Pengadaan ditolak oleh manajer. Tidak ada pembelian diproses.'}"
        else:
            pr_doc.auditor_notes = f"[APPROVED by {approver}]: {notes or 'Pengadaan disetujui untuk pemesanan vendor.'}"
            
        # Update DuckDB orders table status
        update_db_orders_status(pr_doc.pr_number, final_status)
        
        # Compile final PDF with _APPROVED or _REJECTED suffix
        final_pdf_path = generate_pr_pdf(pr_doc)
        pr_doc.pdf_path = final_pdf_path
        print(f"[AGENT] Final Document Compiled: {final_pdf_path}")
    else:
        final_pdf_path = None
        
    print(f"[AGENT] Final PR Status: {final_status}. DuckDB orders updated successfully.")
    
    log_msg = f"Manager ({approver}) marked PR as {final_status}."
    return {
        "pr_document": pr_doc,
        "pdf_path": final_pdf_path,
        "is_approved": is_approve,
        "logs": state.get("logs", []) + [log_msg]
    }


def create_autorestock_graph() -> StateGraph:
    """Build and compile the LangGraph workflow with HITL interrupt_before on wait_approval_node."""
    workflow = StateGraph(AgentState)
    
    workflow.add_node("scan_node", scan_node)
    workflow.add_node("planner_node", planner_node)
    workflow.add_node("audit_node", audit_node)
    workflow.add_node("typst_node", typst_node)
    workflow.add_node("wait_approval_node", wait_approval_node)
    
    workflow.add_edge(START, "scan_node")
    workflow.add_edge("scan_node", "planner_node")
    workflow.add_edge("planner_node", "audit_node")
    workflow.add_edge("audit_node", "typst_node")
    workflow.add_edge("typst_node", "wait_approval_node")
    workflow.add_edge("wait_approval_node", END)
    
    return workflow.compile(
        checkpointer=memory_checkpointer,
        interrupt_before=["wait_approval_node"]
    )


# Singleton compiled graph
autorestock_app = create_autorestock_graph()

PR_THREAD_REGISTRY: dict[str, str] = {}


def run_autorestock_cycle(thread_id: str | None = None) -> PurchaseRequisition:
    """
    Runs cycle up to the HITL interrupt point (Typst Node).
    Returns the generated PurchaseRequisition with status PENDING_APPROVAL.
    """
    if thread_id is None:
        thread_id = f"thread-{uuid.uuid4().hex[:8]}"
        
    initial_state: AgentState = {
        "thread_id": thread_id,
        "low_stock_items": [],
        "planned_items": [],
        "total_budget": 0.0,
        "auditor_status": "",
        "auditor_notes": "",
        "pr_document": None,
        "pdf_path": None,
        "approval_action": None,
        "approver_name": None,
        "approval_notes": None,
        "is_approved": False,
        "logs": []
    }
    
    config = {"configurable": {"thread_id": thread_id}}
    final_state = autorestock_app.invoke(initial_state, config=config)
    
    pr_doc = final_state.get("pr_document")
    if pr_doc:
        PR_THREAD_REGISTRY[pr_doc.pr_number] = thread_id
        
    return pr_doc


def resume_approval(
    pr_number: str,
    action: str = "APPROVE",
    approver_name: str = "Warehouse Operations Manager",
    notes: str = "",
    thread_id: str | None = None
) -> PurchaseRequisition:
    """
    Resumes the workflow from the checkpoint with either APPROVE or REJECT action.
    """
    if thread_id is None:
        thread_id = PR_THREAD_REGISTRY.get(pr_number, f"thread-{pr_number}")
        
    config = {"configurable": {"thread_id": thread_id}}
    
    normalized_action = "APPROVE" if str(action).strip().upper() in ["APPROVE", "APPROVED", "Y", "YES"] else "REJECT"
    
    autorestock_app.update_state(
        config,
        {
            "approval_action": normalized_action,
            "approver_name": approver_name,
            "approval_notes": notes
        }
    )
    
    resumed_state = autorestock_app.invoke(None, config=config)
    return resumed_state.get("pr_document")
