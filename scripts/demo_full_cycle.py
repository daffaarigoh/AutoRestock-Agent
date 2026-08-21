"""
Full Cycle Demo Script
Demonstrates end-to-end pipeline: Document OCR -> Audit -> Prompt Restock -> PR Creation -> Manager Approval.
"""

import asyncio
from database.db import db
from agents.workflow import workflow
from core.config import settings
from core.schemas import PRStatus


async def run_cycle():
    print("=========================================================")
    print("AutoRestock-V2 Autonomous Restock Cycle Demo")
    print("=========================================================")

    # 1. Show inventory state before
    stats_before = db.get_dashboard_stats()
    print(f"[METRICS] Initial State: Total Items={stats_before.total_items}, Low Stock={stats_before.low_stock_items}, Pending PRs={stats_before.pending_prs}")

    # 2. Run NLP Prompt Restock
    user_prompt = "Restock minyak goreng, beras, dan kopi kapal api sebanyak 40 unit dengan prioritas URGENT"
    print(f"\n[PROMPT] Processing User Prompt: '{user_prompt}'")
    result = await workflow.execute_prompt_restock(user_prompt)

    print(f"Status: {result.get('status')}")
    print(f"Reasoning: {result.get('parsed_intent').reasoning if result.get('parsed_intent') else 'N/A'}")
    print(f"Generated PRs: {len(result.get('generated_prs', []))}")

    # 3. Simulate Manager Approval on the first pending PR
    pending_prs = db.get_purchase_requisitions(status="pending_approval")
    if pending_prs:
        target_pr = pending_prs[0]
        print(f"\n[ACTION] Simulating Manager Approval on PR {target_pr.pr_number}...")
        approved = db.update_pr_status(
            pr_number=target_pr.pr_number,
            status=PRStatus.APPROVED,
            approver_name="Bapak Hartono (VP Supply Chain)",
            notes="Approved after budget clearance."
        )
        print(f"[APPROVED] PR {approved.pr_number} successfully APPROVED!")
        if approved.pdf_path:
            print(f"[PDF] Official Document: {approved.pdf_path}")

    # 4. Show final stats
    stats_after = db.get_dashboard_stats()
    print(f"\n[METRICS] Final State: Pending PRs={stats_after.pending_prs}, Approved PRs={stats_after.approved_prs}, Total Discrepancies={stats_after.active_discrepancies}")
    print("=========================================================")


if __name__ == "__main__":
    asyncio.run(run_cycle())
