import asyncio
import re
import json
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status, Response, Depends
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from agents.state import PurchaseRequisition, RestockItem
from agents.workflow import resume_approval, run_autorestock_cycle
from core.security import TokenData, get_current_user, get_document_user
from api.routers.balitower_routes import require_inventory_access
from database.db import get_db_connection
from mcp_server.tools import get_all_inventory_items

router = APIRouter(tags=["AutoRestock Agent"])

STORAGE_DIR = WORKSPACE_DIR / "storage"


def _safe_document_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", value) or ".." in value:
        raise HTTPException(status_code=400, detail="Invalid document identifier")
    return value


def _require_document_domain(user: TokenData, *tenants: str) -> None:
    if user.role != "ADMIN" and user.tenant_id.upper() not in tenants:
        raise HTTPException(status_code=403, detail="Access denied")


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
def get_inventory_items(response: Response, current_user: TokenData = Depends(require_inventory_access)):
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
def run_agent_cycle(current_user: TokenData = Depends(require_inventory_access)):
    """
    Triggers the LangGraph multi-agent workflow:
    1. Scan items below safety threshold.
    2. Planner (qwen-38) matches optimal vendors & calculates budget.
    3. Auditor (qwen-38) enforces compliance guardrails.
    4. Typst compiles the formal Purchase Requisition PDF.
    5. Graph pauses before Wait Approval Node (HITL).
    """
    try:
        tenant_id = current_user.tenant_id if current_user else "ALL"
        pr_document = run_autorestock_cycle(tenant_id=tenant_id)
        if pr_document:
            from api.routers.approval_routes import PR_STORE
            from docgen.compiler import generate_pr_pdf
            
            clean_filename = f"{pr_document.pr_number.replace('-', '_')}.pdf"
            PR_STORE[pr_document.pr_number] = pr_document
            generate_pr_pdf(pr_document, output_path=f"storage/documents/{clean_filename}")
        return pr_document
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AutoRestock agent cycle failed: {e!s}"
        )



@router.get("/api/documents/pr/{pr_number}/download")
def download_pr_document(pr_number: str, inline: bool = False, current_user: TokenData = Depends(get_document_user)):
    """
    Downloads or previews the generated Typst Purchase Requisition PDF.
    Use ?inline=true to display in-browser (for iframe previews).
    Checks status-specific folders first to ensure the served PDF matches true PR status.
    """
    _safe_document_id(pr_number)
    _require_document_domain(current_user, "INVENTORY", "TENANT_A")
    clean_pr_num = pr_number.replace("/", "_").replace("\\", "_")
    clean_filename = f"{pr_number.replace('-', '_')}.pdf"
    
    # Check DB/PR_STORE status first
    from api.routers.approval_routes import _ensure_pr_in_store, _regenerate_pdf
    pr_doc = _ensure_pr_in_store(pr_number)
    if pr_doc and current_user.role != "ADMIN" and pr_doc.tenant_id not in {current_user.tenant_id, "ALL"}:
        raise HTTPException(status_code=403, detail="Access denied")
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


@router.get("/api/documents/po/{po_id}/download")
def download_po_document(po_id: str, inline: bool = False, current_user: TokenData = Depends(get_document_user)):
    """
    Downloads or previews the official Typst Purchase Order (PO) PDF.
    Use ?inline=true to display in-browser (for iframe modal previews).
    Generates the PDF dynamically on-the-fly via Typst if not already compiled.
    """
    _require_document_domain(current_user, "INVENTORY", "TENANT_A")
    clean_po_id = _safe_document_id(po_id)
    po_storage_dir = STORAGE_DIR / "purchase_orders"
    po_storage_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = po_storage_dir / f"{clean_po_id}.pdf"

    from docgen.compiler import generate_po_pdf
    try:
        pdf_path = generate_po_pdf(po_id, output_path=target_pdf)
    except Exception as err:
        if target_pdf.exists():
            pdf_path = str(target_pdf)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gagal menerbitkan dokumen Purchase Order '{po_id}': {err}"
            )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{clean_po_id}.pdf",
        content_disposition_type="inline" if inline else "attachment"
    )


@router.get("/api/documents/leave/{leave_id}/download")
def download_leave_document(leave_id: str, inline: bool = False, current_user: TokenData = Depends(get_document_user)):
    """
    Downloads or previews the official Typst Leave Request PDF.
    Use ?inline=true to display in-browser (for iframe modal previews).
    Generates the PDF dynamically on-the-fly via Typst if not already compiled.
    """
    _require_document_domain(current_user, "HR", "TENANT_B")
    clean_leave_id = _safe_document_id(leave_id)
    leave_storage_dir = STORAGE_DIR / "leave_requests"
    leave_storage_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = leave_storage_dir / f"{clean_leave_id}.pdf"

    from docgen.compiler import generate_leave_pdf
    try:
        pdf_path = generate_leave_pdf(leave_id, output_path=target_pdf)
    except Exception as err:
        if target_pdf.exists():
            pdf_path = str(target_pdf)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gagal menerbitkan dokumen Surat Pengajuan Cuti '{leave_id}': {err}"
            )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{clean_leave_id}.pdf",
        content_disposition_type="inline" if inline else "attachment"
    )


