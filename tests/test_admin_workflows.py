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
        self.assertEqual(wf_map["WF-001"]["tenant_id"], "INVENTORY")
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


if __name__ == "__main__":
    unittest.main()
