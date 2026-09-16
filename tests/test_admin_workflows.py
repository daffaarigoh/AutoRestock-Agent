import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import TokenData, get_current_admin


class TestAdminWorkflows(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        def _override_admin():
            return TokenData(username="admin", role="ADMIN", tenant_id="ALL")
        app.dependency_overrides[get_current_admin] = _override_admin

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_get_all_workflows_schemas(self):
        """Ensure GET /api/auth/admin/workflows returns correctly scoped tenant IDs."""
        res = self.client.get("/api/auth/admin/workflows")
        self.assertEqual(res.status_code, 200)
        wfs = res.json()
        self.assertGreaterEqual(len(wfs), 9)

        wf_map = {w["id"]: w for w in wfs}

        # Check Schema A
        wf_a = wf_map.get("WF-A01") or wf_map.get("WF-001")
        self.assertIsNotNone(wf_a)
        self.assertEqual(wf_a["tenant_id"], "INVENTORY")
        # Check Schema B
        self.assertEqual(wf_map["WF-002"]["tenant_id"], "HR")
        self.assertEqual(wf_map["WF-003"]["tenant_id"], "HR")
        # Check Schema C (Finance)
        self.assertEqual(wf_map["WF-004"]["tenant_id"], "FINANCE")
        self.assertEqual(wf_map["WF-005"]["tenant_id"], "FINANCE")
        self.assertEqual(wf_map["WF-006"]["tenant_id"], "FINANCE")
        # Check Schema ALL
        self.assertEqual(wf_map["WF-ALL-01"]["tenant_id"], "ALL")
        self.assertEqual(wf_map["WF-ALL-02"]["tenant_id"], "ALL")
        self.assertEqual(wf_map["WF-ALL-03"]["tenant_id"], "ALL")

    def test_admin_created_workflow_executed_via_user_prompt(self):
        """Verify that when an Admin creates a workflow, user prompt selects and executes it."""
        from core.security import create_access_token
        # 1. Admin creates a custom workflow
        create_payload = {
            "name": "Audit Seluruh Saldo Gudang Regional",
            "description": "Menarik seluruh saldo stok material gudang regional untuk inspeksi rutin.",
            "business_instruction": "Tarik semua data barang yang ada di sistem gudang logistik untuk audit rutin.",
            "tenant_id": "INVENTORY",
            "example_prompts": ["Audit seluruh inventaris gudang regional hari ini"]
        }
        res_create = self.client.post("/api/auth/admin/workflows", json=create_payload)
        self.assertEqual(res_create.status_code, 200)
        created_data = res_create.json()
        wf_id = created_data["workflow_id"]
        self.assertTrue(wf_id.startswith("WF-"))

        # 2. User submits prompt matching the admin workflow
        user_token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        headers = {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}
        res_prompt = self.client.post("/api/agent/custom-prompt", json={
            "prompt": "Tolong audit seluruh inventaris gudang regional hari ini"
        }, headers=headers)
        self.assertEqual(res_prompt.status_code, 200)
        data = res_prompt.json()
        # Verify that the parsed intent matches the admin-created workflow!
        self.assertEqual(data["parsed_intent"]["workflow_id"], wf_id)
        self.assertEqual(data["action_type"], "workflow_execution")

        # 3. Clean up by deleting the workflow
        del_res = self.client.delete(f"/api/auth/admin/workflows/{wf_id}")
        self.assertEqual(del_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
