import asyncio
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from starlette.testclient import TestClient

from api.main import app
from bot.telegram_bot import telegram_bot
from core.observability import tracer
from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
from docgen.pdf_generator import pdf_generator


class TestPerson2CompletePipeline(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.client.post("/api/approval/reset")


    def test_dashboard_ui_served(self):
        """
        Verifies that GET / serves the interactive HTML dashboard.
        """
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("AutoRestock-Agent", res.text)
        self.assertIn("Live Inventory", res.text)

    def test_inventory_summary_endpoint(self):
        """
        Verifies GET /api/stream/inventory-summary
        """
        res = self.client.get("/api/stream/inventory-summary")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total_sku"], 4)
        self.assertGreaterEqual(data["critical_count"], 1)

    def test_approval_flow_endpoints(self):
        """
        Verifies GET /api/approval/list and POST /api/approval/action
        """
        list_res = self.client.get("/api/approval/list")
        self.assertEqual(list_res.status_code, 200)
        items = list_res.json()
        self.assertGreaterEqual(len(items), 1)

        pr_num = items[0]["pr_number"]
        action_res = self.client.post("/api/approval/action", json={
            "pr_number": pr_num,
            "action": "APPROVE",
            "manager_name": "Test Manager"
        })
        self.assertEqual(action_res.status_code, 200)
        self.assertEqual(action_res.json()["new_status"], "APPROVED")

    def test_observability_tracer(self):
        """
        Verifies tracer span management and metrics recording
        """
        trace = tracer.start_trace(trace_id="test-trace-01")
        span = tracer.start_span("span-01", "Test-Planner-Node", "qwen-35b")
        tracer.end_span(span, output_payload={"status": "ok"}, tokens=150)
        finished_trace = tracer.end_trace(trace, verdict="PASSED")

        self.assertEqual(finished_trace.trace_id, "test-trace-01")
        self.assertEqual(finished_trace.total_tokens_estimated, 150)
        self.assertEqual(finished_trace.compliance_verdict, "PASSED")
        self.assertGreaterEqual(len(finished_trace.spans), 1)

    def test_pdf_generation_typst(self):
        """
        Verifies PDF generator produces valid PDF file
        """
        sample_pr = PurchaseRequisitionDoc(
            pr_number="PR-TEST-001",
            created_at="2026-08-19 10:00",
            items=[
                PurchaseItemRequest(
                    item_id="ITEM-01",
                    name="Test Item Baut",
                    reorder_qty=100,
                    unit="pcs",
                    vendor_id="VEND-01",
                    vendor_name="PT. Vendor Test",
                    unit_price=1000.0,
                    total_price=100000.0,
                    reason="Test reorder"
                )
            ],
            total_budget=100000.0,
            auditor_status="PASSED",
            auditor_notes="Valid test budget"
        )
        pdf_path = pdf_generator.generate_purchase_requisition_pdf(sample_pr, output_filename="PR_TEST_001.pdf")
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 0)

    def test_telegram_bot_dispatch_simulation(self):
        """
        Verifies Telegram Bot dispatch runs cleanly in simulation mode
        """
        async def _run():
            sample_pr = PurchaseRequisitionDoc(
                pr_number="PR-TEST-002",
                created_at="2026-08-19 10:00",
                items=[],
                total_budget=500000.0,
                auditor_status="PASSED",
                auditor_notes="Compliance pass"
            )
            result = await telegram_bot.send_restock_approval_request(sample_pr)
            self.assertIn(result["status"], ["simulated", "sent"])

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
