from pathlib import Path

import duckdb

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = WORKSPACE_DIR / "storage"
DB_PATH = STORAGE_DIR / "inventory.db"


import time

def get_db_connection(read_only: bool = False, max_retries: int = 5) -> duckdb.DuckDBPyConnection:
    """Get a connection to the DuckDB inventory database with retry logic for file locks."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    for attempt in range(max_retries):
        try:
            return duckdb.connect(DB_PATH.as_posix(), read_only=read_only)
        except duckdb.IOException as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(0.1 * (2 ** attempt))  # Exponential backoff: 0.1s, 0.2s, 0.4s, 0.8s...


