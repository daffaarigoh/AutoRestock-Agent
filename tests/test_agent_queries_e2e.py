import asyncio
import sys
import time
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from core.security import TokenData
from agents.autonomous_agent import AutonomousAgent


async def run_query_test(name: str, prompt: str, user: TokenData):
    print(f"\n{'='*70}")
    print(f"TEST CASE: {name}")
    print(f"PROMPT: \"{prompt}\"")
    print(f"USER: {user.username} (Role: {user.role}, Tenant: {user.tenant_id})")
    print(f"{'='*70}")
    
    t0 = time.time()
    res = await AutonomousAgent.run(prompt, current_user=user)
    elapsed = time.time() - t0
    
    msg = res.get("message", "")
    action_type = res.get("action_type", "")
    
    # Assertions
    has_raw_json = "Tindakan berhasil dijalankan" in msg or "```json\n{" in msg
    assert not has_raw_json, f"FAILED: {name} returned raw JSON output!"
    assert len(msg.strip()) > 20, f"FAILED: {name} returned empty message!"
    
    print(f"Status: PASSED ({elapsed:.2f}s)")
    print(f"Action Type: {action_type}")
    print(f"Message Snippet (First 500 chars):\n{msg[:500]}...")
    if "| No |" in msg:
        print("\n[✓] Markdown Table correctly included in response.")


async def main():
    admin_user = TokenData(username="admin", role="ADMIN", full_name="Administrator", tenant_id="ALL")
    inv_user = TokenData(username="usera", role="USER", full_name="Logistics Officer", tenant_id="INVENTORY")
    hr_user = TokenData(username="userb", role="USER", full_name="HR Specialist", tenant_id="HR")
    fin_user = TokenData(username="userc", role="USER", full_name="Finance Analyst", tenant_id="FINANCE")

    # 1. Main user query: apa aja stok yang kurang?
    await run_query_test("Query 1: User Case - apa aja stok yang kurang?", "apa aja stok yang kurang?", inv_user)

    # 2. Inventory query: Cek material kritis
    await run_query_test("Query 2: Cek material kritis", "Cek material yang saat ini berstatus kritis atau di bawah safety threshold", inv_user)

    # 3. Warehouse list query
    await run_query_test("Query 3: Daftar seluruh gudang", "Tampilkan informasi kapasitas dan daftar seluruh gudang regional Bali Tower", inv_user)

    # 4. View PO document
    await run_query_test("Query 4: Dokumen PO", "Tolong tampilkan dokumen PDF untuk PO-2026-001", admin_user)

    # 5. HR query: Absensi teknisi
    await run_query_test("Query 5: Absensi teknisi", "Tampilkan 5 catatan absensi kunjungan teknisi terbaru", hr_user)

    # 6. Finance query: Klien operator
    await run_query_test("Query 6: Klien operator", "Tampilkan daftar klien operator telekomunikasi terbesar", fin_user)

    print("\n" + "="*70)
    print("ALL 6 REAL-WORLD TEST CASES COMPLETED AND PASSED PERFECTLY!")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
