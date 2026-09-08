"""Verification test for tenant data isolation and endpoint access."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_tenant_isolation():
    print("=== TESTING TENANT DATA ISOLATION & ACCESS CONTROL ===")
    
    # 1. Admin login (Tenant: ALL)
    res = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    admin_data = res.json()
    admin_token = admin_data["access_token"]
    assert admin_data["tenant_id"] == "ALL"
    assert admin_data["role"] == "ADMIN"
    print("[PASS] Admin login succeeded (Tenant: ALL)")

    # 2. Inventory User login (Tenant: INVENTORY)
    res = client.post("/api/auth/login", json={"username": "user_inventory", "password": "user123"})
    assert res.status_code == 200, f"Inventory user login failed: {res.text}"
    inv_data = res.json()
    inv_token = inv_data["access_token"]
    assert inv_data["tenant_id"] == "INVENTORY"
    print("[PASS] Inventory user login succeeded (Tenant: INVENTORY)")

    # 3. HR User login (Tenant: HR)
    res = client.post("/api/auth/login", json={"username": "user_hr", "password": "user123"})
    assert res.status_code == 200, f"HR user login failed: {res.text}"
    hr_data = res.json()
    hr_token = hr_data["access_token"]
    assert hr_data["tenant_id"] == "HR"
    print("[PASS] HR user login succeeded (Tenant: HR)")

    # 4. Finance User login (Tenant: FINANCE)
    res = client.post("/api/auth/login", json={"username": "user_finance", "password": "user123"})
    assert res.status_code == 200, f"Finance user login failed: {res.text}"
    fin_data = res.json()
    fin_token = fin_data["access_token"]
    assert fin_data["tenant_id"] == "FINANCE"
    print("[PASS] Finance user login succeeded (Tenant: FINANCE)")

    # --- VERIFY ENDPOINTS FOR ALL 18 TABLES UNDER ADMIN ---
    endpoints_to_test = [
        # Inventory tables
        ("/api/balitower/inventory/items", "inventory_items"),
        ("/api/balitower/inventory/stock-balances", "stock_balances"),
        ("/api/balitower/inventory/warehouses", "warehouses"),
        ("/api/balitower/inventory/suppliers", "suppliers"),
        ("/api/balitower/inventory/purchase-orders", "purchase_orders"),
        # HR tables
        ("/api/balitower/hr/summary", "hr_summary"),
        ("/api/balitower/hr/employees", "employees"),
        ("/api/balitower/hr/attendances", "attendances"),
        ("/api/balitower/hr/leave-requests", "leave_requests"),
        ("/api/balitower/hr/candidates", "candidates"),
        ("/api/balitower/hr/job-postings", "job_postings"),
        ("/api/balitower/hr/sites", "telecom_sites"),
        # Finance tables
        ("/api/balitower/finance/summary", "finance_summary"),
        ("/api/balitower/finance/invoices", "revenue_invoices"),
        ("/api/balitower/finance/clients", "telecom_clients"),
        ("/api/balitower/finance/mla-contracts", "mla_contracts"),
        ("/api/balitower/finance/land-leases", "site_land_leases"),
        ("/api/balitower/finance/site-utilities", "site_utilities_cost"),
        ("/api/balitower/finance/transactions", "financial_transactions"),
        ("/api/balitower/finance/chart-of-accounts", "chart_of_accounts"),
    ]

    print("\n--- Verifying Admin Access to all 18 Tables ---")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    for ep, table_name in endpoints_to_test:
        r = client.get(ep, headers=admin_headers)
        assert r.status_code == 200, f"Admin failed to access {ep} ({table_name}): {r.status_code} {r.text}"
        data = r.json()
        count = len(data) if isinstance(data, list) else len(data.keys())
        print(f"  [OK] Admin can view {table_name} ({count} records/fields)")

    print("\n--- Verifying Strict Multi-Tenant Isolation for INVENTORY User ---")
    inv_headers = {"Authorization": f"Bearer {inv_token}"}
    # Inventory user can access inventory items
    r_inv = client.get("/api/balitower/inventory/items", headers=inv_headers)
    assert r_inv.status_code == 200, "Inventory user should access inventory items"
    print("  [OK] Inventory user accessed inventory items (200 OK)")

    # Inventory user CANNOT access HR
    r_hr = client.get("/api/balitower/hr/employees", headers=inv_headers)
    assert r_hr.status_code == 403, f"Expected 403 for HR endpoint, got {r_hr.status_code}"
    print("  [PASS] Inventory user blocked from HR data (403 Forbidden)")

    # Inventory user CANNOT access Finance
    r_fin = client.get("/api/balitower/finance/invoices", headers=inv_headers)
    assert r_fin.status_code == 403, f"Expected 403 for Finance endpoint, got {r_fin.status_code}"
    print("  [PASS] Inventory user blocked from Finance data (403 Forbidden)")

    print("\n--- Verifying Strict Multi-Tenant Isolation for HR User ---")
    hr_headers = {"Authorization": f"Bearer {hr_token}"}
    # HR user can access HR
    r_hr_ok = client.get("/api/balitower/hr/employees", headers=hr_headers)
    assert r_hr_ok.status_code == 200, "HR user should access employees"
    print("  [OK] HR user accessed employee data (200 OK)")

    # HR user CANNOT access Inventory
    r_inv_block = client.get("/api/balitower/inventory/items", headers=hr_headers)
    assert r_inv_block.status_code == 403, f"Expected 403 for Inventory endpoint, got {r_inv_block.status_code}"
    print("  [PASS] HR user blocked from Inventory data (403 Forbidden)")

    # HR user CANNOT access Finance
    r_fin_block = client.get("/api/balitower/finance/invoices", headers=hr_headers)
    assert r_fin_block.status_code == 403, f"Expected 403 for Finance endpoint, got {r_fin_block.status_code}"
    print("  [PASS] HR user blocked from Finance data (403 Forbidden)")

    print("\n--- Verifying Strict Multi-Tenant Isolation for FINANCE User ---")
    fin_headers = {"Authorization": f"Bearer {fin_token}"}
    # Finance user can access Finance
    r_fin_ok = client.get("/api/balitower/finance/invoices", headers=fin_headers)
    assert r_fin_ok.status_code == 200, "Finance user should access invoices"
    print("  [OK] Finance user accessed invoice data (200 OK)")

    # Finance user CANNOT access Inventory
    r_inv_block2 = client.get("/api/balitower/inventory/items", headers=fin_headers)
    assert r_inv_block2.status_code == 403, f"Expected 403 for Inventory endpoint, got {r_inv_block2.status_code}"
    print("  [PASS] Finance user blocked from Inventory data (403 Forbidden)")

    # Finance user CANNOT access HR
    r_hr_block2 = client.get("/api/balitower/hr/employees", headers=fin_headers)
    assert r_hr_block2.status_code == 403, f"Expected 403 for HR endpoint, got {r_hr_block2.status_code}"
    print("  [PASS] Finance user blocked from HR data (403 Forbidden)")

    print("\n=== ALL ISOLATION & RBAC TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_tenant_isolation()
