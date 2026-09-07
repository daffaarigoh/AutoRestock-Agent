import sys
import unittest
from pathlib import Path

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient

from api.main import app
from core.observability import tracer
from core.schemas import PurchaseRequisitionDoc, RestockItem
from core.security import TokenData, get_current_admin, get_current_user
from docgen.compiler import generate_pr_pdf


def override_get_current_user():
    return TokenData(username="test_admin", role="ADMIN", tenant_id="TENANT_A")


app.dependency_overrides[get_current_user] = override_get_current_user
app.dependency_overrides[get_current_admin] = override_get_current_user


class TestAutoRestockPipeline(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.client.post("/api/approval/reset")

    def test_dashboard_ui_served(self):
        """Verifies that GET / serves the interactive HTML dashboard."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("AutoRestock", res.text)

    def test_inventory_summary_endpoint(self):
        """Verifies GET /api/stream/inventory-summary using real tenant data."""
        res = self.client.get("/api/stream/inventory-summary")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["total_sku"], 1)
        self.assertIn("items", data)

    def test_observability_tracer(self):
        """Verifies tracer span management and metrics recording."""
        trace = tracer.start_trace(trace_id="test-trace-01")
        span = tracer.start_span("span-01", "Test-Planner-Node", "qwen-35b")
        tracer.end_span(span, output_payload={"status": "ok"}, tokens=150)
        finished_trace = tracer.end_trace(trace, verdict="PASSED")

        self.assertEqual(finished_trace.trace_id, "test-trace-01")
        self.assertEqual(finished_trace.total_tokens_estimated, 150)
        self.assertEqual(finished_trace.compliance_verdict, "PASSED")
        self.assertGreaterEqual(len(finished_trace.spans), 1)

    def test_pdf_generation_typst(self):
        """Verifies Typst engine produces a valid PDF file."""
        sample_pr = PurchaseRequisitionDoc(
            pr_number="PR-TEST-001",
            created_at="2026-08-19 10:00",
            items=[
                RestockItem(
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
        pdf_path_str = generate_pr_pdf(sample_pr, output_path=WORKSPACE_DIR / "storage" / "documents" / "PR_TEST_001.pdf")
        pdf_path = Path(pdf_path_str)
        self.assertTrue(pdf_path.exists())
        self.assertGreater(pdf_path.stat().st_size, 0)

    def test_full_pipeline_cycles_and_approval(self):
        """Tests full end-to-end multi-agent restock cycle, approval, rejection, and PDF download."""
        # 1. Test GET /api/inventory/items
        res_items = self.client.get("/api/inventory/items")
        self.assertEqual(res_items.status_code, 200)
        items = res_items.json()
        self.assertGreaterEqual(len(items), 5)

        # 2. Test POST /api/agent/run-cycle (Cycle 1: For Approval)
        res_cycle1 = self.client.post("/api/agent/run-cycle")
        self.assertEqual(res_cycle1.status_code, 200)
        pr_data1 = res_cycle1.json()
        pr1_number = pr_data1["pr_number"]
        self.assertGreaterEqual(len(pr_data1["items"]), 1)

        # 3. Test POST /api/agent/approve (APPROVE Action)
        res_approve = self.client.post("/api/agent/approve", json={
            "pr_number": pr1_number,
            "action": "APPROVE",
            "approver_name": "Chief Operations Officer",
            "notes": "Approved for vendor procurement"
        })
        self.assertEqual(res_approve.status_code, 200)
        self.assertEqual(res_approve.json()["status"], "APPROVED")

        # 4. Test Download of Approved PDF
        res_download_appr = self.client.get(f"/api/documents/pr/{pr1_number}/download")
        self.assertEqual(res_download_appr.status_code, 200)
        self.assertEqual(res_download_appr.headers["content-type"], "application/pdf")

        # 5. Test POST /api/agent/run-cycle (Cycle 2: For Rejection)
        res_cycle2 = self.client.post("/api/agent/run-cycle")
        self.assertEqual(res_cycle2.status_code, 200)
        pr2_number = res_cycle2.json()["pr_number"]

        # 6. Test POST /api/agent/approve (REJECT Action)
        res_reject = self.client.post("/api/agent/approve", json={
            "pr_number": pr2_number,
            "action": "REJECT",
            "approver_name": "Finance Director",
            "notes": "Budget allocation delayed"
        })
        self.assertEqual(res_reject.status_code, 200)
        self.assertEqual(res_reject.json()["status"], "REJECTED")

        # 7. Test Download of Rejected PDF
        res_download_rej = self.client.get(f"/api/documents/pr/{pr2_number}/download")
        self.assertEqual(res_download_rej.status_code, 200)
        self.assertEqual(res_download_rej.headers["content-type"], "application/pdf")

        # 8. Test Threshold Customizer Endpoint (PATCH /api/inventory/items/...)
        first_item_id = items[0]["item_id"]
        res_threshold = self.client.patch(f"/api/inventory/items/{first_item_id}", json={
            "min_threshold": 80
        })
        self.assertEqual(res_threshold.status_code, 200)

        # 9. Test Prompt Templates Endpoint (GET /api/agent/prompt-templates)
        res_templates = self.client.get("/api/agent/prompt-templates")
        self.assertEqual(res_templates.status_code, 200)
        self.assertGreaterEqual(len(res_templates.json()), 4)


if __name__ == "__main__":
    unittest.main()
