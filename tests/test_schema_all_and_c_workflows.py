import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import TokenData, get_current_user


class TestSchemaAllAndCWorkflows(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def set_user(self, username: str, role: str, tenant_id: str):
        def _override():
            return TokenData(username=username, role=role, tenant_id=tenant_id)
        app.dependency_overrides[get_current_user] = _override

    def tearDown(self):
        app.dependency_overrides.clear()

    # -------------------------------------------------------------
    # 1. TEST SCHEMA ALL: ACCESSIBLE BY ALL ROLES & TENANTS
    # -------------------------------------------------------------
    def test_schema_all_for_usera_inventory(self):
        """User A (Inventory) should be able to run all Schema ALL workflows."""
        self.set_user(username="usera", role="USER", tenant_id="INVENTORY")

        # A. Cek Profil
        res1 = self.client.post("/api/agent/custom-prompt", json={"prompt": "cek profil akun saya"})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertIn("Profil Pengguna", data1["message"])
        self.assertIn("usera", data1["message"])
        self.assertIn("INVENTORY", data1["message"])

        # B. Info Sistem
        res2 = self.client.post("/api/agent/custom-prompt", json={"prompt": "info sistem dan status server"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertIn("Status Operasional Sistem", data2["message"])
        self.assertIn("DuckDB", data2["message"])

        # C. Panduan Operasional
        res3 = self.client.post("/api/agent/custom-prompt", json={"prompt": "tampilkan panduan operasional perusahaan"})
        self.assertEqual(res3.status_code, 200)
        data3 = res3.json()
        self.assertIn("Panduan Operasional", data3["message"])
        self.assertIn("Kontak Darurat", data3["message"])

    def test_schema_all_for_userb_hr(self):
        """User B (HR) should be able to run all Schema ALL workflows."""
        self.set_user(username="userb", role="USER", tenant_id="HR")

        res = self.client.post("/api/agent/custom-prompt", json={"prompt": "siapa saya dan apa hak akses saya"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("userb", data["message"])
        self.assertIn("HR", data["message"])

    def test_schema_all_for_userc_finance(self):
        """User C (Finance) should be able to run all Schema ALL workflows."""
        self.set_user(username="userc", role="USER", tenant_id="FINANCE")

        res = self.client.post("/api/agent/custom-prompt", json={"prompt": "status kesehatan sistem saat ini"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("ONLINE & OPERATIONAL", data["message"])

    def test_schema_all_for_admin(self):
        """Admin (Super Admin) should be able to run all Schema ALL workflows."""
        self.set_user(username="admin", role="ADMIN", tenant_id="ALL")

        res = self.client.post("/api/agent/custom-prompt", json={"prompt": "cek profil akun saya"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("admin", data["message"])
        self.assertIn("Super Administrator", data["message"])

    # -------------------------------------------------------------
    # 2. TEST SCHEMA C (FINANCE): ALLOWED FOR USER C AND ADMIN
    # -------------------------------------------------------------
    def test_schema_c_allowed_for_userc(self):
        """User C (Finance) can successfully access Schema C Finance workflows."""
        self.set_user(username="userc", role="USER", tenant_id="FINANCE")

        # Revenue Report
        res1 = self.client.post("/api/agent/custom-prompt", json={"prompt": "tampilkan laporan pendapatan sewa menara"})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertEqual(data1["action_type"], "finance_query")
        self.assertIn("Pendapatan Sewa Menara", data1["message"])

        # OPEX Report
        res2 = self.client.post("/api/agent/custom-prompt", json={"prompt": "audit pengeluaran beban listrik dan sewa lahan"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["action_type"], "finance_query")
        self.assertIn("Beban Operasional Site (OPEX)", data2["message"])

        # Cashflow Summary
        res3 = self.client.post("/api/agent/custom-prompt", json={"prompt": "ringkasan arus kas perusahaan"})
        self.assertEqual(res3.status_code, 200)
        data3 = res3.json()
        self.assertEqual(data3["action_type"], "finance_query")
        self.assertIn("telah dinonaktifkan", data3["message"])

    def test_schema_c_allowed_for_admin(self):
        """Admin has full cross-tenant access to Schema C."""
        self.set_user(username="admin", role="ADMIN", tenant_id="ALL")

        res = self.client.post("/api/agent/custom-prompt", json={"prompt": "laporan pendapatan sewa menara"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["action_type"], "finance_query")
        self.assertIn("Pendapatan Sewa Menara", data["message"])

    # -------------------------------------------------------------
    # 3. TEST SCHEMA C (FINANCE): STRICTLY FORBIDDEN FOR USER A & B
    # -------------------------------------------------------------
    def test_schema_c_rejected_for_usera_inventory(self):
        """User A (Inventory) MUST BE REJECTED when accessing Schema C workflows."""
        self.set_user(username="usera", role="USER", tenant_id="INVENTORY")

        res1 = self.client.post("/api/agent/custom-prompt", json={"prompt": "tampilkan laporan pendapatan sewa menara"})
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertIn("Akses Ditolak", data1["message"])
        self.assertIn("Schema C (Divisi Keuangan)", data1["message"])
        self.assertIn("usera", data1["message"])

        res2 = self.client.post("/api/agent/custom-prompt", json={"prompt": "cek arus kas perusahaan"})
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertIn("Akses Ditolak", data2["message"])
        self.assertIn("Schema C (Divisi Keuangan)", data2["message"])

    def test_schema_c_rejected_for_userb_hr(self):
        """User B (HR) MUST BE REJECTED when accessing Schema C workflows."""
        self.set_user(username="userb", role="USER", tenant_id="HR")

        res = self.client.post("/api/agent/custom-prompt", json={"prompt": "audit beban pengeluaran listrik pln"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("Akses Ditolak", data["message"])
        self.assertIn("Schema C (Divisi Keuangan)", data["message"])
        self.assertIn("userb", data["message"])


if __name__ == "__main__":
    unittest.main()
