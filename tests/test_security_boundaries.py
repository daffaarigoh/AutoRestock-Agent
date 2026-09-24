"""Regression checks for public document and approval access."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from agents.autonomous_agent import AutonomousAgent
from core.action_links import create_action_token, verify_action_token
from core.config import Settings


def test_approval_and_document_routes_reject_anonymous_requests():
    client = TestClient(app)
    assert client.get("/storage/documents/anything.pdf").status_code == 404
    assert client.get("/api/documents/pr/PR-2026-0819-001/download").status_code == 401
    assert client.get("/api/approval/quick-action?pr_number=PR-2026-0819-001&action=APPROVE").status_code == 403
    assert client.post("/api/approval/reset").status_code in {401, 403}
    assert client.post("/api/approval/action", json={"pr_number": "PR-2026-0819-001", "action": "APPROVE", "manager_name": "Test"}).status_code in {401, 403}
    assert client.post("/api/agent/approve", json={"pr_number": "PR-2026-0819-001", "action": "APPROVE"}).status_code in {401, 403}


def test_approval_token_is_bound_to_object_action_and_expiry(monkeypatch):
    monkeypatch.setattr("core.action_links.is_action_token_consumed", lambda token: False)
    token = create_action_token("pr", "PR-001", "APPROVE", now=100)
    assert verify_action_token(token, "pr", "PR-001", "APPROVE", now=101)
    assert not verify_action_token(token, "pr", "PR-002", "APPROVE", now=101)
    assert not verify_action_token(token, "pr", "PR-001", "REJECT", now=101)
    assert not verify_action_token(token, "leave", "PR-001", "APPROVE", now=101)
    assert not verify_action_token(token, "pr", "PR-001", "APPROVE", now=100 + 8 * 86400)
    assert not verify_action_token(token + "0", "pr", "PR-001", "APPROVE", now=101)


def test_document_cookie_is_cleared_on_logout():
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    assert client.get("/api/documents/reports/missing.pdf/download").status_code == 404
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/documents/reports/missing.pdf/download").status_code == 401


def test_production_rejects_default_signing_key():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(APP_ENV="production", SECRET_KEY="super-secret-enterprise-key-for-autorestock-agent")


def test_agent_sql_cannot_read_files():
    result = AutonomousAgent.execute_tool_query_database(
        "SELECT * FROM read_text('requirements.txt')", "INVENTORY", "USER"
    )
    assert "error" in result
