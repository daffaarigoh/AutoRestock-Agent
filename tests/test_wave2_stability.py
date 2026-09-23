"""
Unit and integration tests for Wave 2: Data Consistency & Operational Stability.
Verifies DuckDB-backed PR storage persistence across restarts, destructive reset guards and backups,
HR leave approval state machine and transaction atomicity, decoupled health check, and schema migrations.
"""

import os
import shutil
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from api.main import app
from core.config import settings
from core.schemas import PurchaseItemRequest, PurchaseRequisitionDoc
from database.db import get_db_connection, execute_db_write
from database.migrations import run_migrations
from api.routers.approval_routes import PR_STORE, persist_pr_to_db, _ensure_pr_in_store


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_token(client):
    from core.security import create_access_token
    # Lookup admin's token_version from DB
    conn = get_db_connection(read_only=True)
    row = conn.execute("SELECT token_version FROM users WHERE username = 'admin'").fetchone()
    conn.close()
    tv = row[0] if row and row[0] else 1
    return create_access_token({"sub": "admin", "role": "ADMIN", "tenant_id": "ALL", "token_version": tv})


@pytest.fixture
def hr_token(client):
    from core.security import create_access_token
    conn = get_db_connection(read_only=True)
    row = conn.execute("SELECT token_version FROM users WHERE username = 'userb'").fetchone()
    conn.close()
    tv = row[0] if row and row[0] else 1
    return create_access_token({"sub": "userb", "role": "USER", "tenant_id": "HR", "token_version": tv})



def test_migrations_runner_idempotency():
    """Verify schema migrations run cleanly and idempotently."""
    first_run = run_migrations()
    assert isinstance(first_run, list)
    second_run = run_migrations()
    assert second_run == []


def test_pr_store_persists_across_restart(client, admin_token):
    """
    Verify that PR written to PR_STORE is persisted to DuckDB and can be
    reconstructed after an in-memory cache wipe (simulating a service restart).
    """
    test_pr_num = "PR-TEST-2026-WAVE2"
    doc = PurchaseRequisitionDoc(
        pr_number=test_pr_num,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=[
            PurchaseItemRequest(
                item_id="ITM-W2-01",
                name="Optical Transceiver SFP+ 10G",
                reorder_qty=20,
                unit="pcs",
                vendor_id="VND-001",
                vendor_name="PT Vendor Test",
                unit_price=250000.0,
                total_price=5000000.0,
                reason="Wave 2 automated persistence test"
            )
        ],
        total_budget=5000000.0,
        auditor_status="PASSED",
        auditor_notes="Compliance test pass",
        pdf_path=f"/storage/documents/{test_pr_num.replace('-', '_')}.pdf",
        status="PENDING",
        tenant_id="INVENTORY"
    )

    # 1. Write to PR_STORE
    PR_STORE[test_pr_num] = doc
    assert test_pr_num in PR_STORE

    # 2. Simulate complete memory loss (server restart)
    dict.clear(PR_STORE)
    assert not dict.__contains__(PR_STORE, test_pr_num)

    # 3. Access via PR_STORE.get() - should reload from DuckDB
    reloaded = PR_STORE.get(test_pr_num)
    assert reloaded is not None
    assert reloaded.pr_number == test_pr_num
    assert reloaded.total_budget == 5000000.0
    assert len(reloaded.items) == 1
    assert reloaded.items[0].name == "Optical Transceiver SFP+ 10G"

    # 4. Clean up test record
    def _clean(conn):
        conn.execute("DELETE FROM purchase_requests WHERE pr_number = ?", [test_pr_num])
    execute_db_write(_clean)
    dict.pop(PR_STORE, test_pr_num, None)


def test_reset_endpoints_protected_in_production(client, admin_token):
    """Verify reset endpoints are blocked in production when ALLOW_DEMO_RESET is false."""
    original_env = settings.APP_ENV
    original_reset = settings.ALLOW_DEMO_RESET
    try:
        settings.APP_ENV = "production"
        settings.ALLOW_DEMO_RESET = False

        headers = {"Authorization": f"Bearer {admin_token}", "X-Confirm-Reset": "true"}
        res = client.post("/api/approval/reset?confirm=true", headers=headers)
        assert res.status_code == 403
        assert "dinonaktifkan di lingkungan produksi" in res.json()["detail"]

        res_clear = client.post("/api/approval/clear-all?confirm=true", headers=headers)
        assert res_clear.status_code == 403
        assert "dinonaktifkan di lingkungan produksi" in res_clear.json()["detail"]
    finally:
        settings.APP_ENV = original_env
        settings.ALLOW_DEMO_RESET = original_reset