@router.get("/api/documents/invoice/{invoice_id}/download")
def download_invoice_document(invoice_id: str, inline: bool = False, current_user: TokenData = Depends(get_document_user)):
    """
    Downloads or previews the official Typst Tower Lease Invoice / MLA Contract PDF.
    Use ?inline=true to display in-browser (for iframe modal previews).
    Generates the PDF dynamically on-the-fly via Typst if not already compiled.
    Supports both invoice IDs (e.g. INV-2026-001) and onboarding IDs (e.g. ONB-2026-001).
    """
    _require_document_domain(current_user, "FINANCE", "TENANT_C")
    clean_id = _safe_document_id(invoice_id)
    invoice_storage_dir = STORAGE_DIR / "invoices"
    invoice_storage_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = invoice_storage_dir / f"{clean_id}.pdf"

    from docgen.compiler import generate_invoice_pdf
    try:
        pdf_path = generate_invoice_pdf(invoice_id, output_path=target_pdf)
    except Exception as err:
        if target_pdf.exists():
            pdf_path = str(target_pdf)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Gagal menerbitkan dokumen Invoice/Kontrak Sewa '{invoice_id}': {err}"
            )

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{clean_id}.pdf",
        content_disposition_type="inline" if inline else "attachment"
    )


@router.get("/api/documents/reports/{report_name}/download")
def download_dynamic_report_document(report_name: str, inline: bool = False, current_user: TokenData = Depends(get_document_user)):
    """
    Downloads or previews an official Typst Dynamic Report PDF.
    Use ?inline=true to display in-browser / iframe modal previews.
    """
    clean_name = _safe_document_id(report_name)
    if not clean_name.endswith(".pdf"):
        clean_name = f"{clean_name}.pdf"

    reports_dir = STORAGE_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = reports_dir / clean_name

    if not target_pdf.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Laporan PDF '{report_name}' tidak ditemukan di penyimpanan."
        )

    return FileResponse(
        path=str(target_pdf),
        media_type="application/pdf",
        filename=target_pdf.name,
        content_disposition_type="inline" if inline else "attachment"
    )


@router.post("/api/agent/approve", response_model=ApprovalResponse)
def approve_pr_requisition(request: ApprovalRequest, current_user: TokenData = Depends(require_inventory_access)):
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
def update_item_threshold(item_id: str, payload: UpdateItemThresholdRequest, current_user: TokenData = Depends(require_inventory_access)):
    """
    Updates threshold and inventory parameters for a specific item in DuckDB.
    Supports real heterogeneous tenant tables and legacy items.
    """
    from database.schema_adapters import TenantSchemaAdapter
    tenant_id = current_user.tenant_id if current_user else "ALL"
    
    # 1. Look up existing item in real tenant tables or legacy items
    matching_items = TenantSchemaAdapter.get_specific_item_stock(item_id, tenant_id=tenant_id)
    if matching_items:
        existing_name = matching_items[0]["name"]
        cur_stock = matching_items[0].get("current_stock", 0)
        old_min = matching_items[0].get("min_threshold", 0)
    else:
        conn = get_db_connection(read_only=True)
        legacy = conn.execute("SELECT item_id, name, min_threshold, max_threshold, current_stock FROM items WHERE item_id = ? OR lower(name) LIKE ?", [item_id, f"%{item_id.lower()}%"]).fetchone()
        conn.close()
        if not legacy:
            raise HTTPException(status_code=404, detail=f"Item with ID '{item_id}' not found in inventory.")
        existing_name = legacy[1]
        cur_stock = legacy[4]
        old_min = legacy[2]

    # 2. Apply threshold update if provided
    new_min = payload.min_threshold if payload.min_threshold is not None else old_min
    if payload.min_threshold is not None:
        TenantSchemaAdapter.update_item_threshold(item_id, payload.min_threshold, tenant_id=tenant_id)

    # 3. Update legacy items table if extra fields provided
    conn = get_db_connection()
    try:
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

        if updates:
            params.extend([item_id, f"%{item_id.lower()}%"])
            conn.execute(f"UPDATE items SET {', '.join(updates)} WHERE item_id = ? OR lower(name) LIKE ?;", params)
            conn.commit()
    finally:
        conn.close()

    return {
        "status": "success",
        "message": f"Berhasil memperbarui {existing_name} ({item_id}).",
        "item": {
            "item_id": item_id,
            "name": existing_name,
            "min_threshold": new_min,
            "current_stock": payload.current_stock if payload.current_stock is not None else cur_stock
        }
    }



from services.goods_receipt_service import process_goods_receipt


class CustomPromptRequest(BaseModel):
    prompt: str = Field(..., description="Natural language prompt from user describing restock intent or workflow")
    destinations: list[str] | None = Field(None, description="Explicit destinations: ['database', 'email', 'pdf']")
    recipient_email: str | None = Field(None, description="Optional custom recipient email")
    history: list[dict[str, Any]] | None = Field(None, description="Optional multi-turn conversation history: [{'role': 'user', 'content': '...'}, ...]")


