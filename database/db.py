import duckdb
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = WORKSPACE_DIR / "storage"
DB_PATH = STORAGE_DIR / "inventory.db"


def get_db_connection(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Get a connection to the DuckDB inventory database."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(DB_PATH.as_posix(), read_only=read_only)

