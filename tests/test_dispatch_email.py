import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import get_current_user, TokenData
from api.routers.approval_routes import PR_STORE


class TestDispatchEmailFlow(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: TokenData(username="admin", role="ADMIN", tenant_id="ALL")

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def setUp(self):
        # Reset database and seed PR-2026-0819-001 before each test
        res_reset = self.client.post("/api/approval/reset?seed=true")
        self.assertEqual(res_reset.status_code, 200)

    def test_dispatch_email_default_manager(self):
        """1) Kirim email ke default manager logistik (manager.logistik@balitower.co.id)."""
        payload = {
            "pr_number": "PR-2026-0819-001"
        }
        res = self.client.post("/api/approval/dispatch-email", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["pr_number"], "PR-2026-0819-001")
        self.assertEqual(data["recipient_email"], "manager.logistik@balitower.co.id")
        self.assertIn("manager.logistik@balitower.co.id", data["message"])
        
        # Verify store flag
        pr = PR_STORE.get("PR-2026-0819-001")
        self.assertIsNotNone(pr)
        self.assertTrue(getattr(pr, "email_sent", False))

    def test_dispatch_email_custom_recipient(self):
        """2) Kirim email ke email kustom."""
        custom_email = "approver.custom@balitower.co.id"
        payload = {
            "pr_number": "PR-2026-0819-001",
            "recipient_email": custom_email
        }
        res = self.client.post("/api/approval/dispatch-email", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["pr_number"], "PR-2026-0819-001")
        self.assertEqual(data["recipient_email"], custom_email)
        self.assertIn(custom_email, data["message"])

        # Verify store flag
        pr = PR_STORE.get("PR-2026-0819-001")
        self.assertIsNotNone(pr)
        self.assertTrue(getattr(pr, "email_sent", False))

    def test_dispatch_email_pr_not_found(self):
        """3) Validasi error 404 jika PR tidak ditemukan."""
        payload = {
            "pr_number": "PR-NONEXISTENT-99999",
            "recipient_email": "manager.logistik@balitower.co.id"
        }
        res = self.client.post("/api/approval/dispatch-email", json=payload)
        self.assertEqual(res.status_code, 404)
        data = res.json()
        self.assertIn("tidak ditemukan", data.get("detail", "").lower())


if __name__ == "__main__":
    unittest.main()
