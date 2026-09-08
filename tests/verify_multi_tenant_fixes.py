import sys
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_login_and_roles():
    print("--- 1. Testing Login & Roles ---")
    users = [
        ("admin", "admin123", "ADMIN", "ALL"),
        ("usera", "user123", "USER", "INVENTORY"),
        ("userb", "user123", "USER", "HR"),
        ("userc", "user123", "USER", "FINANCE"),
    ]
    tokens = {}
    for username, password, expected_role, expected_tenant in users:
        res = client.post("/api/auth/login", json={"username": username, "password": password})
        assert res.status_code == 200, f"Login failed for {username}: {res.text}"
        data = res.json()
        assert data["role"] == expected_role, f"Role mismatch for {username}: got {data['role']}"
        assert data["tenant_id"] == expected_tenant, f"Tenant mismatch for {username}: got {data['tenant_id']}"
        tokens[username] = data["access_token"]
        print(f"  [PASS] {username}: Role={data['role']}, Tenant={data['tenant_id']}")
    return tokens

def test_rbac_isolation(tokens):
    print("\n--- 2. Testing Strict Multi-Tenant RBAC Isolation ---")
    
    # usera: Inventory ONLY
    auth_a = {"Authorization": f"Bearer {tokens['usera']}"}
    res_inv_a = client.get("/api/balitower/inventory/items", headers=auth_a)
    assert res_inv_a.status_code == 200, f"usera cannot access inventory: {res_inv_a.status_code}"
    assert len(res_inv_a.json()) == 14, f"usera expected 14 items, got {len(res_inv_a.json())}"
    print(f"  [PASS] usera accessing /inventory/items -> 200 OK ({len(res_inv_a.json())} items)")

    res_hr_a = client.get("/api/balitower/hr/employees", headers=auth_a)
    assert res_hr_a.status_code == 403, f"usera should NOT access hr: {res_hr_a.status_code}"
    print("  [PASS] usera accessing /hr/employees -> 403 Forbidden (Strictly Blocked)")

    res_fin_a = client.get("/api/balitower/finance/invoices", headers=auth_a)
    assert res_fin_a.status_code == 403, f"usera should NOT access finance: {res_fin_a.status_code}"
    print("  [PASS] usera accessing /finance/invoices -> 403 Forbidden (Strictly Blocked)")

    # userb: HR ONLY
    auth_b = {"Authorization": f"Bearer {tokens['userb']}"}
    res_hr_b = client.get("/api/balitower/hr/employees", headers=auth_b)
    assert res_hr_b.status_code == 200, f"userb cannot access hr: {res_hr_b.status_code}"
    assert len(res_hr_b.json()) == 12, f"userb expected 12 employees, got {len(res_hr_b.json())}"
    print(f"  [PASS] userb accessing /hr/employees -> 200 OK ({len(res_hr_b.json())} employees)")

    res_inv_b = client.get("/api/balitower/inventory/items", headers=auth_b)
    assert res_inv_b.status_code == 403, f"userb should NOT access inventory: {res_inv_b.status_code}"
    print("  [PASS] userb accessing /inventory/items -> 403 Forbidden (Strictly Blocked)")

    res_fin_b = client.get("/api/balitower/finance/invoices", headers=auth_b)
    assert res_fin_b.status_code == 403, f"userb should NOT access finance: {res_fin_b.status_code}"
    print("  [PASS] userb accessing /finance/invoices -> 403 Forbidden (Strictly Blocked)")

    # userc: Finance ONLY
    auth_c = {"Authorization": f"Bearer {tokens['userc']}"}
    res_fin_c = client.get("/api/balitower/finance/invoices", headers=auth_c)
    assert res_fin_c.status_code == 200, f"userc cannot access finance: {res_fin_c.status_code}"
    assert len(res_fin_c.json()) == 8, f"userc expected 8 invoices, got {len(res_fin_c.json())}"
    print(f"  [PASS] userc accessing /finance/invoices -> 200 OK ({len(res_fin_c.json())} invoices)")

    res_inv_c = client.get("/api/balitower/inventory/items", headers=auth_c)
    assert res_inv_c.status_code == 403, f"userc should NOT access inventory: {res_inv_c.status_code}"
    print("  [PASS] userc accessing /inventory/items -> 403 Forbidden (Strictly Blocked)")

    res_hr_c = client.get("/api/balitower/hr/employees", headers=auth_c)
    assert res_hr_c.status_code == 403, f"userc should NOT access hr: {res_hr_c.status_code}"
    print("  [PASS] userc accessing /hr/employees -> 403 Forbidden (Strictly Blocked)")

    # admin: ALL access
    auth_adm = {"Authorization": f"Bearer {tokens['admin']}"}
    res_inv_adm = client.get("/api/balitower/inventory/items", headers=auth_adm)
    res_hr_adm = client.get("/api/balitower/hr/employees", headers=auth_adm)
    res_fin_adm = client.get("/api/balitower/finance/invoices", headers=auth_adm)
    assert res_inv_adm.status_code == 200
    assert res_hr_adm.status_code == 200
    assert res_fin_adm.status_code == 200
    print("  [PASS] admin has full access across all 3 domains (Inventory, HR, Finance)")

def test_admin_panel_users(tokens):
    print("\n--- 3. Testing Admin Panel /admin/users Data ---")
    auth_adm = {"Authorization": f"Bearer {tokens['admin']}"}
    res = client.get("/api/auth/admin/users", headers=auth_adm)
    assert res.status_code == 200, f"/admin/users failed: {res.text}"
    data = res.json()
    assert data["total_users"] == 4, f"Expected 4 clean users, got {data['total_users']}"
    usernames = [u["username"] for u in data["users"]]
    assert usernames == ["admin", "usera", "userb", "userc"], f"Unexpected users: {usernames}"
    print(f"  [PASS] Exactly 4 clean users returned: {usernames}")

    items = data["items"]
    usera_items = [i for i in items if i["tenant_id"] == "usera"]
    userb_items = [i for i in items if i["tenant_id"] == "userb"]
    userc_items = [i for i in items if i["tenant_id"] == "userc"]

    print(f"  [PASS] Multi-tenant items: Total={len(items)}, usera={len(usera_items)}, userb={len(userb_items)}, userc={len(userc_items)}")
    assert len(usera_items) == 14, f"Expected 14 usera items, got {len(usera_items)}"
    assert len(userb_items) == 12, f"Expected 12 userb items, got {len(userb_items)}"
    assert len(userc_items) == 8, f"Expected 8 userc items, got {len(userc_items)}"

if __name__ == "__main__":
    t = test_login_and_roles()
    test_rbac_isolation(t)
    test_admin_panel_users(t)
    print("\n>>> ALL VERIFICATION TESTS PASSED PERFECTLY! <<<")
