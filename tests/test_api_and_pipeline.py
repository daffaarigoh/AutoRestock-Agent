import sys
from pathlib import Path

# Base path resolution
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app

def test_full_pipeline():
    client = TestClient(app)
    client.post("/api/approval/reset")
    
    print("\n" + "=" * 80)

    print("🧪 RUNNING END-TO-END VERIFICATION TEST (APPROVE & REJECT)")
    print("=" * 80)
    
    # 1. Test Root
    res_root = client.get("/")
    assert res_root.status_code == 200
    print(f"[TEST 1] Root Endpoint: OK -> {res_root.json()['service']}")
    
    # 2. Test GET /api/inventory/items
    res_items = client.get("/api/inventory/items")
    assert res_items.status_code == 200
    items = res_items.json()
    assert len(items) == 25
    print(f"[TEST 2] GET /api/inventory/items: OK -> Retrieved {len(items)} items from DuckDB")
    
    # 3. Test POST /api/agent/run-cycle (Cycle 1: For Approval)
    res_cycle1 = client.post("/api/agent/run-cycle")
    assert res_cycle1.status_code == 200
    pr_data1 = res_cycle1.json()
    pr1_number = pr_data1["pr_number"]
    assert len(pr_data1["items"]) == 5
    print(f"[TEST 3] POST /api/agent/run-cycle (Cycle 1): OK -> PR #{pr1_number} (PENDING)")
    
    # 4. Test POST /api/agent/approve (APPROVE Action)
    res_approve = client.post("/api/agent/approve", json={
        "pr_number": pr1_number,
        "action": "APPROVE",
        "approver_name": "Chief Operations Officer",
        "notes": "Approved for vendor procurement"
    })
    assert res_approve.status_code == 200
    assert res_approve.json()["status"] == "APPROVED"
    print(f"[TEST 4] POST /api/agent/approve (APPROVE): OK -> PR #{pr1_number} APPROVED")
    
    # 5. Test Download of Approved PDF
    res_download_appr = client.get(f"/api/documents/pr/{pr1_number}/download")
    assert res_download_appr.status_code == 200
    assert res_download_appr.headers["content-type"] == "application/pdf"
    print(f"[TEST 5] GET /api/documents/pr/{pr1_number}/download: OK -> Approved PDF downloaded ({len(res_download_appr.content)} bytes)")
    
    # 6. Test POST /api/agent/run-cycle (Cycle 2: For Rejection)
    res_cycle2 = client.post("/api/agent/run-cycle")
    assert res_cycle2.status_code == 200
    pr2_number = res_cycle2.json()["pr_number"]
    print(f"[TEST 6] POST /api/agent/run-cycle (Cycle 2): OK -> PR #{pr2_number} (PENDING)")
    
    # 7. Test POST /api/agent/approve (REJECT Action)
    res_reject = client.post("/api/agent/approve", json={
        "pr_number": pr2_number,
        "action": "REJECT",
        "approver_name": "Finance Director",
        "notes": "Budget allocation delayed"
    })
    assert res_reject.status_code == 200
    assert res_reject.json()["status"] == "REJECTED"
    print(f"[TEST 7] POST /api/agent/approve (REJECT): OK -> PR #{pr2_number} REJECTED")
    
    # 8. Test Download of Rejected PDF
    res_download_rej = client.get(f"/api/documents/pr/{pr2_number}/download")
    assert res_download_rej.status_code == 200
    assert res_download_rej.headers["content-type"] == "application/pdf"
    print(f"[TEST 8] GET /api/documents/pr/{pr2_number}/download: OK -> Rejected PDF downloaded ({len(res_download_rej.content)} bytes)")
    
    print("=" * 80)
    print("🎉 ALL 8 INTEGRATION TESTS (INCLUDING APPROVE & REJECT) PASSED!")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    test_full_pipeline()
