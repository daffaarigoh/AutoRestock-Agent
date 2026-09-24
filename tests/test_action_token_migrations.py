"""Regression tests for approval token schema compatibility and replay protection."""

import duckdb

import database.db as db_module
from core.action_links import consume_action_token, create_action_token, is_action_token_consumed, verify_action_token
from database.migrations import (
    _migration_004_consumed_action_tokens,
    _migration_007_normalize_consumed_action_token_columns,
)


def _column_names(conn):
    return {row[0] for row in conn.execute("DESCRIBE consumed_action_tokens;").fetchall()}


def test_migration_normalizes_legacy_schema_and_preserves_consumed_tokens(tmp_path):
    db_path = tmp_path / "legacy.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE consumed_action_tokens (
            token_sig VARCHAR PRIMARY KEY,
            kind VARCHAR NOT NULL,
            object_id VARCHAR NOT NULL,
            action VARCHAR NOT NULL,
            consumed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute(
        "INSERT INTO consumed_action_tokens (token_sig, kind, object_id, action) VALUES (?, ?, ?, ?)",
        ["existing-signature", "pr", "PR-OLD", "APPROVE"],
    )

    _migration_007_normalize_consumed_action_token_columns(conn)
    _migration_007_normalize_consumed_action_token_columns(conn)

    assert {"token_signature", "action_type", "target_id", "action", "consumed_at"} <= _column_names(conn)
    row = conn.execute(
        "SELECT token_signature, action_type, target_id, action FROM consumed_action_tokens"
    ).fetchone()
    assert row == ("existing-signature", "pr", "PR-OLD", "APPROVE")
    conn.close()

def test_missing_consumption_table_fails_closed(tmp_path, monkeypatch):
    db_path = tmp_path / "unmigrated.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.close()
    monkeypatch.setattr(
        db_module,
        "get_db_connection",
        lambda read_only=False: duckdb.connect(str(db_path)),
    )
    token = create_action_token("pr", "PR-TEST-UNMIGRATED", "APPROVE")

    assert is_action_token_consumed(token)
    assert not verify_action_token(token, "pr", "PR-TEST-UNMIGRATED", "APPROVE")

def test_migrated_schema_accepts_token_once_and_rejects_replay(tmp_path, monkeypatch):
    db_path = tmp_path / "approval.duckdb"
    conn = duckdb.connect(str(db_path))
    _migration_004_consumed_action_tokens(conn)
    _migration_007_normalize_consumed_action_token_columns(conn)
    conn.close()

    monkeypatch.setattr(
        db_module,
        "get_db_connection",
        lambda read_only=False: duckdb.connect(str(db_path)),
    )
    token = create_action_token("pr", "PR-TEST-007", "APPROVE")

    assert verify_action_token(token, "pr", "PR-TEST-007", "APPROVE")
    assert consume_action_token(token, "pr", "PR-TEST-007", "APPROVE")
    assert not verify_action_token(token, "pr", "PR-TEST-007", "APPROVE")
    assert not consume_action_token(token, "pr", "PR-TEST-007", "APPROVE")