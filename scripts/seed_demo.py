import sys
import time
from pathlib import Path

# Fix console encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Workspace setup
WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from agents.workflow import resume_approval, run_autorestock_cycle
from database.db import get_db_connection
from database.seed_data import init_db, seed_data


def print_banner(title: str):
    print("\n" + "=" * 90)
    print(f"🚀 {title.upper()}")
    print("=" * 90)


def print_section(title: str):
    print("\n" + "-" * 90)
    print(f"📌 {title}")
    print("-" * 90)


def run_interactive_simulation():
    start_time = time.time()
    
    print_banner("AUTORESTOCK-AGENT: FULL INTERACTIVE HITL SIMULATION")
    print("Multi-Agent Architecture: Scan -> Qwen-35b (Planner) -> Nemotron-35 (Auditor) -> Typst (DocGen) -> HITL Approval")
    
    # -------------------------------------------------------------
    # 1. Database Initialization & Seeding
    # -------------------------------------------------------------
    print_section("FASE 1: Inisialisasi Database DuckDB & Seeding Data")
    conn = init_db()
    seed_data(conn)
    critical_count = conn.execute("SELECT COUNT(*) FROM items WHERE current_stock <= min_threshold;").fetchone()[0]
    print(f"Total Critical Items Found in Legacy/Shared Table: {critical_count}")
    conn.close()
    
    # -------------------------------------------------------------
    # 2. Trigger Autonomous Multi-Agent Cycle (Up to HITL Pause)
    # -------------------------------------------------------------
    print_section("FASE 2 & 3: Menjalankan LangGraph Multi-Agent Cycle")
    print("Memicu alur otomasi:")
    print("  1. Scan Node: Identifikasi stok < threshold")
    print("  2. Planner Node (qwen-35b): Vendor matching & kalkulasi Dynamic Safety Stock")
    print("  3. Audit Node (nemotron-35): Validasi anggaran & compliance guardrail")
    print("  4. Typst Node: Kompilasi dokumen formal PDF Purchase Requisition")
    
    pr = run_autorestock_cycle()
    
    print("\n" + "=" * 90)
    print("📋 DRAF PURCHASE REQUISITION TERBENTUK (STATUS: PENDING_APPROVAL):")
    print("=" * 90)
    print(f"Nomor PR       : {pr.pr_number}")
    print(f"Dibuat Pada    : {pr.created_at}")
    print(f"Jumlah Barang  : {len(pr.items)} barang")
    print(f"Total Anggaran : Rp {pr.total_budget:,.0f}")
    print(f"Status Audit   : {pr.auditor_status} (Nemotron-35)")
    print(f"Catatan Audit  : {pr.auditor_notes}")
    print(f"Lokasi Draf PDF: {pr.pdf_path}")
    print("=" * 90)
    
    # -------------------------------------------------------------
    # 3. Human-in-the-Loop (HITL) Interactive Decision
    # -------------------------------------------------------------
    print_section("FASE 4: Human-in-the-Loop (HITL) - Menunggu Keputusan Manajer")
    print("[PAUSED] LangGraph terhenti di breakpoint 'interrupt_before=[wait_approval_node]'.")
    print("Dokumen telah siap. Silakan tentukan keputusan pengadaan:")
    
    try:
        user_choice = input("\n>>> [TINDAKAN MANAJER] Ketik 'Y' untuk APPROVE, atau 'N' untuk REJECT: ").strip().upper()
    except (EOFError, KeyboardInterrupt):
        user_choice = "Y"
        print("\n[Defaulting to APPROVE due to non-interactive environment]")

    if user_choice in ["Y", "YES", "APPROVE"]:
        action = "APPROVE"
        approver = "Bapak Hendra (VP Supply Chain)"
        notes = "Disetujui untuk pengadaan darurat safety stock."
    else:
        action = "REJECT"
        approver = "Bapak Hendra (VP Supply Chain)"
        notes = "Ditolak: Anggaran dialihkan ke periode berikutnya."
        
    print(f"\n[Sinyal Diterima] Keputusan: {action}")
    
    # -------------------------------------------------------------
    # 4. Resume LangGraph Execution with Manager's Decision
    # -------------------------------------------------------------
    print_section(f"FASE 5: Melanjutkan LangGraph ({action}) & Update DuckDB")
    approved_pr = resume_approval(
        pr_number=pr.pr_number,
        action=action,
        approver_name=approver,
        notes=notes
    )
    
    print("[RESUMED] LangGraph selesai mengeksekusi 'wait_approval_node' -> END.")
    print(f"Status PR Akhir   : {approved_pr.status}")
    print(f"Dokumen Final PDF : {approved_pr.pdf_path}")
    
    # -------------------------------------------------------------
    # 5. Verify Orders Table in DuckDB
    # -------------------------------------------------------------
    print_section("VERIFIKASI STATUS DATA 'orders' DI DUCKDB")
    conn = get_db_connection(read_only=True)
    orders_df = conn.execute("""
        SELECT 
            o.order_id,
            o.pr_number,
            o.item_id,
            i.name AS item_name,
            o.vendor_id,
            o.quantity,
            o.unit_price,
            o.total_price,
            o.status
        FROM orders o
        JOIN items i ON o.item_id = i.item_id
        WHERE o.pr_number = ?
        ORDER BY o.total_price DESC;
    """, [pr.pr_number]).df()
    conn.close()
    
    print(orders_df.to_string(index=False))
    
    elapsed = time.time() - start_time
    print_banner(f"SIMULASI SELESAI ({action}) DALAM {elapsed:.2f} DETIK!")


if __name__ == "__main__":
    run_interactive_simulation()