def classify_workflow_proposal_eligibility(prompt: str, agent_result: dict, user_role: str = "USER") -> bool:
    """
    Determines whether a user prompt should show the 'Ajukan Alur Kerja ke Administrator' proposal card.
    
    Enterprise Policy:
    1. Admin user -> False (Admin can create workflows directly in admin portal).
    2. Pure Greetings / Pleasantries / Out-of-Domain Refusal -> False.
    3. Direct Single-Tool Execution (Safe Read Queries, Check Stock, View PO):
       -> False (Task was successfully executed by the LLM single-tool capability; no workflow card needed).
    4. Guarded Tool Blocked or Unregistered Multi-Step Workflow Required:
       -> True (Action is blocked by enterprise governance, so system actively recommends proposing an admin workflow).
    """
    if str(user_role).upper() == "ADMIN":
        return False

    action_type = agent_result.get("action_type", "")
    message = agent_result.get("message", "")

    # Out of scope or domain refusal -> Never propose workflow
    if action_type == "out_of_scope":
        return False
    if "hanya berwenang melayani pertanyaan dan instruksi seputar operasional Dashboard BaliTower" in message:
        return False

    # If action was blocked due to guarded tool policy or unregistered workflow
    if action_type == "workflow_not_found" or agent_result.get("is_tool_blocked") or agent_result.get("guarded_tool"):
        return True

    # If the user explicitly asks to create/register a workflow
    lower_prompt = prompt.lower()
    is_create_workflow_request = (
        bool(re.search(r'\b(buat|bikin|create|tambah|daftarkan|ajukan)\s+(alur\s+kerja|workflow)\b', lower_prompt))
        or bool(re.search(r'\b(workflow|alur kerja)\s+(baru|belum ada)\b', lower_prompt))
        or bool(re.search(r'\b(saya\s+butuh|perlu)\s+(alur\s+kerja|workflow)\b', lower_prompt))
    )
    if is_create_workflow_request:
        return True

    # Explicit flag from agent when an action requires admin workflow
    if agent_result.get("can_request_admin") and action_type in ["workflow_not_found", "tool_blocked"]:
        return True

    # Safe direct queries and resolved actions should NOT propose workflow
    return False


