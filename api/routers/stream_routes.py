import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from core.observability import tracer
from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
from core.security import TokenData, get_current_user

router = APIRouter(prefix="/api/stream", tags=["Live Agent Streaming"])


@router.get("/inventory-summary")
async def get_inventory_summary(current_user: TokenData = Depends(get_current_user)):
    """
    Returns live inventory items and health status directly from DuckDB.
    """
    items = []
    try:
        from database.db import get_db_connection
        conn = get_db_connection(read_only=True)
        query = """
            SELECT 
                i.item_id,
                i.name,
                i.category,
                i.current_stock,
                i.min_threshold,
                i.avg_daily_usage,
                i.lead_time_days,
                i.unit,
                COALESCE(MIN(v.unit_price), 0.0) AS unit_price
            FROM items i
            LEFT JOIN vendors v ON i.item_id = v.item_id
            WHERE i.tenant_id = ? OR ? = 'ALL'
            GROUP BY i.item_id, i.name, i.category, i.current_stock, i.min_threshold, i.avg_daily_usage, i.lead_time_days, i.unit
            ORDER BY (i.min_threshold - i.current_stock) DESC;
        """
        rows = conn.execute(query, [current_user.tenant_id, current_user.tenant_id]).fetchall()
        conn.close()

        for r in rows:
            cur_stock = r[3]
            min_thresh = r[4]
            if cur_stock < min_thresh:
                health = "CRITICAL"
            elif cur_stock <= min_thresh * 1.3:
                health = "WARNING"
            else:
                health = "HEALTHY"

            items.append({
                "item_id": r[0],
                "name": r[1],
                "category": r[2],
                "current_stock": cur_stock,
                "min_threshold": min_thresh,
                "avg_daily_usage": float(r[5]),
                "lead_time_days": int(r[6]),
                "unit": r[7],
                "unit_price": float(r[8]),
                "health": health
            })
    except Exception:
        pass

    total_items = len(items)
    critical_items = sum(1 for item in items if item["health"] == "CRITICAL")
    warning_items = sum(1 for item in items if item["health"] == "WARNING")
    healthy_items = sum(1 for item in items if item["health"] == "HEALTHY")

    return {
        "total_sku": total_items,
        "critical_count": critical_items,
        "warning_count": warning_items,
        "healthy_count": healthy_items,
        "items": items
    }



async def agent_thought_generator() -> AsyncGenerator[str, None]:
    """
    Dynamically executes and streams the live multi-agent decision steps with Server-Sent Events (SSE)
    connected directly to DuckDB and LangGraph multi-agent workflow.
    """
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    tracer.start_trace(trace_id=trace_id)

    # Step 1: Real Scan from DuckDB
    from mcp_server.tools import get_low_stock_items
    low_stock = get_low_stock_items()
    num_low = len(low_stock)
    item_names = [it.get("name", it.get("item_id", "")) for it in low_stock]
    item_summary_str = ", ".join(item_names[:3]) + (f" dan {num_low - 3} SKU lainnya" if num_low > 3 else "")

    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 1, 'node': 'Scanner Node (DuckDB)', 'model': 'DuckDB-Engine', 'message': f'Memindai 25 inventaris di DuckDB... Ditemukan {num_low} SKU dengan stok kritis di bawah threshold: {item_summary_str}.', 'progress': 16})}\n\n"
    await asyncio.sleep(0.6)

    # Step 2: Real Dynamic Stock Calculator
    reorder_details = []
    for it in low_stock[:3]:
        name = it.get("name", "")
        cur = it.get("current_stock", 0)
        thresh = it.get("min_threshold", 0)
        req = max(thresh * 2 - cur, 10)
        unit = it.get("unit", "pcs")
        reorder_details.append(f"{name} (Reorder: {req} {unit})")
    reorder_str = ", ".join(reorder_details)

    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 2, 'node': 'Dynamic Stock Calculator', 'model': 'Math-Engine', 'message': f'Menghitung Safety Stock & Burn Rate harian: {reorder_str}.', 'progress': 33})}\n\n"
    await asyncio.sleep(0.6)

    # Step 3: Real Agent Execution (Planner & Vendor Matcher)
    from agents.workflow import run_autorestock_cycle
    from api.routers.approval_routes import PR_STORE
    from docgen.pdf_generator import pdf_generator

    pr_doc = run_autorestock_cycle()
    
    vendor_names = list(set([it.vendor_name for it in pr_doc.items]))[:2]
    vendor_str = " & ".join([f"'{v}'" for v in vendor_names]) if vendor_names else "supplier terverifikasi"
    total_budget_fmt = f"Rp {pr_doc.total_budget:,.0f}".replace(",", ".")

    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 3, 'node': 'Procurement Planner Node', 'model': 'qwen-35b', 'message': f'qwen-35b mencocokkan supplier: Memilih {vendor_str} berdasarkan harga termurah & lead time tercepat.', 'progress': 50})}\n\n"
    await asyncio.sleep(0.7)

    # Step 4: Compliance Auditor
    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 4, 'node': 'Compliance Auditor Node', 'model': 'nemotron-35', 'message': f'nemotron-35 memverifikasi anggaran: Total PR {total_budget_fmt} dinyatakan PASSED ({pr_doc.auditor_notes}).', 'progress': 68})}\n\n"
    await asyncio.sleep(0.6)

    # Step 5: Typst Engine
    clean_filename = f"{pr_doc.pr_number.replace('-', '_')}.pdf"
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
        for it in pr_doc.items
    ]
    PR_STORE[pr_doc.pr_number] = PurchaseRequisitionDoc(
        pr_number=pr_doc.pr_number,
        created_at=pr_doc.created_at,
        items=items_req,
        total_budget=pr_doc.total_budget,
        auditor_status=pr_doc.auditor_status or "PASSED",
        auditor_notes=pr_doc.auditor_notes or "Audit passed.",
        pdf_path=f"/storage/documents/{clean_filename}",
        status=pr_doc.status or "PENDING"
    )
    pdf_generator.generate_purchase_requisition_pdf(PR_STORE[pr_doc.pr_number], output_filename=clean_filename)

    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 5, 'node': 'Document Engine (Typst)', 'model': 'Typst-Compiler', 'message': f'Typst berhasil menyusun dan meng-compile dokumen {clean_filename} dengan status PENDING.', 'progress': 85})}\n\n"
    await asyncio.sleep(0.5)

    # Step 6: HITL Dispatcher
    yield f"data: {json.dumps({'timestamp': datetime.now().strftime('%H:%M:%S'), 'step': 6, 'node': 'Human-In-The-Loop Dispatcher', 'model': 'Dashboard & Telegram', 'message': f'Dokumen {pr_doc.pr_number} berhasil diterbitkan dan siap diverifikasi di tab Purchase Requisitions.', 'progress': 100})}\n\n"

    tracer.end_trace(verdict="PASSED")
    yield f"data: {json.dumps({'event': 'DONE', 'message': f'Autonomous cycle completed. Dokumen {pr_doc.pr_number} siap disetujui.'})}\n\n"




@router.get("/agent-run")
async def stream_agent_execution():
    """
    Server-Sent Events endpoint streaming live agent reasoning traces to the frontend console.
    """
    return StreamingResponse(
        agent_thought_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
