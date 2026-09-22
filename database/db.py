import threading
import time
from pathlib import Path
from typing import Any

import duckdb

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = WORKSPACE_DIR / "storage"
DB_PATH = STORAGE_DIR / "balitower.db"

_db_write_lock = threading.RLock()


def get_db_connection(read_only: bool = False, max_retries: int = 15) -> duckdb.DuckDBPyConnection:
    """Get a connection to the DuckDB inventory database with retry logic for file locks."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    for attempt in range(max_retries):
        try:
            return duckdb.connect(DB_PATH.as_posix(), read_only=read_only)
        except duckdb.IOException as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(0.1 + 0.05 * attempt)


class DuckDBManager:
    """
    Centralized manager providing serialized write access and safe connection lifecycle.
    Prevents single-writer lock collisions across concurrent requests.
    """
    @staticmethod
    def execute_write(query: str, params: list[Any] | None = None) -> Any:
        """Executes write transaction with serialized process lock."""
        with _db_write_lock:
            conn = get_db_connection(read_only=False)
            try:
                res = conn.execute(query, params or [])
                conn.commit()
                return res
            finally:
                conn.close()

    @staticmethod
    def execute_read(query: str, params: list[Any] | None = None) -> list[Any]:
        """Executes read query safely and ensures connection closure."""
        conn = get_db_connection(read_only=True)
        try:
            return conn.execute(query, params or []).fetchall()
        finally:
            conn.close()

    @staticmethod
    def transaction(func):
        """Executes a callable that receives a write connection under process-wide write lock."""
        with _db_write_lock:
            conn = get_db_connection(read_only=False)
            try:
                result = func(conn)
                conn.commit()
                return result
            finally:
                conn.close()


def execute_db_write(func_or_query, params: list[Any] | None = None) -> Any:
    """Convenience helper for DuckDBManager write operations."""
    if callable(func_or_query):
        return DuckDBManager.transaction(func_or_query)
    return DuckDBManager.execute_write(func_or_query, params)
