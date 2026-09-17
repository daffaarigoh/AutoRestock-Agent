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
        existing_po = w_conn.execute("SELECT po_id FROM purchase_orders WHERE po_id = 'PO-2026-006';").fetchone()
        if not existing_po:
            w_conn.execute("INSERT INTO purchase_orders (po_id, po_number, supplier_id, item_id, order_quantity, unit_price, total_amount, status, order_date, expected_delivery, actual_delivery, warehouse_id, pr_number) VALUES ('PO-2026-006', 'PO/BLT/2026/09/036', 'SUP-001', 'BLT-INV-002', 10, 22000, 220000, 'ORDERED', '2026-09-16', '2026-09-26', NULL, 'WH-BDG-01', 'PR-2026-TEST');")
        else:
            w_conn.execute("UPDATE purchase_orders SET status = 'ORDERED', actual_delivery = NULL, warehouse_id = 'WH-BDG-01', item_id = 'BLT-INV-002', order_quantity = 10 WHERE po_id = 'PO-2026-006';")
        w_conn.execute("UPDATE stock_balances SET quantity_on_hand = 450, reorder_point = 400, stock_status = 'CRITICAL' WHERE warehouse_id = 'WH-BDG-01' AND item_id = 'BLT-INV-002';")
        w_conn.commit()
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

    def test_multi_warehouse_goods_receipt(self):
        from agents.router import check_clarification_needs

        # 1. Test Regex Clarification Needs:
        # BaliTower format PO/BLT/2026/09/031 must NOT trigger po_number_required
        clarif_po_blt = check_clarification_needs("PO/BLT/2026/09/031 sudah sampai di gudang, tolong catat penerimaan barangnya")
        self.assertIsNone(clarif_po_blt, "PO/BLT/... should NOT trigger clarification")

        # PO document lookup with PO/BLT/... should NOT trigger po_lookup_id
        clarif_doc = check_clarification_needs("Tolong tampilkan dokumen PDF untuk PO/BLT/2026/09/031")
        self.assertIsNone(clarif_doc, "PO doc lookup with PO/BLT/... should NOT trigger clarification")

        # Without PO number, it MUST trigger clarification
        clarif_missing = check_clarification_needs("Barang sudah sampai di gudang, tolong catat penerimaannya")
        self.assertIsNotNone(clarif_missing)
        self.assertEqual(clarif_missing["field"], "po_number_required")

        # 2. Setup Multi-Warehouse PO (PO-2026-031 / PO/BLT/2026/09/031) in DuckDB
        w_conn = get_db_connection(read_only=False)
        w_conn.execute("DELETE FROM purchase_orders WHERE po_id = 'PO-2026-031' OR po_number = 'PO/BLT/2026/09/031';")
        w_conn.execute("""
            INSERT INTO purchase_orders (po_id, po_number, supplier_id, item_id, order_quantity, unit_price, total_amount, status, order_date, expected_delivery, actual_delivery, warehouse_id, pr_number)
            VALUES 
                ('PO-2026-031', 'PO/BLT/2026/09/031', 'SUP-001', 'BLT-INV-002', 25, 22000, 550000, 'ORDERED', '2026-09-17', '2026-09-27', NULL, 'WH-BDG-01', 'PR-2026-MW01'),
                ('PO-2026-031', 'PO/BLT/2026/09/031', 'SUP-002', 'BLT-INV-005', 15, 18500000, 277500000, 'ORDERED', '2026-09-17', '2026-09-27', NULL, 'WH-DPS-01', 'PR-2026-MW01'),
                ('PO-2026-031', 'PO/BLT/2026/09/031', 'SUP-003', 'BLT-INV-009', 30, 1450000, 43500000, 'ORDERED', '2026-09-17', '2026-09-27', NULL, 'WH-SBY-01', 'PR-2026-MW01');
        """)
        
        # Initialize stock baseline for test items
        w_conn.execute("UPDATE stock_balances SET quantity_on_hand = 100, reorder_point = 50, stock_status = 'NORMAL' WHERE warehouse_id = 'WH-BDG-01' AND item_id = 'BLT-INV-002';")
        w_conn.execute("UPDATE stock_balances SET quantity_on_hand = 20, reorder_point = 25, stock_status = 'LOW_STOCK' WHERE warehouse_id = 'WH-DPS-01' AND item_id = 'BLT-INV-005';")
        w_conn.execute("UPDATE stock_balances SET quantity_on_hand = 10, reorder_point = 20, stock_status = 'CRITICAL' WHERE warehouse_id = 'WH-SBY-01' AND item_id = 'BLT-INV-009';")
        w_conn.commit()
        w_conn.close()

        inv_headers = login("usera", "user123")

        # 3. KASUS A: User does NOT specify warehouse & does NOT say 'semua'
        # Must return structured multi-warehouse clarification without mutating DB
        res_case_a = client.post(
            "/api/agent/custom-prompt",
            headers=inv_headers,
            json={"prompt": "PO/BLT/2026/09/031 sudah sampai di gudang, tolong catat penerimaan barangnya", "destinations": []}
        )
        self.assertEqual(res_case_a.status_code, 200, f"Case A request failed: {res_case_a.text}")
        data_a = res_case_a.json()
        self.assertEqual(data_a["action_type"], "goods_receipt")
        self.assertEqual(data_a["workflow_id"], "goods_receipt_multi_warehouse_clarification")
        self.assertEqual(data_a["parsed_intent"]["workflow_id"], "goods_receipt_multi_warehouse_clarification")
        self.assertTrue(data_a["is_multi_warehouse"])
        # Verify table content in response message
        self.assertIn("Sebaran Alokasi Gudang Tujuan", data_a["message"])
        self.assertIn("WH-BDG-01", data_a["message"])
        self.assertIn("WH-DPS-01", data_a["message"])
        self.assertIn("WH-SBY-01", data_a["message"])
        self.assertIn("Bandung", data_a["message"])
        self.assertIn("Denpasar", data_a["message"])
        self.assertIn("Surabaya", data_a["message"])
        self.assertIn("Penerimaan per Gudang (Parsial)", data_a["message"])
        self.assertIn("Penerimaan Seluruhnya (All Warehouses)", data_a["message"])

        # Verify DB remained ORDERED
        conn = get_db_connection(read_only=True)
        pending_rows = conn.execute("SELECT status FROM purchase_orders WHERE po_id = 'PO-2026-031' AND status = 'ORDERED';").fetchall()
        self.assertEqual(len(pending_rows), 3, "All 3 items must remain ORDERED in Case A")
        conn.close()

        # 4. KASUS B: Partial Goods Receipt for Gudang Bandung
        res_case_b = client.post(
            "/api/agent/custom-prompt",
            headers=inv_headers,
            json={"prompt": "PO/BLT/2026/09/031 untuk Gudang Bandung sudah sampai", "destinations": []}
        )
        self.assertEqual(res_case_b.status_code, 200, f"Case B request failed: {res_case_b.text}")
        data_b = res_case_b.json()
        self.assertEqual(data_b["action_type"], "goods_receipt")
        self.assertEqual(data_b["parsed_intent"]["workflow_id"], "goods_receipt")
        self.assertTrue(data_b["is_partial"])
        self.assertIn("Penerimaan Parsial Berhasil", data_b["message"])
        self.assertIn("Bandung", data_b["message"])
        self.assertIn("Sisa Material Menunggu Kedatangan di Gudang Lain", data_b["message"])
        self.assertIn("WH-DPS-01", data_b["message"])
        self.assertIn("WH-SBY-01", data_b["message"])

        # Verify DB state after partial delivery:
        # WH-BDG-01 is DELIVERED, WH-DPS-01 & WH-SBY-01 remain ORDERED
        conn = get_db_connection(read_only=True)
        bdg_po = conn.execute("SELECT status, actual_delivery FROM purchase_orders WHERE po_id = 'PO-2026-031' AND warehouse_id = 'WH-BDG-01';").fetchone()
        self.assertEqual(bdg_po[0], "DELIVERED")
        self.assertIsNotNone(bdg_po[1])

        dps_po = conn.execute("SELECT status FROM purchase_orders WHERE po_id = 'PO-2026-031' AND warehouse_id = 'WH-DPS-01';").fetchone()
        self.assertEqual(dps_po[0], "ORDERED")

        sby_po = conn.execute("SELECT status FROM purchase_orders WHERE po_id = 'PO-2026-031' AND warehouse_id = 'WH-SBY-01';").fetchone()
        self.assertEqual(sby_po[0], "ORDERED")

        # Verify stock for Bandung updated: 100 + 25 = 125
        stk_bdg = conn.execute("SELECT quantity_on_hand FROM stock_balances WHERE warehouse_id = 'WH-BDG-01' AND item_id = 'BLT-INV-002';").fetchone()
        self.assertEqual(stk_bdg[0], 125)
        conn.close()

        # 5. KASUS C: Receive All Remaining Warehouses ("semua gudang")
        res_case_c = client.post(
            "/api/agent/custom-prompt",
            headers=inv_headers,
            json={"prompt": "Catat penerimaan PO/BLT/2026/09/031 untuk semua gudang", "destinations": []}
        )
        self.assertEqual(res_case_c.status_code, 200, f"Case C request failed: {res_case_c.text}")
        data_c = res_case_c.json()
        self.assertEqual(data_c["action_type"], "goods_receipt")
        self.assertIn("Berhasil Dibukukan", data_c["message"])

        # Verify DB state: All items are now DELIVERED
        conn = get_db_connection(read_only=True)
        all_po = conn.execute("SELECT status FROM purchase_orders WHERE po_id = 'PO-2026-031';").fetchall()
        for r in all_po:
            self.assertEqual(r[0], "DELIVERED")

        # Stock Denpasar: 20 + 15 = 35
        stk_dps = conn.execute("SELECT quantity_on_hand FROM stock_balances WHERE warehouse_id = 'WH-DPS-01' AND item_id = 'BLT-INV-005';").fetchone()
        self.assertEqual(stk_dps[0], 35)

        # Stock Surabaya: 10 + 30 = 40
        stk_sby = conn.execute("SELECT quantity_on_hand FROM stock_balances WHERE warehouse_id = 'WH-SBY-01' AND item_id = 'BLT-INV-009';").fetchone()
        self.assertEqual(stk_sby[0], 40)
        conn.close()

        # 6. Test Duplicate on fully delivered PO
        res_dup = client.post(
            "/api/agent/custom-prompt",
            headers=inv_headers,
            json={"prompt": "PO/BLT/2026/09/031 sudah sampai", "destinations": []}
        )
        self.assertEqual(res_dup.status_code, 200)
        data_dup = res_dup.json()
        self.assertEqual(data_dup["parsed_intent"]["workflow_id"], "goods_receipt_already_delivered")
        self.assertIn("Sudah Pernah Diterima", data_dup["message"])


if __name__ == "__main__":
    unittest.main()
