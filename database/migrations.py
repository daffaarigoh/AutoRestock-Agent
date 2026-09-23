"""
Database Schema Migration Manager for AutoRestock-Agent.
Provides ordered, versioned, idempotent schema migrations executed prior to handling application traffic.
"""

import logging
from datetime import datetime
from typing import Callable

from database.db import execute_db_write

logger = logging.getLogger("autorestock.migrations")


def _migration_001_workflow_columns(conn):
    """Ensure workflows table has tenant_id and example_prompts columns."""
    existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
    if "workflows" in existing_tables:
        wf_cols = [c[0] for c in conn.execute("DESCRIBE workflows;").fetchall()]
        if "tenant_id" not in wf_cols:
            conn.execute("ALTER TABLE workflows ADD COLUMN tenant_id VARCHAR DEFAULT 'ALL';")
            logger.info("[Migration 001] Added 'tenant_id' column to workflows.")
        if "example_prompts" not in wf_cols:
            conn.execute("ALTER TABLE workflows ADD COLUMN example_prompts VARCHAR;")
            logger.info("[Migration 001] Added 'example_prompts' column to workflows.")


def _migration_002_workflow_requests_table(conn):
    """Ensure workflow_requests table exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_requests (
            id VARCHAR PRIMARY KEY,
            username VARCHAR NOT NULL,
            tenant_id VARCHAR NOT NULL,
            prompt TEXT NOT NULL,
            notes TEXT,
            status VARCHAR DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_by VARCHAR,
            resolved_workflow_id VARCHAR,
            title VARCHAR
        );
    """)
    existing_cols = [c[0] for c in conn.execute("DESCRIBE workflow_requests;").fetchall()]
    if "title" not in existing_cols:
        conn.execute("ALTER TABLE workflow_requests ADD COLUMN title VARCHAR;")
    logger.info("[Migration 002] Ensured workflow_requests table exists.")



def _migration_003_users_token_version(conn):
    """Ensure users table has token_version column for session revocation."""
    existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
    if "users" in existing_tables:
        user_cols = [c[0] for c in conn.execute("DESCRIBE users;").fetchall()]
        if "token_version" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 1;")
            logger.info("[Migration 003] Added 'token_version' column to users table.")


def _migration_004_consumed_action_tokens(conn):
    """Ensure consumed_action_tokens table exists for single-use approval links."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consumed_action_tokens (
            token_signature VARCHAR PRIMARY KEY,
            action_type VARCHAR,
            target_id VARCHAR,
            action VARCHAR,
            consumed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    logger.info("[Migration 004] Ensured consumed_action_tokens table exists.")


def _migration_005_purchase_requests_schema(conn):
    """Ensure purchase_requests table exists with full metadata columns."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS purchase_requests (
            pr_number VARCHAR PRIMARY KEY,
            created_at TIMESTAMP,
            status VARCHAR,
            total_amount BIGINT,
            items_json TEXT,
            tenant_id VARCHAR DEFAULT 'ALL',
            auditor_status VARCHAR DEFAULT 'PASSED',
            auditor_notes TEXT,
            pdf_path VARCHAR
        );
    """)
    # Check if extra columns are missing from existing purchase_requests
    pr_cols = [c[0] for c in conn.execute("DESCRIBE purchase_requests;").fetchall()]
    if "auditor_status" not in pr_cols:
        conn.execute("ALTER TABLE purchase_requests ADD COLUMN auditor_status VARCHAR DEFAULT 'PASSED';")
    if "auditor_notes" not in pr_cols:
        conn.execute("ALTER TABLE purchase_requests ADD COLUMN auditor_notes TEXT;")
    if "pdf_path" not in pr_cols:
        conn.execute("ALTER TABLE purchase_requests ADD COLUMN pdf_path VARCHAR;")
    logger.info("[Migration 005] Ensured purchase_requests table schema is complete.")


def _migration_006_purchase_orders_pr_number(conn):
    """Ensure purchase_orders table has pr_number column."""
    existing_tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
    if "purchase_orders" in existing_tables:
        po_cols = [c[0] for c in conn.execute("DESCRIBE purchase_orders;").fetchall()]
        if "pr_number" not in po_cols:
            conn.execute("ALTER TABLE purchase_orders ADD COLUMN pr_number VARCHAR;")
            logger.info("[Migration 006] Added 'pr_number' column to purchase_orders.")


MIGRATIONS: list[tuple[int, str, Callable]] = [
    (1, "workflow_columns", _migration_001_workflow_columns),
    (2, "workflow_requests_table", _migration_002_workflow_requests_table),
    (3, "users_token_version", _migration_003_users_token_version),
    (4, "consumed_action_tokens", _migration_004_consumed_action_tokens),
    (5, "purchase_requests_schema", _migration_005_purchase_requests_schema),
    (6, "purchase_orders_pr_number", _migration_006_purchase_orders_pr_number),
]


def run_migrations() -> list[int]:
    """
    Executes all unapplied schema migrations in sequential order.
    Returns list of newly applied migration versions.
    """
    applied_now = []

    def _runner(conn):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name VARCHAR NOT NULL,
                applied_at TIMESTAMP NOT NULL
            );
        """)
        applied_versions = {
            r[0] for r in conn.execute("SELECT version FROM schema_migrations;").fetchall()
        }

        for version, name, func in MIGRATIONS:
            if version not in applied_versions:
                logger.info(f"Applying migration {version:03d}_{name}...")
                func(conn)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?);",
                    [version, name, datetime.now()]
                )
                applied_now.append(version)
                logger.info(f"Migration {version:03d}_{name} applied successfully.")

    execute_db_write(_runner)
    return applied_now