async def execute_prompt_logic(
    request: CustomPromptRequest,
    current_user: TokenData,
    stage_callback = None
) -> dict:
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt tidak boleh kosong.")

    from agents.router import extract_recipient_email, check_clarification_needs

    # 0. Context Merge: If user is responding directly to a previous clarification question
    if request.history and len(request.history) >= 1:
        last_turn = request.history[-1]
        last_content = str(last_turn.get("content", "")).lower()
        # Case A: Email clarification response
        if any(kw in last_content for kw in ["alamat email", "penerima belum disebutkan", "email tujuan"]):
            new_email = extract_recipient_email(request.prompt)
            if new_email:
                prev_user_prompt = None
                for turn in reversed(request.history[:-1]):
                    if turn.get("role") == "user":
                        prev_user_prompt = str(turn.get("content", "")).strip()
                        break
                if prev_user_prompt:
                    merged = re.sub(r'\bke\s+email\b', f'ke {new_email}', prev_user_prompt, flags=re.IGNORECASE)
                    if new_email not in merged:
                        merged = f"{merged.rstrip('. ')} ke {new_email}"
                    request.prompt = merged
        # Case B: Threshold item or value clarification response
        elif "batas minimum" in last_content or "ambang batas" in last_content:
            prev_user_prompt = None
            for turn in reversed(request.history[:-1]):
                if turn.get("role") == "user":
                    prev_user_prompt = str(turn.get("content", "")).strip()
                    break
            if prev_user_prompt and len(request.prompt.split()) <= 4:
                request.prompt = f"{prev_user_prompt.rstrip('. ')} {request.prompt.strip()}"

    lower_prompt = request.prompt.strip().lower()

    if stage_callback:
        await stage_callback("analyze", "Menganalisis instruksi & hak akses wewenang...")

    # 0. Security Guardrail: Pre-Execution Prompt Injection & Destructive Command Check
    from agents.autonomous_agent import AutonomousAgent
    is_safe, refusal_msg = AutonomousAgent.check_prompt_injection_guardrail(request.prompt)
    if not is_safe:
        return {
            "parsed_intent": {"workflow_id": "security_guardrail_refusal"},
            "action_type": "security_refusal",
            "message": refusal_msg,
            "generated_prs": [],
            "affected_items": []
        }

    # 0.5 Domain Scope Guardrail: Pre-Execution Out-of-Domain Filter
    is_out_of_domain, domain_refusal_msg = AutonomousAgent.check_domain_boundary(request.prompt)
    if is_out_of_domain:
        return {
            "parsed_intent": {"workflow_id": "out_of_domain_refusal"},
            "action_type": "out_of_scope",
            "message": domain_refusal_msg,
            "generated_prs": [],
            "affected_items": [],
            "can_request_admin": False,
            "prompt_text": request.prompt
        }

    u_tenant = str(getattr(current_user, 'tenant_id', 'ALL')).upper()
    u_role = str(getattr(current_user, 'role', 'USER')).upper()

    # 0.7 Check if user directly requests to open/render the interactive workflow proposal form in chat
    is_interactive_form_request = (
        bool(re.search(r'\b(mau\s+ajukan|ingin\s+ajukan|ajukan|request|buka\s+form|form\s+pengajuan|formulir)\s+(alur\s+kerja|workflow)\b', lower_prompt))
        and not any(task_kw in lower_prompt for task_kw in ["untuk", "rekap", "audit", "restock", "laporan", "otomatisasi", "vendor"])
    ) or lower_prompt.strip() in [
        "mau ajukan workflow", "ajukan workflow", "request workflow", "form workflow",
        "form pengajuan workflow", "formulir workflow", "mau ajukan alur kerja",
        "ajukan alur kerja", "request alur kerja", "buka form workflow", "workflow request",
        "buka form pengajuan workflow", "tampilkan form workflow"
    ]

    if is_interactive_form_request:
        return {
            "parsed_intent": {"workflow_id": "render_workflow_request_form"},
            "action_type": "render_workflow_request_form",
            "message": "Silakan lengkapi formulir pengajuan alur kerja baru di bawah ini. Usulan Anda akan langsung diteruskan ke antrean Administrator untuk ditinjau dan dikompilasi.",
            "prompt_text": request.prompt,
            "can_request_admin": True,
            "user_tenant": u_tenant,
            "user_role": u_role,
            "generated_prs": [],
            "affected_items": []
        }

    # 0.8 Check if user is asking to create/register a new workflow but lacks admin authority
    is_create_workflow_request = (
        bool(re.search(r'\b(buat|bikin|create|tambah|daftarkan|ajukan)\s+(alur\s+kerja|workflow)\b', lower_prompt))
        or bool(re.search(r'\b(workflow|alur kerja)\s+(baru|belum ada)\b', lower_prompt))
        or bool(re.search(r'\b(saya\s+butuh|perlu)\s+(alur\s+kerja|workflow)\b', lower_prompt))
    )
    if is_create_workflow_request and u_role != "ADMIN":
        return {
            "parsed_intent": {"workflow_id": "workflow_not_found"},
            "action_type": "workflow_not_found",
            "message": "Pembuatan alur kerja baru merupakan wewenang khusus Administrator. Anda dapat mengajukan permohonan alur kerja ini langsung ke Administrator agar dapat ditinjau dan dikompilasi.",
            "prompt_text": request.prompt,
            "can_request_admin": True,
            "generated_prs": [],
            "affected_items": []
        }

    # 1. Proactive Clarification Check
    clarif = check_clarification_needs(
        request.prompt,
        tenant_id=current_user.tenant_id if current_user else "ALL",
        recipient_email=request.recipient_email
    )
    if clarif:
        return {
            "parsed_intent": {"workflow_id": "clarification_needed"},
            "action_type": "clarification_needed",
            "needs_clarification": True,
            "message": clarif["message"],
            "clarification": clarif,
            "generated_prs": [],
            "affected_items": []
        }

    # 2. Specialized Goods Receipt Process (PO arrival at warehouse)
    gr_result = process_goods_receipt(request.prompt, current_user)
    if gr_result:
        return gr_result

    # 3. Multi-Tenant Boundary Guard (HR, Finance, Inventory)
    u_tenant = str(getattr(current_user, 'tenant_id', 'ALL')).upper()
    u_role = str(getattr(current_user, 'role', 'USER')).upper()
    if u_role != "ADMIN" and u_tenant != "ALL":
        if u_tenant not in ["HR", "USERB", "TENANT_B"]:
            hr_keywords = [
                "kandidat", "pelamar", "rigger", "tkpk", "screening", "rekrutmen",
                "absensi", "kehadiran", "karyawan", "pegawai", "lembur", "overtime",
                "cuti", "sakit", "izin kerja", "gaji", "payroll", "hourly_overtime_rate",
                "leave_requests", "attendances"
            ]
            if any(hk in lower_prompt for hk in hr_keywords):
                return {
                    "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                    "action_type": "out_of_scope",
                    "message": f"Akses Ditolak: Permintaan ini di luar ranah kewenangan Anda. Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi {current_user.tenant_id}. Anda tidak memiliki akses ke alur kerja Schema B (Divisi HR) perusahaan.",
                    "generated_prs": [],
                    "affected_items": []
                }
        if u_tenant not in ["FINANCE", "USERC", "TENANT_C"]:
            fin_keywords = [
                "laporan pendapatan", "pendapatan sewa", "sewa menara", "arus kas",
                "beban pengeluaran", "listrik pln", "beban listrik", "revenue",
                "tagihan operator", "mla_contracts", "kontrak mla", "site_land_leases",
                "sewa lahan", "faktur invoice", "revenue_invoices",
                "onboarding klien", "billing"
            ]
            if any(fk in lower_prompt for fk in fin_keywords):
                return {
                    "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                    "action_type": "out_of_scope",
                    "message": f"Akses Ditolak: Akun Anda ({current_user.username} - Divisi {u_tenant}) tidak memiliki izin mengakses data Schema C (Divisi Keuangan). Akses ini dilindungi dan hanya dapat dibuka oleh staf Divisi Keuangan atau Super Administrator.",
                    "generated_prs": [],
                    "affected_items": []
                }
        if u_tenant not in ["INVENTORY", "USERA", "TENANT_A"]:
            inv_keywords = [
                "stok", "material", "gudang", "restock", "buatkan pr", "bikin pr", "draf pr",
                "purchase order", "po-", "safety stock", "stock_balances", "inventory_items",
                "barang masuk", "goods receipt", "reorder"
            ]
            if any(ik in lower_prompt for ik in inv_keywords):
                return {
                    "parsed_intent": {"workflow_id": "tenant_boundary_restricted"},
                    "action_type": "out_of_scope",
                    "message": f"Akses Ditolak: Permintaan ini di luar ranah kewenangan Anda. Akun Anda ({current_user.username}) terdaftar khusus untuk Divisi {current_user.tenant_id}. Anda tidak memiliki akses ke alur kerja Schema A (Divisi Logistik / Material Gudang) perusahaan.",
                    "generated_prs": [],
                    "affected_items": []
                }

    # 4. Primary: Match User Prompt to Admin-Created / Predefined Workflows
    from agents.router import SemanticRouter
    from agents.json_executor import JSONExecutionEngine
    from database.db import get_db_connection

    routing_res = await SemanticRouter.route_prompt(
        prompt=request.prompt,
        tenant_id=u_tenant,
        history=request.history
    )

    wf_id = routing_res.get("workflow_id") if isinstance(routing_res, dict) else None

    # Handle LLM-determined clarification requirement
    if isinstance(routing_res, dict) and (routing_res.get("needs_clarification") or wf_id == "clarification_needed"):
        clarif = routing_res.get("clarification") or {
            "title": "Klarifikasi Diperlukan",
            "message": routing_res.get("message", "Mohon lengkapi parameter instruksi Anda."),
            "hint": request.prompt
        }
        return {
            "parsed_intent": {"workflow_id": "clarification_needed"},
            "action_type": "clarification_needed",
            "message": clarif.get("message", "Mohon lengkapi parameter instruksi Anda."),
            "clarification": clarif,
            "generated_prs": [],
            "affected_items": []
        }

    if wf_id:
        conn = get_db_connection(read_only=True)
        row = None
        try:
            row = conn.execute("SELECT id, name, description, business_instruction, compiled_json, tenant_id FROM workflows WHERE id = ?", [wf_id]).fetchone()
        finally:
            conn.close()

        if row:
            wf_id_db, wf_name, wf_desc, wf_inst, wf_compiled_raw, wf_tenant = row
            try:
                compiled_json = json.loads(wf_compiled_raw) if isinstance(wf_compiled_raw, str) else wf_compiled_raw
            except Exception:
                compiled_json = {}

            if stage_callback:
                await stage_callback("plan", f"Memilih workflow: '{wf_name}' ({wf_id})...")

            custom_context = {
                "prompt": request.prompt,
                "username": current_user.username if current_user else "user",
                "role": current_user.role if current_user else "USER",
                "tenant_id": u_tenant,
                "recipient_email": request.recipient_email or routing_res.get("recipient_email"),
                "send_email": routing_res.get("send_email", False),
                "new_item_data": routing_res.get("new_item_data"),
                "threshold_updates": routing_res.get("threshold_updates", []),
                "target_item_name": routing_res.get("target_item_name"),
                "workflow_id": wf_id,
                "workflow_name": wf_name,
                "user_info": {
                    "username": current_user.username if current_user else "user",
                    "role": current_user.role if current_user else "USER",
                    "tenant_id": u_tenant
                }
            }

            if stage_callback:
                await stage_callback("execute", f"Mengeksekusi tahapan alur kerja '{wf_name}'...")

            exec_result = await JSONExecutionEngine.execute(
                compiled_json=compiled_json,
                tenant_id=u_tenant,
                custom_context=custom_context
            )

            target_po_id = exec_result.get("target_po_id") or custom_context.get("target_po_id")
            target_po_num = exec_result.get("target_po_number") or custom_context.get("target_po_number")
            
            is_hr_tenant = u_tenant in ["HR", "TENANT_B", "userb"]
            is_fin_tenant = u_tenant in ["FINANCE", "TENANT_C", "userc"]

            str_compiled = str(compiled_json).lower()
            if is_hr_tenant:
                if exec_result.get("mutated_employee") or "mutasi" in str_compiled or "mutate" in str_compiled:
                    action_type = "hr_mutation"
                elif exec_result.get("leave_id") or any(
                    tool in str_compiled for tool in ("hr.submit_leave_request", "hr.approve_leave")
                ):
                    action_type = "hr_leave"
                else:
                    action_type = "hr_query"
                target_po_id = None
                target_po_num = None
            elif is_fin_tenant:
                if exec_result.get("onboarding_id") or "onboard" in str_compiled:
                    action_type = "finance_onboarding"
                else:
                    action_type = "finance_query"
                target_po_id = None
                target_po_num = None
            elif "view_po" in str_compiled or target_po_id:
                action_type = "view_po_document"
            elif exec_result.get("onboarding_id") or "onboard" in str_compiled:
                action_type = "finance_onboarding"
            elif wf_id in ["WF-C01", "WF-C02", "WF-C04", "WF-004", "WF-005"] or "finance.revenue_report" in str_compiled or "finance.opex_audit" in str_compiled or "finance.cashflow_summary" in str_compiled:
                action_type = "finance_query"
            elif wf_id in ["WF-B02", "WF-B03", "WF-B04", "WF-003"] or "hr.filter_candidates" in str_compiled or "hr.audit_attendance" in str_compiled or "pending_leaves" in custom_context:
                action_type = "hr_query"
            elif wf_id in ["WF-ALL-01", "WF-ALL-02", "WF-ALL-03"] or "system.check_profile" in str_compiled or "system.get_system_info" in str_compiled or "system.get_company_guidelines" in str_compiled:
                action_type = "general"
            elif exec_result.get("registered_item") or "register_product" in str_compiled:
                action_type = "register_product"
            elif "update_threshold" in str_compiled:
                action_type = "update_threshold"
            elif exec_result.get("pr_number") or ("restock" in str_compiled and not exec_result.get("registered_item")):
                action_type = "review_prs"
            else:
                action_type = "workflow_execution"

            prs_list = []
            if not is_hr_tenant and not is_fin_tenant:
                prs_list = [exec_result["pr_number"]] if exec_result.get("pr_number") else []
                if exec_result.get("pr_number"):
                    from api.routers.approval_routes import PR_STORE
                    pr_doc = PR_STORE.get(exec_result["pr_number"])
                    if pr_doc:
                        prs_list = [{
                            "pr_number": pr_doc.pr_number,
                            "supplier_name": "Multiple Vendors" if len(set(it.vendor_name for it in pr_doc.items)) > 1 else (pr_doc.items[0].vendor_name if pr_doc.items else "Vendor"),
                            "grand_total": pr_doc.total_budget,
                            "status": pr_doc.status.lower(),
                            "email_sent": exec_result.get("email_sent", False),
                            "items": [{"item_name": it.name, "quantity": it.reorder_qty, "unit": it.unit} for it in pr_doc.items]
                        }]

            return {
                "parsed_intent": {"workflow_id": wf_id, "workflow_name": wf_name},
                "action_type": action_type,
                "message": exec_result.get("summary", ""),
                "email_sent": exec_result.get("email_sent", False),
                "generated_prs": prs_list,
                "prs": prs_list,
                "affected_items": exec_result.get("affected_items", []),
                "total_items_analyzed": exec_result.get("total_items_analyzed", len(exec_result.get("affected_items", []))),
                "target_destinations": exec_result.get("target_destinations", ["database"]),
                "pdf_download_url": exec_result.get("pdf_download_url") if not is_hr_tenant else (exec_result.get("pdf_download_url") if "leave" in str(exec_result.get("pdf_download_url", "")) else None),
                "po_id": target_po_id,
                "po_number": target_po_num,
                "onboarding_id": exec_result.get("onboarding_id"),
                "client_name": exec_result.get("client_name"),
                "site_id": exec_result.get("site_id"),
                "total_billed": exec_result.get("total_billed", 0),
                "leave_id": exec_result.get("leave_id"),
                "applicant_name": exec_result.get("applicant_name"),
                "leave_type": exec_result.get("leave_type"),
                "days_requested": exec_result.get("days_requested"),
                "mutated_employee": exec_result.get("mutated_employee"),
                "execution_steps": exec_result.get("execution_steps", []),
                "total_budget_formatted": exec_result.get("total_budget_formatted", "Rp 0")
            }

    # 6. Fallback: Core Autonomous Agent Reasoning & Execution (for ad-hoc queries / free-form)
    from agents.autonomous_agent import AutonomousAgent
    agent_result = await AutonomousAgent.run(
        prompt=request.prompt,
        current_user=current_user,
        stage_callback=stage_callback,
        history=request.history
    )

    can_propose = classify_workflow_proposal_eligibility(
        prompt=request.prompt,
        agent_result=agent_result,
        user_role=getattr(current_user, "role", "USER")
    )

    dashboard_response = {
        "parsed_intent": agent_result.get("parsed_intent", {"workflow_id": "autonomous_agent"}),
        "action_type": agent_result.get("action_type", "general"),
        "message": agent_result.get("message", ""),
        "email_sent": agent_result.get("email_sent", False),
        "generated_prs": agent_result.get("generated_prs", []),
        "prs": agent_result.get("prs", []),
        "affected_items": agent_result.get("affected_items", []),
        "total_items_analyzed": agent_result.get("total_items_analyzed", len(agent_result.get("affected_items", []))),
        "target_destinations": agent_result.get("target_destinations", ["database"]),
        "pdf_download_url": agent_result.get("pdf_download_url"),
        "po_id": agent_result.get("po_id"),
        "po_number": agent_result.get("po_number"),
        "onboarding_id": agent_result.get("onboarding_id"),
        "client_name": agent_result.get("client_name"),
        "site_id": agent_result.get("site_id"),
        "total_billed": agent_result.get("total_billed", 0),
        "leave_id": agent_result.get("leave_id"),
        "applicant_name": agent_result.get("applicant_name"),
        "leave_type": agent_result.get("leave_type"),
        "days_requested": agent_result.get("days_requested"),
        "execution_steps": agent_result.get("execution_steps", []),
        "total_budget_formatted": agent_result.get("total_budget_formatted", "Rp 0"),
        "can_request_admin": can_propose,
        "prompt_text": request.prompt
    }

    if agent_result.get("generated_prs") and not dashboard_response["prs"]:
        dashboard_response["prs"] = agent_result["generated_prs"]

    return dashboard_response




