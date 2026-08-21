"""
Seed Demo Script for AutoRestock-V2
Initializes database, generates synthetic warehouse documents, and executes an initial autonomous restock run.
"""

import asyncio
from database.seed_data import seed_database
from scripts.generate_sample_assets import generate_all_samples
from agents.workflow import workflow
from core.config import settings


async def main():
    print("==================================================")
    print("[INIT] AutoRestock-V2 System Initialization & Seeding")
    print("==================================================")

    # 1. Populate Suppliers & Items
    seed_database()

    # 2. Generate Synthetic Document Assets
    generate_all_samples()

    # 3. Ingest Sample Kartu Stok to simulate discrepancy detection
    sample_stock_card = settings.DATA_DIR / "samples" / "kartu_stok_warehouse.png"
    if sample_stock_card.exists():
        print("\n--- Ingesting Sample Kartu Stok for Audit ---")
        res1 = await workflow.execute_document_ingest(str(sample_stock_card))
        print(f"Status: {res1.get('status')}")
        disc_count = res1.get('discrepancy_report').total_discrepancies if res1.get('discrepancy_report') else 0
        print(f"Discrepancies Found: {disc_count}")

    # 4. Ingest Sample Surat Jalan to simulate inbound stock update
    sample_sj = settings.DATA_DIR / "samples" / "surat_jalan_inbound.png"
    if sample_sj.exists():
        print("\n--- Ingesting Sample Surat Jalan Inbound Delivery ---")
        res2 = await workflow.execute_document_ingest(str(sample_sj))
        print(f"Status: {res2.get('status')}")
        print(f"PRs Generated: {len(res2.get('generated_prs', []))}")

    # 5. Execute Prompt Restock command for depleted items
    print("\n--- Executing Sample AI Prompt Restock Command ---")
    prompt = "Tolong restock semua barang ATK dan IT yang stoknya menipis segera ke supplier rekanan."
    res3 = await workflow.execute_prompt_restock(prompt, auto_execute=True)
    print(f"Status: {res3.get('status')}")
    print(f"PRs Generated: {len(res3.get('generated_prs', []))}")

    print("\n==================================================")
    print("[SUCCESS] AutoRestock-V2 System Ready!")
    print(f"Server can be launched with: python -m uvicorn api.main:app --host {settings.API_HOST} --port {settings.API_PORT} --reload")
    print(f"Dashboard URL: http://localhost:{settings.API_PORT}")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(main())
