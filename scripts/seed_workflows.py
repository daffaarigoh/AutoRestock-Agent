import json
from database.db import get_db_connection

def seed_workflows():
    wf_list = [
        ("WF-A01", "Pipeline Pengadaan Material PR-to-PO End-to-End", "Alur pengadaan otomatis terintegrasi dari inspeksi stok, penerbitan PR draf, approval email, hingga penerbitan PO ke vendor.", "Periksa seluruh saldo stok material menara dan kabel fiber optic di gudang logistik usera yang berada di bawah ambang batas minimum. Hitung kuantitas reorder dan vendor rekanan terbaik, terbitkan dokumen resmi Purchase Requisition (PR) dan draf PO PENDING_APPROVAL, lalu kirim email notifikasi ke manajer.", json.dumps({"workflow": "pipeline_pengadaan_material_pr_to_po_end_to_end", "steps": [{"type": "tool", "tool": "inventory.get_low_stock_products"}, {"type": "agent", "task": "calculate_reorder_quantity"}, {"type": "tool", "tool": "docgen.compile"}, {"type": "tool", "tool": "notification.dispatch"}]}), "INVENTORY"),
        ("WF-A02", "Penerimaan Barang Fisik PO & Update Saldo", "Verifikasi barang Purchase Order (PO) yang tiba di gudang logistik dan sinkronisasi penambahan stok fisik.", "Verifikasi kedatangan barang Purchase Order yang tiba di gudang, catat penerimaan aktual, update status DELIVERED, dan tambahkan stok ke saldo gudang.", json.dumps({"workflow": "usera_po_goods_receipt", "steps": [{"type": "tool", "tool": "inventory.check_specific_stock"}, {"type": "tool", "tool": "inventory.crud_record"}, {"type": "tool", "tool": "notification.dispatch"}]}), "INVENTORY"),
        ("WF-A03", "Tracking Pengiriman PO & Cetak Dokumen PDF", "Monitoring status pengiriman Purchase Order (PO) aktif dan penerbitan surat pesanan resmi format PDF Typst.", "Audit status PO yang sedang dikirim (IN_TRANSIT), tampilkan nomor PO dan total nilai, serta terbitkan berkas PDF surat pesanan resmi untuk diunduh.", json.dumps({"workflow": "usera_po_tracking_pdf", "steps": [{"type": "tool", "tool": "po.query_orders"}, {"type": "tool", "tool": "docgen.compile_po"}]}), "INVENTORY"),
        ("WF-002", "Cek Absensi & Lembur Teknisi", "Audit absensi kunjungan site menara dan rekap jam lembur teknisi.", "Tarik data absensi teknisi lapangan dengan validasi geofencing GPS dan kalkulasi biaya lembur.", json.dumps({"workflow": "hr_attendance_audit", "steps": [{"type": "tool", "tool": "hr.audit_attendance"}]}), "HR"),
        ("WF-003", "Filter Pelamar Rigger K3", "Menyaring kandidat rigger tower dengan sertifikasi TKPK dan tes medis layak ketinggian.", "Filter kandidat rigger berdasarkan sertifikasi TKPK 1/2 dan tes kesehatan.", json.dumps({"workflow": "hr_filter_candidates", "steps": [{"type": "tool", "tool": "hr.filter_candidates"}]}), "HR"),
        ("WF-004", "Laporan Pendapatan Sewa Menara", "Rekapitulasi tagihan invoice sewa menara ke operator telekomunikasi (Telkomsel, XL, IOH).", "Tarik data invoice sewa menara per operator dan status pembayarannya.", json.dumps({"workflow": "finance_revenue_report", "steps": [{"type": "tool", "tool": "finance.revenue_report"}]}), "FINANCE"),
        ("WF-005", "Audit Beban Listrik & Sewa Lahan", "Laporan pengeluaran operasional utilitas listrik PLN, BBM genset, dan sewa lahan tower.", "Analisis beban operasional per site mencakup tagihan PLN dan jatuh tempo sewa tanah.", json.dumps({"workflow": "finance_opex_audit", "steps": [{"type": "tool", "tool": "finance.opex_audit"}]}), "FINANCE"),
        ("WF-006", "Ringkasan Arus Kas (Cash Flow)", "Laporan arus kas masuk vs keluar harian dan posisi saldo bersih.", "Hitung net cash flow dari transaksi inflow dan outflow.", json.dumps({"workflow": "finance_cashflow", "steps": [{"type": "tool", "tool": "finance.cashflow_summary"}]}), "FINANCE")
    ]
    
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            description TEXT NOT NULL,
            business_instruction TEXT NOT NULL,
            compiled_json TEXT NOT NULL,
            tenant_id VARCHAR DEFAULT 'ALL'
        );
    """)
    conn.execute("DELETE FROM workflows;")
    conn.executemany("INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?);", wf_list)
    conn.commit()
    rows = conn.execute("SELECT id, name, tenant_id FROM workflows ORDER BY id ASC;").fetchall()
    print("Workflows seeded successfully:")
    for r in rows:
        print(f"  [{r[0]}] {r[1]} -> Tenant: {r[2]}")
    conn.close()

if __name__ == "__main__":
    seed_workflows()