@router.post("/api/agent/custom-prompt")
async def execute_custom_prompt_workflow(request: CustomPromptRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Accepts free-form natural language instructions from non-technical users,
    synthesizes a custom multi-agent workflow, executes actions, and dispatches outputs.
    """
    return await execute_prompt_logic(request, current_user)


@router.post("/api/agent/stream-prompt")
async def execute_custom_prompt_workflow_stream(request: CustomPromptRequest, current_user: TokenData = Depends(get_current_user)):
    """
    Real-Time SSE Streaming Endpoint for interactive Chat Dashboard (TTPS Optimization).
    Streams live stage status badges, clarification questions, token-by-token content,
    and final rich interactive dashboard response card.
    """
    async def event_generator():
        stages_queue = asyncio.Queue()

        async def stage_cb(stage: str, message: str):
            await stages_queue.put({"type": "status", "stage": stage, "message": message})

        # 1. Instant Initial Stage Badge (TTPS < 20ms)
        yield f"data: {json.dumps({'type': 'status', 'stage': 'analyze', 'message': 'Menganalisis instruksi & hak akses wewenang...'})}\n\n"

        # 2. Asynchronous execution with real-time stage forwarding
        task = asyncio.create_task(execute_prompt_logic(request, current_user, stage_callback=stage_cb))

        while not task.done():
            try:
                stage_msg = await asyncio.wait_for(stages_queue.get(), timeout=0.08)
                yield f"data: {json.dumps(stage_msg)}\n\n"
            except asyncio.TimeoutError:
                pass

        # Drain any remaining stage events
        while not stages_queue.empty():
            stage_msg = stages_queue.get_nowait()
            yield f"data: {json.dumps(stage_msg)}\n\n"

        try:
            result = await task
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        # 3. Clarification event if parameters missing
        if result.get("action_type") == "clarification_needed":
            yield f"data: {json.dumps({'type': 'clarification', 'clarification': result.get('clarification'), 'message': result.get('message')})}\n\n"

        # 4. Token-by-token streaming for ultra-fluid typing effect
        msg = result.get("message", "")
        if msg:
            words = msg.split(" ")
            for i, w in enumerate(words):
                token = w + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                await asyncio.sleep(0.01)

        # 5. Final complete event with rich interactive payload
        yield f"data: {json.dumps({'type': 'complete', 'payload': result})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/agent/prompt-templates")
def get_prompt_templates():
    """
    Returns curated 1-click prompt templates for non-technical users tailored to Bali Tower.
    """
    return [
        {
            "id": 1,
            "title": "Cek Stok Kritis & Buat Draf PR",
            "prompt": "Periksa stok material menara yang menipis dan buatkan draf Purchase Requisition (PR)."
        },
        {
            "id": 2,
            "title": "Catat Penerimaan Barang PO Tiba",
            "prompt": "Barang untuk PO-2026-006 sudah sampai di Gudang Bandung, tolong catat penerimaannya."
        },
        {
            "id": 3,
            "title": "Lihat & Unduh Dokumen PO Resmi",
            "prompt": "Tolong tampilkan dokumen PDF untuk PO-2026-006."
        },
        {
            "id": 4,
            "title": "Absensi & Lembur Teknisi Lapangan",
            "prompt": "Tampilkan rekap absensi kunjungan site menara teknisi rigger minggu ini beserta validasi geofencing GPS dan total jam lembur."
        },
        {
            "id": 4,
            "title": "Filter Pelamar Rigger K3 TKPK",
            "prompt": "Saring kandidat pelamar posisi Rigger / Tower Climber yang memiliki sertifikasi K3 TKPK aktif dan berstatus layak naik menara (Fit for Height)."
        },
        {
            "id": 5,
            "title": "Laporan Pemasukan Sewa Menara",
            "prompt": "Tampilkan ringkasan pendapatan sewa menara dari operator Telkomsel, XL, dan Indosat beserta piutang invoice yang belum dibayar."
        },
        {
            "id": 6,
            "title": "Biaya Listrik PLN & Sewa Lahan",
            "prompt": "Tampilkan rincian pengeluaran beban operasional untuk tagihan listrik PLN shelter dan sewa lahan lokasi menara per site."
        },
        {
            "id": 7,
            "title": "Ringkasan Arus Kas Operasional",
            "prompt": "Berapa total kas masuk (inflow) versus kas keluar (outflow) dan surplus kas bersih operasional saat ini?"
        }
    ]



@router.get("/api/agent/tools", tags=["Agent Configuration"])
def get_agent_tools(current_user: TokenData = Depends(get_current_user)):
    '''
    Returns the comprehensive list of tools (APIs) available to the AI model
    for executing autonomous workflows. Requires authentication.
    '''
    return {
        "status": "success",
        "available_tools": [
            {
                "tool_name": "inventory.register_product",
                "description": "Registers and inserts new product items into the active tenant's inventory database."
            },
            {
                "tool_name": "inventory.get_low_stock_products",
                "description": "Queries products that have fallen below their minimum safety threshold."
            },
            {
                "tool_name": "inventory.get_all_products",
                "description": "Queries all products for full warehouse audits."
            },
            {
                "tool_name": "inventory.check_specific_stock",
                "description": "Queries the current stock level of a specific product."
            },
            {
                "tool_name": "inventory.update_threshold",
                "description": "Updates the safety stock threshold bounds for a product."
            },
            {
                "tool_name": "inventory.crud_record",
                "description": "Performs generic database record operations."
            },
            {
                "tool_name": "notification.dispatch",
                "description": "Dispatches system alerts to configured notification channels."
            },
            {
                "tool_name": "notification.send_email",
                "description": "Sends detailed HTML email notifications to stakeholders."
            },
            {
                "tool_name": "docgen.compile",
                "description": "Compiles raw data into formal Typst PDF documents."
            },
            {
                "tool_name": "purchase_order.create_draft",
                "description": "Generates a draft Purchase Requisition (PR) document based on low stock data."
            },
            {
                "tool_name": "hr.mutate_employee",
                "description": "Melakukan mutasi posisi/jabatan dan departemen karyawan pada basis data master kepegawaian PT Bali Towerindo Sentra Tbk."
            },
            {
                "tool_name": "hr.approve_leave",
                "description": "Otorisasi permohonan cuti karyawan (APPROVED) dan pemotongan otomatis kuota saldo cuti tahunan."
            },
            {
                "tool_name": "hr.audit_attendance",
                "description": "Audit absensi GPS geofencing teknisi site tower dan perhitungan jam kerja lembur."
            },
            {
                "tool_name": "hr.filter_candidates",
                "description": "Penyaringan kandidat Rigger Menara berkualifikasi sertifikat K3 TKPK tingkat 1 atau tingkat 2."
            },
            {
                "tool_name": "hr.submit_leave_request",
                "description": "Merekam pengajuan cuti teknisi/karyawan baru ke dalam basis data DuckDB."
            },
            {
                "tool_name": "docgen.compile_leave_pdf",
                "description": "Mengompilasi dokumen resmi Surat Pengajuan Cuti karyawan ke format PDF Typst dengan kop surat PT Bali Towerindo Sentra Tbk."
            },
            {
                "tool_name": "hr.query_pending_leaves",
                "description": "Memeriksa dan merekap seluruh pengajuan cuti karyawan yang berstatus PENDING_APPROVAL."
            },
            {
                "tool_name": "finance.draft_client_onboarding",
                "description": "Menyusun draft pendaftaran klien operator baru & kontrak sewa menara (MLA) serta estimasi tagihan perdana berstatus PENDING_APPROVAL untuk otorisasi email."
            },
            {
                "tool_name": "finance.approve_client_onboarding",
                "description": "Mengesahkan otorisasi onboarding klien operator: mengaktifkan data klien, menerbitkan kontrak MLA aktif, dan menerbitkan invoice perdana di database."
            },
            {
                "tool_name": "finance.audit_client_onboardings",
                "description": "Memeriksa daftar pengajuan sewa menara dan pendaftaran operator baru yang masih menunggu otorisasi persetujuan."
            },
            {
                "tool_name": "finance.revenue_report",
                "description": "Menampilkan rekapitulasi pendapatan sewa menara per operator, total tagihan terbit, pembayaran lunas, dan piutang (AR)."
            },
            {
                "tool_name": "finance.opex_audit",
                "description": "Audit transaksi beban operasional site (OPEX) termasuk listrik PLN, sewa lahan, dan bahan bakar genset."
            },
            {
                "tool_name": "finance.cashflow_summary",
                "description": "Menghitung ringkasan arus kas operasional (Inflow vs Outflow) dan surplus kas bersih perusahaan."
            }
        ]
    }

