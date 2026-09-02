import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status, Response, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from agents.state import PurchaseRequisition
from agents.workflow import resume_approval, run_autorestock_cycle
from core.security import TokenData, get_current_user
from database.db import get_db_connection
from mcp_server.tools import get_all_inventory_items

router = APIRouter(tags=["AutoRestock Agent"])

STORAGE_DIR = WORKSPACE_DIR / "storage"


class ApprovalRequest(BaseModel):
    pr_number: str = Field(..., description="Purchase Requisition number to approve or reject")
    action: str = Field("APPROVE", description="Decision action: 'APPROVE' or 'REJECT'")
    approver_name: str | None = Field("Warehouse Operations Manager", description="Name/Role of approver")
    notes: str | None = Field(None, description="Optional notes or reason for decision")


class ApprovalResponse(BaseModel):
    pr_number: str
    status: str
    approver: str
    message: str
    pr_document: PurchaseRequisition | None = None


@router.get("/api/inventory/items", response_model=list[dict[str, Any]])
def get_inventory_items(response: Response, current_user: TokenData = Depends(get_current_user)):
    """
    Retrieve all inventory items from DuckDB.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    try:
        items = get_all_inventory_items(tenant_id=current_user.tenant_id)
        return items
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch inventory items: {e!s}"
        )


@router.post("/api/agent/run-cycle", response_model=PurchaseRequisition)
def run_agent_cycle():
    """
    Triggers the LangGraph multi-agent workflow:
    1. Scan items below safety threshold.
    2. Planner (qwen-35b) matches optimal vendors & calculates budget.
    3. Auditor (nemotron-35) enforces compliance guardrails.
    4. Typst compiles the formal Purchase Requisition PDF.
    5. Graph pauses before Wait Approval Node (HITL).
    """
    try:
        pr_document = run_autorestock_cycle()
        if pr_document:
            from api.routers.approval_routes import PR_STORE
            from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
            from docgen.pdf_generator import pdf_generator
            
            items_req = [
                PurchaseItemRequest(
                    item_id=it.item_id,
                    name=it.name,
                    reorder_qty=it.reorder_qty,
                    unit=it.unit,
                    vendor_id=it.vendor_id,
                    vendor_name=it.vendor_name,
                    unit_price=it.unit_price,
                    total_price=it.total_price,
                    reason=it.reason
                )
                for it in pr_document.items
            ]
            clean_filename = f"{pr_document.pr_number.replace('-', '_')}.pdf"
            PR_STORE[pr_document.pr_number] = PurchaseRequisitionDoc(
                pr_number=pr_document.pr_number,
                created_at=pr_document.created_at,
                items=items_req,
                total_budget=pr_document.total_budget,
                auditor_status=pr_document.auditor_status or "PASSED",
                auditor_notes=pr_document.auditor_notes or "Audit passed.",
                pdf_path=f"/storage/documents/{clean_filename}",
                status=pr_document.status or "PENDING"
            )
            pdf_generator.generate_purchase_requisition_pdf(PR_STORE[pr_document.pr_number], output_filename=clean_filename)
        return pr_document
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AutoRestock agent cycle failed: {e!s}"
        )



@router.get("/api/documents/pr/{pr_number}/download")
def download_pr_document(pr_number: str, inline: bool = False):
    """
    Downloads or previews the generated Typst Purchase Requisition PDF.
    Use ?inline=true to display in-browser (for iframe previews).
    Checks status-specific folders first to ensure the served PDF matches true PR status.
    """
    clean_pr_num = pr_number.replace("/", "_").replace("\\", "_")
    clean_filename = f"{pr_number.replace('-', '_')}.pdf"
    
    # Check DB/PR_STORE status first
    from api.routers.approval_routes import _ensure_pr_in_store, _regenerate_pdf
    pr_doc = _ensure_pr_in_store(pr_number)
    current_status = (pr_doc.status if pr_doc else "PENDING").upper()
    
    candidate_paths = []
    if "APPROV" in current_status:
        candidate_paths = [
            STORAGE_DIR / "approved" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / "approved" / clean_filename,
            STORAGE_DIR / "documents" / clean_filename,
            STORAGE_DIR / "documents" / f"{clean_pr_num}.pdf",
        ]
    elif "REJECT" in current_status:
        candidate_paths = [
            STORAGE_DIR / "rejected" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / "rejected" / clean_filename,
            STORAGE_DIR / "documents" / clean_filename,
            STORAGE_DIR / "documents" / f"{clean_pr_num}.pdf",
        ]
    else:
        candidate_paths = [
            STORAGE_DIR / "pending" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / "pending" / clean_filename,
            STORAGE_DIR / "documents" / clean_filename,
            STORAGE_DIR / "documents" / f"{clean_pr_num}.pdf",
            STORAGE_DIR / f"{clean_pr_num}.pdf"
        ]
    
    found_path = None
    for path in candidate_paths:
        if path.exists():
            found_path = path
            break
            
    # If not found or if the document needs regeneration for its current status
    if found_path is None and pr_doc:
        try:
            _regenerate_pdf(pr_doc)
            for path in candidate_paths:
                if path.exists():
                    found_path = path
                    break
        except Exception as e:
            print(f"[download_pr_document] Regeneration on-the-fly failed: {e}")

    # Recursive wildcard search fallback
    if found_path is None:
        matches = list(STORAGE_DIR.rglob(f"*{clean_pr_num}*.pdf"))
        if matches:
            found_path = matches[0]

    if found_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase Requisition PDF '{pr_number}' not found in storage."
        )
            
    return FileResponse(
        path=str(found_path),
        media_type="application/pdf",
        filename=f"{clean_pr_num}.pdf",
        content_disposition_type="inline" if inline else "attachment"
    )


@router.post("/api/agent/approve", response_model=ApprovalResponse)
def approve_pr_requisition(request: ApprovalRequest):
    """
    Handles Human-In-The-Loop (HITL) approval for a Purchase Requisition:
    - If APPROVE: Updates DuckDB orders table status to 'APPROVED' and resumes the paused LangGraph workflow.
    - If REJECT: Updates DuckDB orders table status to 'REJECTED'.
    """
    try:
        action = request.action.upper()
        if action not in ["APPROVE", "REJECT"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action must be either 'APPROVE' or 'REJECT'."
            )
            
        updated_pr = resume_approval(
            pr_number=request.pr_number,
            action=action,
            approver_name=request.approver_name or "Manager",
            notes=request.notes or ""
        )
        
        final_status = "APPROVED" if action == "APPROVE" else "REJECTED"
        msg = f"Purchase Requisition {request.pr_number} successfully {final_status} by {request.approver_name}."
        
        return ApprovalResponse(
            pr_number=request.pr_number,
            status=final_status,
            approver=request.approver_name or "Manager",
            message=msg,
            pr_document=updated_pr
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process PR approval: {e!s}"
        )


class UpdateItemThresholdRequest(BaseModel):
    min_threshold: int | None = Field(None, description="New minimum safety threshold")
    max_threshold: int | None = Field(None, description="New maximum safety threshold")
    current_stock: int | None = Field(None, description="Optional update to current physical stock")
    avg_daily_usage: float | None = Field(None, description="Optional update to daily usage burn rate")
    lead_time_days: int | None = Field(None, description="Optional update to vendor lead time")


@router.patch("/api/inventory/items/{item_id}")
def update_item_threshold(item_id: str, payload: UpdateItemThresholdRequest):
    """
    Updates threshold and inventory parameters for a specific item in DuckDB.
    """
    conn = get_db_connection()
    try:
        existing = conn.execute("SELECT item_id, name, min_threshold, max_threshold, current_stock FROM items WHERE item_id = ?", [item_id]).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Item with ID '{item_id}' not found in inventory.")

        updates = []
        params = []
        if payload.min_threshold is not None:
            updates.append("min_threshold = ?")
            params.append(payload.min_threshold)
        if payload.max_threshold is not None:
            updates.append("max_threshold = ?")
            params.append(payload.max_threshold)
        if payload.current_stock is not None:
            updates.append("current_stock = ?")
            params.append(payload.current_stock)
        if payload.avg_daily_usage is not None:
            updates.append("avg_daily_usage = ?")
            params.append(payload.avg_daily_usage)
        if payload.lead_time_days is not None:
            updates.append("lead_time_days = ?")
            params.append(payload.lead_time_days)

        if not updates:
            return {"status": "no_change", "message": "No parameters provided to update."}

        params.append(item_id)
        sql = f"UPDATE items SET {', '.join(updates)} WHERE item_id = ?;"
        conn.execute(sql, params)

        # Retrieve updated record
        updated_row = conn.execute("""
            SELECT item_id, name, category, current_stock, min_threshold, max_threshold, avg_daily_usage, lead_time_days, unit
            FROM items WHERE item_id = ?;
        """, [item_id]).fetchone()
        columns = [d[0] for d in conn.description]
        updated_item = dict(zip(columns, updated_row))

        return {
            "status": "success",
            "message": f"Berhasil memperbarui {existing[1]} ({item_id}).",
            "item": updated_item
        }
    finally:
        conn.close()


class CustomPromptRequest(BaseModel):
    prompt: str = Field(..., description="Natural language prompt from user describing restock intent or workflow")
    destinations: list[str] | None = Field(None, description="Explicit destinations: ['database', 'email', 'pdf']")
    recipient_email: str | None = Field(None, description="Optional custom recipient email")


@router.post("/api/agent/custom-prompt")
async def execute_custom_prompt_workflow(request: CustomPromptRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Accepts free-form natural language instructions from non-technical users,
    synthesizes a custom multi-agent workflow, executes actions, and dispatches outputs.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt tidak boleh kosong.")

    lower_prompt = request.prompt.strip().lower()
    if lower_prompt in ["hi", "halo", "hello", "tes", "test", "testing"]:
        return {
            "parsed_intent": {"workflow_id": "greeting"},
            "action_type": "general",
            "message": "Halo! Saya adalah AutoRestock Agent. Ada yang bisa saya bantu terkait persediaan dan restock barang hari ini?",
            "generated_prs": [],
            "affected_items": []
        }

    from agents.router import SemanticRouter
    from agents.json_executor import JSONExecutionEngine
    from database.db import get_db_connection
    import json
    
    try:
        # Route prompt to workflow ID
        route_result = await SemanticRouter.route_prompt(request.prompt, current_user.tenant_id)
        workflow_id = route_result.get("workflow_id")
        
        if not workflow_id:
            # Default to WF-001 (Auto Restock) if nothing matches or LLM failed
            workflow_id = "WF-001"
            
        # Fetch workflow from DB
        conn = get_db_connection()
        wf_row = conn.execute("SELECT compiled_json FROM workflows WHERE id = ?", [workflow_id]).fetchone()
        conn.close()
        
        if not wf_row:
            raise Exception(f"Workflow {workflow_id} not found in database.")
            
        compiled_json = json.loads(wf_row[0])
        
        # Execute workflow
        context = {
            "threshold_updates": route_result.get("threshold_updates", []),
            "target_item_name": route_result.get("target_item_name"),
            "send_email": route_result.get("send_email", False),
            "new_item_data": route_result.get("new_item_data", {})
        }
        result = await JSONExecutionEngine.execute(compiled_json, current_user.tenant_id, custom_context=context)
        
        # Map to dashboard.js expected schema
        action_type = "general"
        if "update_threshold" in compiled_json.get("workflow", ""):
            action_type = "update_threshold"
        elif "daftar" in compiled_json.get("workflow", "") or "register" in compiled_json.get("workflow", "") or "tambah" in compiled_json.get("workflow", "") or result.get("registered_item"):
            action_type = "register_product"
        elif result.get("pr_number"):
            action_type = "review_prs"
        elif context.get("send_email") and "email" in str(compiled_json.get("steps", [])):
            action_type = "notify_email"
            
        affected = []
        # Return items to dashboard
        if result.get("registered_item"):
            reg = result["registered_item"]
            new_item = context.get("new_item_data", {})
            affected = [{
                "name": reg.get("name", "Item Baru"),
                "current_stock": new_item.get("current_stock", 0),
                "min_stock": new_item.get("min_threshold", 0),
                "unit": new_item.get("unit", "pcs")
            }]
        elif context.get("low_stock_items"):
            affected = [{"name": it["name"], "current_stock": it["current_stock"], "min_stock": it.get("min_threshold", 0), "unit": it["unit"]} for it in context["low_stock_items"]]
        elif context.get("specific_items"):
            affected = [{"name": it["name"], "current_stock": it["current_stock"], "min_stock": it.get("min_threshold", 0), "unit": it["unit"]} for it in context["specific_items"]]

        dashboard_response = {
            "parsed_intent": {"workflow_id": workflow_id},
            "action_type": action_type,
            "message": result.get("summary", ""),
            "email_sent": result.get("email_sent", False),
            "generated_prs": [],
            "affected_items": affected,
            "total_items_analyzed": result.get("total_items_analyzed", len(affected)),
            "target_destinations": result.get("target_destinations", ["database"]),
            "pdf_download_url": result.get("pdf_download_url"),
            "execution_steps": result.get("execution_steps", []),
            "total_budget_formatted": result.get("total_budget_formatted", "Rp 0")
        }

        if result.get("pr_number"):
            from api.routers.approval_routes import PR_STORE
            pr_doc = PR_STORE.get(result["pr_number"])
            if pr_doc:
                dashboard_response["generated_prs"] = [{
                    "pr_number": pr_doc.pr_number,
                    "supplier_name": "Multiple Vendors" if len(set(it.vendor_name for it in pr_doc.items)) > 1 else (pr_doc.items[0].vendor_name if pr_doc.items else "Vendor"),
                    "grand_total": pr_doc.total_budget,
                    "status": pr_doc.status.lower(),
                    "email_sent": result.get("email_sent", False),
                    "items": [{"item_name": it.name, "quantity": it.reorder_qty, "unit": it.unit} for it in pr_doc.items]
                }]
                
        return dashboard_response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal mengeksekusi dynamic workflow: {e!s}"
        )


@router.get("/api/agent/prompt-templates")
def get_prompt_templates():
    """
    Returns curated 1-click prompt templates for non-technical users.
    """
    return [
        {
            "id": 1,
            "title": "Restock Darurat Elektronik -> Email",
            "prompt": "Tolong cek semua barang kategori Electronics yang stoknya kritis, pilihkan vendor termurah, buatkan dokumen PDF, dan kirim notifikasi ke Email."
        },
        {
            "id": 2,
            "title": "Update Threshold STM32 & Simpan DB",
            "prompt": "Ubah threshold barang ITM-001 jadi 80 pcs, lalu hitung ulang kebutuhan restock dan simpan hasilnya di database saja."
        },
        {
            "id": 3,
            "title": "Rekap Stok Kemasan -> Email",
            "prompt": "Buatkan rekap laporan restock barang Packaging dan kirimkan ke email manager@company.com."
        },
        {
            "id": 4,
            "title": "Audit Lengkap Semua Barang Gudang",
            "prompt": "Periksa semua barang di gudang yang di bawah threshold, buatkan draf Purchase Requisition PDF resmi."
        }
    ]

