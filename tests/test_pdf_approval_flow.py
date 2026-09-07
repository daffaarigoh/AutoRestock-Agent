import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

import pypdf
from fastapi.testclient import TestClient
from api.main import app
from core.security import get_current_user, TokenData

import io
import unittest

class TestPDFApprovalFlow(unittest.TestCase):

    def test_approval_and_pdf_rendering(self):
        client = TestClient(app)
        
        # Override auth to ADMIN
        app.dependency_overrides[get_current_user] = lambda: TokenData(username="admin", role="ADMIN", tenant_id="ALL")
        
        # 1. Reset database & store
        res_reset = client.post("/api/approval/reset")
        self.assertEqual(res_reset.status_code, 200)
        
        # 2. Get PR list
        res_list = client.get("/api/approval/list")
        self.assertEqual(res_list.status_code, 200)
        prs = res_list.json()
        self.assertGreater(len(prs), 0)
        pr_target = prs[0]["pr_number"]
        self.assertEqual(prs[0]["status"], "PENDING")
        
        # 3. Check Pending PDF content
        res_pdf_pending = client.get(f"/api/documents/pr/{pr_target}/download")
        self.assertEqual(res_pdf_pending.status_code, 200)
        reader_pending = pypdf.PdfReader(io.BytesIO(res_pdf_pending.content))
        text_pending = reader_pending.pages[0].extract_text()
        self.assertIn("Status: PENDING", text_pending)
        self.assertIn("PASSED (PENDING)", text_pending)
        
        # 4. Perform Approval Action
        res_action = client.post("/api/approval/action", json={
            "pr_number": pr_target,
            "action": "APPROVE",
            "manager_name": "Warehouse Manager"
        })
        self.assertEqual(res_action.status_code, 200)
        self.assertEqual(res_action.json()["new_status"], "APPROVED")
        
        # 5. Check Approved PDF content
        res_pdf_approved = client.get(f"/api/documents/pr/{pr_target}/download")
        self.assertEqual(res_pdf_approved.status_code, 200)
        reader_approved = pypdf.PdfReader(io.BytesIO(res_pdf_approved.content))
        text_approved = reader_approved.pages[0].extract_text()
        self.assertIn("Status: APPROVED", text_approved)
        self.assertNotIn("PASSED (PENDING)", text_approved)
        
        # 6. Verify DuckDB order status
        from database.db import get_db_connection
        conn = get_db_connection(read_only=True)
        db_order = conn.execute("SELECT status FROM orders WHERE pr_number = ? LIMIT 1;", [pr_target]).fetchone()
        conn.close()
        self.assertEqual(db_order[0], "APPROVED")


if __name__ == "__main__":
    unittest.main()
