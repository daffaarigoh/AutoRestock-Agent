import sys
import unittest
from pathlib import Path

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app


class TestAuthAndRBAC(unittest.TestCase):

    def setUp(self):
        # Use fresh TestClient without dependency overrides for auth testing
        self.client = TestClient(app)

    def test_login_success(self):
        """Verifies successful login returns JWT access token."""
        res = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data.get("token_type"), "bearer")

    def test_login_invalid_credentials(self):
        """Verifies invalid login attempt returns 401 Unauthorized."""
        res = self.client.post("/api/auth/login", json={"username": "wronguser", "password": "wrongpassword"})
        self.assertEqual(res.status_code, 401)

    def test_multi_tenant_scoping_usera(self):
        """Verifies usera only accesses Tenant A items."""
        res = self.client.post("/api/auth/login", json={"username": "usera", "password": "user123"})
        self.assertEqual(res.status_code, 200)
        token = res.json()["access_token"]

        items_res = self.client.get(
            "/api/inventory/items",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(items_res.status_code, 200)
        items = items_res.json()
        self.assertGreater(len(items), 0)
        for it in items:
            self.assertEqual(it["tenant_id"], "TENANT_A")


if __name__ == "__main__":
    unittest.main()