def test_reset_creates_pre_reset_backup(client, admin_token):
    """Verify reset creates an automatic timestamped backup when reset is permitted."""
    original_reset = settings.ALLOW_DEMO_RESET
    try:
        settings.ALLOW_DEMO_RESET = True
        headers = {"Authorization": f"Bearer {admin_token}", "X-Confirm-Reset": "true"}
        res = client.post("/api/approval/reset?confirm=true&seed=true", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "backup_created" in data
        assert os.path.exists(data["backup_created"])
    finally:
        settings.ALLOW_DEMO_RESET = original_reset


def test_hr_leave_approval_validation_and_transitions(client, hr_token):
    """
    Verify:
    1. Unknown action returns 422 Unprocessable Entity
    2. Missing leave ID returns 404
    3. Duplicate transition returns 400
    4. Successful approval deducts employee leave balance atomically
    """
    headers = {"Authorization": f"Bearer {hr_token}"}

    # 1. Invalid action -> 422
    res_invalid = client.post(
        "/api/balitower/hr/leave-requests/LV-9999/action",
        json={"action": "INVALID_ACTION"},
        headers=headers
    )
    assert res_invalid.status_code == 422

    # 2. Non-existent leave ID -> 404
    res_404 = client.post(
        "/api/balitower/hr/leave-requests/LV-NONEXISTENT-999/action",
        json={"action": "APPROVE"},
        headers=headers
    )
    assert res_404.status_code == 404

    # 3. Setup temporary test leave request and test employee
    test_emp_id = "EMP-TEST-W2"
    test_leave_id = "LV-TEST-W2"

    def _setup_tx(conn):
        conn.execute("DELETE FROM employees WHERE employee_id = ?", [test_emp_id])
        conn.execute("""
            INSERT INTO employees (employee_id, full_name, department, job_title, leave_balance)
            VALUES (?, 'Budi Santoso Wave2', 'HR', 'Field Tech', 12);
        """, [test_emp_id])
        conn.execute("DELETE FROM leave_requests WHERE leave_id = ?", [test_leave_id])
        conn.execute("""
            INSERT INTO leave_requests (leave_id, employee_id, leave_type, start_date, end_date, days_requested, reason, approval_status)
            VALUES (?, ?, 'ANNUAL_LEAVE', '2026-10-01', '2026-10-03', 3, 'Keperluan Keluarga', 'PENDING_APPROVAL');
        """, [test_leave_id, test_emp_id])

    execute_db_write(_setup_tx)


    try:
        # Initial approval -> should succeed and reduce leave balance from 12 to 9
        res_approve = client.post(
            f"/api/balitower/hr/leave-requests/{test_leave_id}/action",
            json={"action": "APPROVE"},
            headers=headers
        )
        assert res_approve.status_code == 200
        assert res_approve.json()["status"] == "APPROVED"

        # Verify leave balance in DB
        conn = get_db_connection(read_only=True)
        bal = conn.execute("SELECT leave_balance FROM employees WHERE employee_id = ?", [test_emp_id]).fetchone()[0]
        status = conn.execute("SELECT approval_status FROM leave_requests WHERE leave_id = ?", [test_leave_id]).fetchone()[0]
        conn.close()
        assert bal == 9
        assert status == "APPROVED"

        # Re-approval or re-rejection -> should return 400 Bad Request
        res_duplicate = client.post(
            f"/api/balitower/hr/leave-requests/{test_leave_id}/action",
            json={"action": "APPROVE"},
            headers=headers
        )
        assert res_duplicate.status_code == 400
        assert "sudah diproses sebelumnya" in res_duplicate.json()["detail"]

    finally:
        # Cleanup test records
        def _cleanup_tx(conn):
            conn.execute("DELETE FROM leave_requests WHERE leave_id = ?", [test_leave_id])
            conn.execute("DELETE FROM employees WHERE employee_id = ?", [test_emp_id])
        execute_db_write(_cleanup_tx)


def test_decoupled_health_endpoints(client):
    """Verify local liveness is decoupled from external LLM."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert "local_service" in data
    assert data["local_service"] == "online"
    assert "database" in data
    assert "llm_connected" in data

    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "alive"

    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200
    assert res_ready.json()["status"] == "ready"
