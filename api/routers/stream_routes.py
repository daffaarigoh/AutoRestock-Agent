import asyncio
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.observability import tracer
from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc

router = APIRouter(prefix="/api/stream", tags=["Live Agent Streaming"])


# Sample inventory state
LIVE_INVENTORY = [
    {
        "item_id": "ITEM-BAUT-M8",
        "name": "Baut Baja Hitam M8 x 50mm",
        "category": "Fasteners",
        "current_stock": 12,
        "min_threshold": 100,
        "unit": "pcs",
        "avg_daily_usage": 25.0,
        "lead_time_days": 2,
        "unit_price": 2500.0,
        "health": "CRITICAL"
    },
    {
        "item_id": "ITEM-OLI-68",
        "name": "Oli Hidrolik ISO VG 68 20L",
        "category": "Lubricants",
        "current_stock": 1,
        "min_threshold": 5,
        "unit": "pail",
        "avg_daily_usage": 0.5,
        "lead_time_days": 3,
        "unit_price": 875000.0,
        "health": "CRITICAL"
    },
    {
        "item_id": "ITEM-LAKBAN-2IN",
        "name": "Lakban Coklat 2 Inch 100m",
        "category": "Packaging",
        "current_stock": 18,
        "min_threshold": 30,
        "unit": "roll",
        "avg_daily_usage": 4.0,
        "lead_time_days": 2,
        "unit_price": 18500.0,
        "health": "WARNING"
    },
    {
        "item_id": "ITEM-KERTAS-A4",
        "name": "Kertas Box A4 80gr",
        "category": "Office",
        "current_stock": 85,
        "min_threshold": 20,
        "unit": "box",
        "avg_daily_usage": 2.0,
        "lead_time_days": 1,
        "unit_price": 45000.0,
        "health": "HEALTHY"
    }
]


@router.get("/inventory-summary")
async def get_inventory_summary():
    """
    Returns live inventory items and health status.
    """
    total_items = len(LIVE_INVENTORY)
    critical_items = sum(1 for item in LIVE_INVENTORY if item["health"] == "CRITICAL")
    warning_items = sum(1 for item in LIVE_INVENTORY if item["health"] == "WARNING")
    healthy_items = sum(1 for item in LIVE_INVENTORY if item["health"] == "HEALTHY")

    return {
        "total_sku": total_items,
        "critical_count": critical_items,
        "warning_count": warning_items,
        "healthy_count": healthy_items,
        "items": LIVE_INVENTORY
    }


async def agent_thought_generator() -> AsyncGenerator[str, None]:
    """
    Simulates / streams the live multi-agent decision steps with Server-Sent Events (SSE).
    """
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"
    tracer.start_trace(trace_id=trace_id)

    steps = [
        {
            "step": 1,
            "node": "Scanner Node (DuckDB)",
            "model": "DuckDB-Engine",
            "message": "Memindai seluruh inventaris di DuckDB... Ditemukan 2 SKU dengan stok di bawah threshold.",
            "delay": 0.4
        },
        {
            "step": 2,
            "node": "Dynamic Stock Calculator",
            "model": "Math-Engine",
            "message": "Menghitung Safety Stock & Burn Rate: Baut M8 (Reorder Qty: 500 pcs), Oli Hidrolik (Reorder Qty: 4 pail).",
            "delay": 0.5
        },
        {
            "step": 3,
            "node": "Procurement Planner Node",
            "model": "qwen-35b",
            "message": "qwen-35b mencocokkan supplier: Memilih 'PT. Sumber Makmur' (Baut) & 'PT. Pelumas Nusantara' (Oli) berdasarkan SLA 2 hari & harga termurah.",
            "delay": 0.7
        },
        {
            "step": 4,
            "node": "Compliance Auditor Node",
            "model": "nemotron-35",
            "message": "nemotron-35 memverifikasi anggaran: Total PR Rp 4.750.000 dinyatakan PASSED (dalam batas alokasi anggaran Q3).",
            "delay": 0.6
        },
        {
            "step": 5,
            "node": "Document Engine (Typst)",
            "model": "Typst-Compiler",
            "message": "Typst meng-compile dokumen resmi Purchase Requisition PR-2026-0819-001.pdf (Kompilasi selesai dalam 28ms).",
            "delay": 0.4
        },
        {
            "step": 6,
            "node": "Human-In-The-Loop Dispatcher",
            "model": "Telegram-Webhook",
            "message": "Notifikasi persetujuan berhasil dikirim ke Telegram Manajer & Dashboard. Menunggu persetujuan...",
            "delay": 0.3
        }
    ]

    for s in steps:
        await asyncio.sleep(s["delay"])
        span = tracer.start_span(
            span_id=f"span-{s['step']}",
            node_name=s["node"],
            model_name=s["model"],
            input_payload={"step": s["step"]}
        )
        tracer.end_span(span, output_payload={"message": s["message"]}, status="SUCCESS", tokens=120)

        payload = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "step": s["step"],
            "node": s["node"],
            "model": s["model"],
            "message": s["message"],
            "progress": int((s["step"] / len(steps)) * 100)
        }
        yield f"data: {json.dumps(payload)}\n\n"

    tracer.end_trace(verdict="PASSED")
    yield f"data: {json.dumps({'event': 'DONE', 'message': 'Autonomous cycle completed. PR document generated.'})}\n\n"


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
