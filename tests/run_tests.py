import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tests.test_api_and_pipeline import (
    test_database_and_seed,
    test_stock_adjustment,
    test_llm_prompt_parsing,
    test_ocr_and_auditor,
    test_agent_workflow,
    test_api_endpoints
)
import asyncio


def run():
    print("==================================================")
    print("[TEST SUITE] AutoRestock-V2 Full Verification")
    print("==================================================")
    test_database_and_seed()
    test_stock_adjustment()
    asyncio.run(test_llm_prompt_parsing())
    asyncio.run(test_ocr_and_auditor())
    asyncio.run(test_agent_workflow())
    test_api_endpoints()
    print("==================================================")
    print("[ALL 6 TEST SUITES PASSED CLEANLY!]")
    print("==================================================")


if __name__ == "__main__":
    run()
