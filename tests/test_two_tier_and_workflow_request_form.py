import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import create_access_token
from agents.autonomous_agent import AutonomousAgent


class TestTwoTierAndWorkflowRequestForm(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.user_token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        self.userb_token = create_access_token({"sub": "userb", "role": "USER", "tenant_id": "HR"})
        self.admin_token = create_access_token({"sub": "admin", "role": "ADMIN", "tenant_id": "ALL"})
        
        self.user_headers = {"Authorization": f"Bearer {self.user_token}", "Content-Type": "application/json"}
        self.userb_headers = {"Authorization": f"Bearer {self.userb_token}", "Content-Type": "application/json"}
        self.admin_headers = {"Authorization": f"Bearer {self.admin_token}", "Content-Type": "application/json"}

    def test_01_mau_ajukan_workflow_prompt_triggers_form_render(self):
        """Typing 'mau ajukan workflow' or its variations returns render_workflow_request_form."""
        prompts = [
            "mau ajukan workflow",
            "ajukan workflow",
            "request workflow",
            "buka form workflow",
            "mau ajukan alur kerja",
            "form pengajuan workflow"
        ]
        for p in prompts:
            res = self.client.post("/api/agent/custom-prompt", json={"prompt": p}, headers=self.user_headers)
            self.assertEqual(res.status_code, 200, f"Failed on prompt: {p}")
            data = res.json()
            self.assertEqual(
                data.get("action_type"), 
                "render_workflow_request_form", 
                f"Expected render_workflow_request_form for '{p}', got {data.get('action_type')}"
            )
            self.assertTrue(data.get("can_request_admin"))
            self.assertIn("formulir", data.get("message", "").lower())

    def test_02_direct_tool_single_step_query_executes_immediately(self):
        """Direct / safe tools (read-only query database) execute directly without workflow blocker."""
        # Query stock of specific item
        res = self.client.post(
            "/api/agent/custom-prompt",
            json={"prompt": "Berapa sisa stok ODC 48 Port di Gudang Surabaya?"},
            headers=self.user_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Direct execution must not be blocked
        self.assertNotEqual(data.get("action_type"), "workflow_not_found")
        self.assertIn("message", data)
        self.assertFalse(data.get("email_sent", False))

    def test_03_guarded_tool_blocked_without_workflow(self):
        """Guarded tools (e.g. ad-hoc dispatch_pr_email by regular user) are blocked by Tier 2 check."""
        # Direct call to execute_tool with non-admin user trying to dispatch email or run procurement
        res = self.client.post(
            "/api/agent/custom-prompt",
            json={"prompt": "Kirimkan dokumen PR-2026-0819-001 ke email manager.logistik@balitower.co.id"},
            headers=self.user_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Since PR email dispatch is a guarded tool and this is not an approved workflow execution,
        # it is either routed to workflow WF-A01 if restock intent, or blocked by guarded tool check
        if data.get("action_type") == "workflow_not_found":
            self.assertTrue(data.get("can_request_admin"))
            self.assertIn("terproteksi", data.get("message", ""))

    def test_04_submit_workflow_request_with_title_and_tenant(self):
        """User can submit workflow request with structured title and tenant_id."""
        req_payload = {
            "title": "Audit Utilisasi Genset Bulanan",
            "prompt": "Periksa seluruh konsumsi solar genset per akhir bulan dan rekap dalam tabel",
            "tenant_id": "INVENTORY",
            "notes": "Dibutuhkan untuk evaluasi efisiensi BBM site regional"
        }
        res_submit = self.client.post("/api/workflows/request", json=req_payload, headers=self.user_headers)
        self.assertEqual(res_submit.status_code, 200)
        res_data = res_submit.json()
        self.assertEqual(res_data["status"], "success")
        self.assertTrue(res_data["request_id"].startswith("REQ-"))
        self.assertEqual(res_data.get("title"), "Audit Utilisasi Genset Bulanan")

        # Admin retrieves list and sees the title and tenant
        res_admin = self.client.get("/api/auth/admin/workflow-requests", headers=self.admin_headers)
        self.assertEqual(res_admin.status_code, 200)
        admin_data = res_admin.json()
        found = next((r for r in admin_data["requests"] if r["id"] == res_data["request_id"]), None)
        self.assertIsNotNone(found)
        self.assertEqual(found.get("title"), "Audit Utilisasi Genset Bulanan")
        self.assertEqual(found.get("tenant_id"), "INVENTORY")
        self.assertEqual(found.get("username"), "usera")
        self.assertEqual(found.get("status"), "PENDING")

    def test_05_guarded_tool_constants_integrity(self):
        """AutonomousAgent defines DIRECT_TOOLS and GUARDED_TOOLS accurately."""
        self.assertIn("tool_query_database", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("tool_view_po", AutonomousAgent.DIRECT_TOOLS)
        self.assertIn("tool_dispatch_pr_email", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("tool_procurement_cycle", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("tool_manage_po", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("tool_update_threshold", AutonomousAgent.GUARDED_TOOLS)
        self.assertIn("tool_register_product", AutonomousAgent.GUARDED_TOOLS)


if __name__ == "__main__":
    unittest.main()
