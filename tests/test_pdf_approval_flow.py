import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

import pypdf
from fastapi.testclient import TestClient
from api.main import app
from core.security import get_current_user, TokenData

def io_bytes(b):
    import io
    return io.BytesIO(b)

def test_approval_and_pdf_rendering():
    client = TestClient(app)
    
    # Override auth to ADMIN
    app.dependency_overrides[get_current_user] = lambda: TokenData(username="admin", role="ADMIN", tenant_id="ALL")
    
    # 1. Reset database & store
    res_reset = client.post("/api/approval/reset")
    assert res_reset.status_code == 200
    
    # 2. Get PR list
    res_list = client.get("/api/approval/list")
    assert res_list.status_code == 200
    prs = res_list.json()
    assert len(prs) > 0
    pr_target = prs[0]["pr_number"]
    assert prs[0]["status"] == "PENDING"
    
    # 3. Check Pending PDF content
    res_pdf_pending = client.get(f"/api/documents/pr/{pr_target}/download")
    assert res_pdf_pending.status_code == 200
    reader_pending = pypdf.PdfReader(io_bytes(res_pdf_pending.content))
    text_pending = reader_pending.pages[0].extract_text()
    assert "Status: PENDING" in text_pending
    assert "PASSED (PENDING)" in text_pending
    print("[PASS] Pending PDF correctly contains 'Status: PENDING' & 'PASSED (PENDING)'")
    
    # 4. Perform Approval Action
    res_action = client.post("/api/approval/action", json={
        "pr_number": pr_target,
        "action": "APPROVE",
        "manager_name": "Warehouse Manager"
    })
    assert res_action.status_code == 200
    assert res_action.json()["new_status"] == "APPROVED"
    print(f"[PASS] PR {pr_target} successfully approved via /api/approval/action")
    
    # 5. Check Approved PDF content
    res_pdf_approved = client.get(f"/api/documents/pr/{pr_target}/download")
    assert res_pdf_approved.status_code == 200
    reader_approved = pypdf.PdfReader(io_bytes(res_pdf_approved.content))
    text_approved = reader_approved.pages[0].extract_text()
    assert "Status: APPROVED" in text_approved
    assert "PASSED (PENDING)" not in text_approved
    assert "APPROVED" in text_approved
    print("[PASS] Approved PDF correctly contains 'Status: APPROVED' and does NOT contain 'PASSED (PENDING)'")
    
    # 6. Verify DuckDB order status
    from database.db import get_db_connection
    conn = get_db_connection(read_only=True)
    db_order = conn.execute("SELECT status FROM orders WHERE pr_number = ? LIMIT 1;", [pr_target]).fetchone()
    conn.close()
    assert db_order[0] == "APPROVED"
    print("[PASS] DuckDB order status updated to 'APPROVED'")

if __name__ == "__main__":
    test_approval_and_pdf_rendering()
    print("\nALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")
