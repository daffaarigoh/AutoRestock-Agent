import sys
import subprocess
from pathlib import Path
import pytest

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

@pytest.fixture(scope="session", autouse=True)
def ensure_test_database():
    """
    Session-wide autouse fixture that guarantees storage/balitower.db
    exists and contains seeded tables before any test runs.
    """
    db_path = WORKSPACE_DIR / "storage" / "balitower.db"
    if not db_path.exists() or db_path.stat().st_size < 1000:
        generator_script = WORKSPACE_DIR / "scripts" / "generate_balitower_data.py"
        if generator_script.exists():
            subprocess.run([sys.executable, str(generator_script)], check=True)
