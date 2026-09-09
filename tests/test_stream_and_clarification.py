import unittest
import uuid
import json
import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import create_access_token
from database.db import get_db_connection
from agents.router import extract_recipient_email, check_clarification_needs

class TestStreamAndClarification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.admin_token = create_access_token({"sub": "admin", "role": "ADMIN", "tenant_id": "ALL"})
        cls.inv_token = create_access_token({"sub": "usera", "role": "USER", "tenant_id": "INVENTORY"})
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}", "Content-Type": "application/json"}
        cls.inv_headers = {"Authorization": f"Bearer {cls.inv_token}", "Content-Type": "application/json"}

    def test_01_email_regex_extraction(self):
        """Verify automatic detection of any recipient email address."""
        self.assertEqual(extract_recipient_email("Kirim ke boss@balitower.co.id ya"), "boss@balitower.co.id")
        self.assertEqual(extract_recipient_email("tolong approve di manager.it@perusahaan.com."), "manager.it@perusahaan.com")
        self.assertIsNone(extract_recipient_email("tolong restock barang tanpa email"))

    def test_02_clarification_guard(self):
        """Verify proactive clarification when missing critical parameters."""
        # Missing email address
        clarif_email = check_clarification_needs("Tolong kirimkan notifikasi dokumen ke email")
        self.assertIsNotNone(clarif_email)
        self.assertEqual(clarif_email["field"], "recipient_email")

        # Missing threshold values
        clarif_thresh = check_clarification_needs("Tolong ubah threshold barang ini")
        self.assertIsNotNone(clarif_thresh)
        self.assertEqual(clarif_thresh["field"], "threshold_parameters")

        # Missing product specifications for registration
        clarif_prod = check_clarification_needs("Tolong tambah barang baru dong")
        self.assertIsNotNone(clarif_prod)
        self.assertEqual(clarif_prod["field"], "product_details")

        # Complete request should NOT trigger clarification
        clarif_ok = check_clarification_needs("Kirimkan dokumen PR ke manager@balitower.co.id")
        self.assertIsNone(clarif_ok)

    def test_03_stream_prompt_endpoint(self):
        """Verify /api/agent/stream-prompt outputs SSE stages, tokens, and complete event."""
        with self.client.stream("POST", "/api/agent/stream-prompt", json={"prompt": "Halo agent"}, headers=self.admin_headers) as response:
            self.assertEqual(response.status_code, 200)
            events = []
            for line in response.iter_lines():
                if line and line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))
            
            event_types = [e.get("type") for e in events]
            self.assertIn("status", event_types)
            self.assertIn("token", event_types)
            self.assertIn("complete", event_types)

    def test_04_stream_clarification_flow(self):
        """Verify stream-prompt emits clarification type when parameters are missing."""
        with self.client.stream("POST", "/api/agent/stream-prompt", json={"prompt": "tolong kirimkan email persetujuan pr"}, headers=self.inv_headers) as response:
            self.assertEqual(response.status_code, 200)
            events = []
            for line in response.iter_lines():
                if line and line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))
            
            event_types = [e.get("type") for e in events]
            self.assertIn("clarification", event_types)

    def test_05_dynamic_email_approval_and_stock_increment(self):
        """Verify recipient email approval link increments DuckDB physical stock."""
        conn = get_db_connection()
        row = conn.execute("SELECT item_id, current_stock FROM items LIMIT 1").fetchone()
        item_id, initial_stock = row[0], row[1]
        pr_num = f"PR-AUTOTEST-{uuid.uuid4().hex[:6].upper()}"
        ord_id = f"ORD-AUTOTEST-{uuid.uuid4().hex[:6].upper()}"
        qty_to_add = 10

        conn.execute("""
            INSERT INTO orders (order_id, pr_number, item_id, vendor_id, quantity, unit_price, total_price, status, tenant_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', 'INVENTORY');
        """, [ord_id, pr_num, item_id, "VND-001", qty_to_add, 50000, 500000])
        conn.commit()
        conn.close()

        # Call quick-action approval (simulating user clicking SETUJUI in their email)
        res = self.client.get(f"/api/approval/quick-action?pr_number={pr_num}&action=APPROVE")
        self.assertEqual(res.status_code, 200)
        self.assertIn("DISETUJUI (APPROVED)", res.text)

        # Assert DuckDB updated
        conn = get_db_connection(read_only=True)
        order_status = conn.execute("SELECT status FROM orders WHERE pr_number = ?;", [pr_num]).fetchone()[0]
        updated_stock = conn.execute("SELECT current_stock FROM items WHERE item_id = ?;", [item_id]).fetchone()[0]
        conn.close()

        self.assertEqual(order_status, "APPROVED")
        self.assertEqual(updated_stock, initial_stock + qty_to_add)

if __name__ == "__main__":
    unittest.main()
