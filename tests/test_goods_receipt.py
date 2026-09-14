import os
import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from database.db import get_db_connection

client = TestClient(app)

def login(username: str, password: str = "user123"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed for {username}: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestGoodsReceipt(unittest.TestCase):

    def test_goods_receipt_workflow(self):
        # Setup / Reset initial baseline for idempotent testing
        w_conn = get_db_connection(read_only=False)
        w_conn.execute("UPDATE purchase_orders SET status = 'ORDERED', actual_delivery = NULL WHERE po_id = 'PO-2026-006';")
        w_conn.execute("UPDATE stock_balances SET quantity_on_hand = 450, stock_status = 'CRITICAL' WHERE warehouse_id = 'WH-BDG-01' AND item_id = 'BLT-INV-002';")
        w_conn.close()

        # 1. Login as Inventory User (usera)
        inv_headers = login("usera", "user123")

        # 2. Verify Initial State of PO-2026-006 & Bandung Stock
        conn = get_db_connection(read_only=True)
        po_before = conn.execute("""
            SELECT status, order_quantity, warehouse_id, item_id 
            FROM purchase_orders WHERE po_id = 'PO-2026-006';
        """).fetchone()
        self.assertIsNotNone(po_before, "PO-2026-006 should exist")
        self.assertEqual(po_before[0], "ORDERED")
        qty_ordered = po_before[1]
        
        stk_before = conn.execute("""
            SELECT quantity_on_hand, stock_status, reorder_point 
            FROM stock_balances WHERE warehouse_id = 'WH-BDG-01' AND item_id = 'BLT-INV-002';
        """).fetchone()
        self.assertIsNotNone(stk_before, "Stock record for WH-BDG-01 / BLT-INV-002 should exist")
        old_qty, old_status, rop = stk_before
        conn.close()

        # 3. Submit Goods Receipt Prompt via AI Copilot
        prompt_text = "Barang untuk PO-2026-006 sudah sampai di Gudang Bandung, tolong catat penerimaannya"
        res = client.post(
            "/api/agent/custom-prompt",
            headers=inv_headers,
            json={"prompt": prompt_text, "destinations": []}
        )
        self.assertEqual(res.status_code, 200, f"Prompt failed: {res.text}")
        data = res.json()
        self.assertEqual(data["action_type"], "goods_receipt")
        self.assertEqual(data["parsed_intent"]["workflow_id"], "goods_receipt")
        self.assertEqual(data["parsed_intent"]["po_id"], "PO-2026-006")
        self.assertIn("DELIVERED", data["message"])

        # 4. Verify DuckDB State After Receipt
        conn = get_db_connection(read_only=True)
        po_after = conn.execute("""
            SELECT status, actual_delivery FROM purchase_orders WHERE po_id = 'PO-2026-006';
        """).fetchone()
        self.assertEqual(po_after[0], "DELIVERED")
        self.assertIsNotNone(po_after[1], "actual_delivery should be recorded")

        stk_after = conn.execute("""
            SELECT quantity_on_hand, stock_status FROM stock_balances 
            WHERE warehouse_id = 'WH-BDG-01' AND item_id = 'BLT-INV-002';
        """).fetchone()
        expected_qty = old_qty + qty_ordered
        self.assertEqual(stk_after[0], expected_qty)
        self.assertEqual(stk_after[1], "NORMAL")
        conn.close()

        # 5. Test Duplicate Prevention
        res_dup = client.post(
            "/api/agent/custom-prompt",
            headers=inv_headers,
            json={"prompt": "PO-2026-006 sudah sampai", "destinations": []}
        )
        self.assertEqual(res_dup.status_code, 200)
        data_dup = res_dup.json()
        self.assertEqual(data_dup["parsed_intent"]["workflow_id"], "goods_receipt_already_delivered")
        self.assertIn("Sudah Pernah Diterima", data_dup["message"])

        # 6. Test Multi-Tenant Boundary: HR User Blocked
        hr_headers = login("userb", "user123")
        res_hr = client.post(
            "/api/agent/custom-prompt",
            headers=hr_headers,
            json={"prompt": "Barang untuk PO-2026-004 sudah sampai di Bandung, catat penerimaannya", "destinations": []}
        )
        self.assertEqual(res_hr.status_code, 200)
        data_hr = res_hr.json()
        self.assertEqual(data_hr["action_type"], "out_of_scope")
        self.assertIn("Akses Ditolak", data_hr["message"])


if __name__ == "__main__":
    unittest.main()
