#!/usr/bin/env python3
"""
Controlled migration script to update user credentials securely.
- Enforces backup before changes.
- Automatically revokes existing user sessions by incrementing token_version.
- Prevents demo passwords unless ALLOW_DEMO_PASSWORDS is set or --allow-demo is specified.
"""

import os
import sys
import shutil
import argparse
from datetime import datetime
from pathlib import Path

# Workspace resolution
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import duckdb
from core.config import settings
from core.security import get_password_hash
from database.db import DB_PATH, STORAGE_DIR


def create_backup(db_path: Path) -> Path:
    backup_dir = STORAGE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"balitower_backup_pre_pwd_migration_{timestamp}.db"
    shutil.copy2(db_path, backup_file)
    return backup_file


def migrate_passwords(allow_demo: bool = False):
    db_path = DB_PATH
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    effective_allow_demo = allow_demo or getattr(settings, "ALLOW_DEMO_PASSWORDS", False) or settings.APP_ENV == "development"

    # Resolve passwords from environment or demo defaults if allowed
    admin_pwd = os.environ.get("ADMIN_PASSWORD")
    user_pwd = os.environ.get("USER_PASSWORD")

    if not admin_pwd or not user_pwd:
        if not effective_allow_demo:
            print(
                "Error: Demo passwords (admin123/user123) are disabled in this environment (ALLOW_DEMO_PASSWORDS=False).\n"
                "To set custom secure passwords, provide ADMIN_PASSWORD and USER_PASSWORD environment variables.\n"
                "To explicitly allow demo passwords for a local/test environment, pass --allow-demo or set ALLOW_DEMO_PASSWORDS=True in .env.",
                file=sys.stderr
            )
            sys.exit(1)
        admin_pwd = admin_pwd or "admin123"
        user_pwd = user_pwd or "user123"

    print("Creating pre-migration database backup...")
    backup_path = create_backup(db_path)
    print(f"Backup created at: {backup_path}")

    # Generate bcrypt hashes
    print("Generating bcrypt password hashes...")
    admin_hash = get_password_hash(admin_pwd)
    user_hash = get_password_hash(user_pwd)

    con = duckdb.connect(str(db_path), read_only=False)
    try:
        # Check token_version column exists
        cols = [c[1] for c in con.execute("PRAGMA table_info('users')").fetchall()]
        if "token_version" not in cols:
            con.execute("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 1")

        # Update admin
        con.execute(
            "UPDATE users SET password_hash = ?, token_version = COALESCE(token_version, 1) + 1 WHERE username = 'admin'",
            [admin_hash]
        )

        # Update standard users
        con.execute(
            "UPDATE users SET password_hash = ?, token_version = COALESCE(token_version, 1) + 1 WHERE username IN ('usera', 'userb', 'userc')",
            [user_hash]
        )

        updated_users = con.execute("SELECT username, role, tenant_id, token_version FROM users ORDER BY username").fetchall()
        print("Successfully updated user credentials and revoked legacy active sessions:")
        for u in updated_users:
            print(f"  - User: {u[0]}, Role: {u[1]}, Tenant: {u[2]}, Active Token Version: {u[3]}")

    finally:
        con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate user passwords with backup and session revocation.")
    parser.add_argument("--allow-demo", action="store_true", help="Allow default demo passwords (admin123/user123)")
    args = parser.parse_args()
    migrate_passwords(allow_demo=args.allow_demo)
