import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from core.config import settings
from database.db import db
from database.seed_data import seed_database
from multimodal.ocr_engine import ocr_engine
from multimodal.vision_auditor import vision_auditor
from multimodal.visualizer import visualizer
from docgen.pdf_generator import pdf_generator
from core.llm_client import llm_client
from agents.workflow import workflow
from api.main import app


def test_database_and_seed():
    """Verify database initialization and seeding."""
    seed_database()
    items = db.get_items()
    assert len(items) >= 10
    
    suppliers = db.get_suppliers()
    assert len(suppliers) >= 5
    
    stats = db.get_dashboard_stats()
    assert stats.total_items == len(items)
    assert stats.total_suppliers == len(suppliers)
    print("[PASS] Database and Seed test passed.")


def test_stock_adjustment():
    """Verify inventory update and transaction logs."""
    item = db.get_item_by_sku("FMCG-MINYAK-01")
    assert item is not None
    initial_stock = item.current_stock
    
    updated = db.update_stock("FMCG-MINYAK-01", change=10, transaction_type="manual_test", notes="Unit test adjustment")
    assert updated.current_stock == initial_stock + 10
    
    # Revert
    db.update_stock("FMCG-MINYAK-01", change=-10, transaction_type="manual_revert", notes="Unit test revert")
    print("[PASS] Stock Adjustment test passed.")


async def test_llm_prompt_parsing():
    """Verify intelligent prompt understanding in Indonesian."""
    items = [it.model_dump() for it in db.get_items()]
    
    prompt = "Tolong pesan 25 box Kertas HVS A4 dan restock Beras Ramos ke supplier Alfaria segera URGENT"
    parsed = await llm_client.parse_restock_prompt(prompt, items)
    
    assert parsed.intent_type == "restock"
    assert parsed.urgency == "URGENT"
    assert "Office Supplies" in parsed.target_categories or len(parsed.target_skus) > 0 or parsed.quantity_specified == 25
    print("[PASS] LLM Prompt Parsing test passed.")


async def test_ocr_and_auditor():
    """Verify OCR extraction and discrepancy detection."""
    sample_file = settings.DATA_DIR / "samples" / "kartu_stok_warehouse.png"
    if sample_file.exists():
        extracted = await ocr_engine.process_document(str(sample_file))
        assert len(extracted.line_items) > 0
        
        report = vision_auditor.audit_document(extracted)
        assert report.doc_number == extracted.doc_number
        
        annotated_path = visualizer.annotate_document(str(sample_file), extracted, report)
        assert Path(annotated_path).exists()
        print("[PASS] OCR & Vision Auditor test passed.")


async def test_agent_workflow():
    """Verify end-to-end multi-agent execution."""
    prompt = "Restock semua barang yang stoknya di bawah batas minimum"
    result = await workflow.execute_prompt_restock(prompt, auto_execute=True)
    assert result.get("status") == "completed"
    print(f"[PASS] Multi-Agent Workflow test passed: {len(result.get('generated_prs', []))} PR(s) created.")


def test_api_endpoints():
    """Verify FastAPI endpoints via TestClient."""
    client = TestClient(app)
    
    # Health
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"
    
    # Inventory items
    r = client.get("/api/inventory/items")
    assert r.status_code == 200
    assert len(r.json()) > 0
    
    # Stats
    r = client.get("/api/inventory/stats")
    assert r.status_code == 200
    assert "total_items" in r.json()
    
    # Approvals list
    r = client.get("/api/approvals/all")
    assert r.status_code == 200
    
    # Prompt restock API
    r = client.post("/api/agent/prompt-restock", json={"prompt": "Cek dan restock barang low stock", "auto_execute": True})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    
    print("[PASS] FastAPI Endpoints test passed.")


if __name__ == "__main__":
    test_database_and_seed()
    test_stock_adjustment()
    asyncio.run(test_llm_prompt_parsing())
    asyncio.run(test_ocr_and_auditor())
    asyncio.run(test_agent_workflow())
    test_api_endpoints()
    print("\n[ALL TESTS PASSED SUCCESSFULLY!]")
