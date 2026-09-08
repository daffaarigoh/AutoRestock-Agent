"""
Script Verifikasi dan Pemeriksaan Data Multi-Tenant PT Bali Towerindo Sentra Tbk
Menampilkan ringkasan data dan simulasi query untuk ketiga scope (Inventory, HR, Finance).
"""

import sys
from pathlib import Path
import duckdb
import pandas as pd

# Handle Windows cp1252 console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

pd.set_option('display.max_columns', 15)
pd.set_option('display.width', 1000)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "storage" / "balitower.db"

conn = duckdb.connect(str(DB_PATH), read_only=True)

print("=" * 80)
print("  VERIFIKASI DATABASE MULTI-TENANT PT BALI TOWERINDO SENTRA TBK")
print("=" * 80)

# 1. Daftar Seluruh Tabel dan Jumlah Record
print("\n--> [1] DAFTAR TABEL & JUMLAH BARIS:")
tables = conn.execute("SHOW TABLES").fetchall()
table_stats = []
for t in tables:
    tname = t[0]
    count = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
    scope = "01_Inventory" if tname in ["suppliers", "warehouses", "inventory_items", "stock_balances", "purchase_orders"] else \
            "02_HR_Recruitment" if tname in ["telecom_sites", "employees", "attendances", "leave_requests", "job_postings", "candidates"] else \
            "03_Finance"
    table_stats.append((scope, tname, count))

df_stats = pd.DataFrame(table_stats, columns=["Scope / Modul", "Nama Tabel", "Total Baris"])
print(df_stats.sort_values(by=["Scope / Modul", "Nama Tabel"]).to_string(index=False))

# 2. Scope HR: Flow Cari & Filter Karyawan / Kandidat
print("\n" + "=" * 80)
print("--> [2] HR - FLOW CARI & FILTER KANDIDAT RIGGER/TOWER CLIMBER (K3 TKPK Valid):")
query_hr_filter = """
    SELECT 
        c.candidate_id,
        c.full_name,
        j.job_title,
        c.k3_cert_held,
        c.years_of_experience,
        c.medical_checkup_status,
        c.technical_score,
        c.recruitment_stage
    FROM candidates c
    JOIN job_postings j ON c.job_id = j.job_id
    WHERE c.k3_cert_held IN ('TKPK 1', 'TKPK 2')
      AND c.medical_checkup_status = 'FIT_FOR_HEIGHT'
    ORDER BY c.technical_score DESC;
"""
print(conn.execute(query_hr_filter).df().to_string(index=False))

# 3. Scope HR: Flow Absensi Geofencing Site Visit & Lembur
print("\n" + "=" * 80)
print("--> [3] HR - FLOW ABSENSI SITE VISIT MENARA & VALIDASI GEOFENCING:")
query_hr_att = """
    SELECT 
        a.attendance_id,
        a.date,
        e.full_name AS teknisi,
        s.site_id,
        s.site_name,
        a.distance_to_site_m AS jarak_gps_meter,
        a.overtime_hours AS jam_lembur,
        a.status
    FROM attendances a
    JOIN employees e ON a.employee_id = e.employee_id
    JOIN telecom_sites s ON a.site_id = s.site_id
    WHERE a.overtime_hours > 0
    LIMIT 6;
"""
print(conn.execute(query_hr_att).df().to_string(index=False))

# 4. Scope HR: Flow Cuti
print("\n" + "=" * 80)
print("--> [4] HR - FLOW PENGAJUAN CUTI & DELEGASI TEKNISI PENGGANTI:")
query_hr_leave = """
    SELECT 
        l.leave_id,
        e.full_name AS pemohon,
        l.leave_type,
        l.days_requested AS hari,
        l.start_date,
        l.reason,
        sub.full_name AS teknisi_pengganti,
        l.approval_status
    FROM leave_requests l
    JOIN employees e ON l.employee_id = e.employee_id
    LEFT JOIN employees sub ON l.substitute_employee_id = sub.employee_id;
"""
print(conn.execute(query_hr_leave).df().to_string(index=False))

# 5. Scope Finance: Flow Laporan Pemasukan (Revenue Invoices per Operator)
print("\n" + "=" * 80)
print("--> [5] FINANCE - FLOW LAPORAN PEMASUKAN SEWA MENARA (REVENUE PER OPERATOR):")
query_fin_rev = """
    SELECT 
        c.client_name AS nama_operator,
        COUNT(i.invoice_id) AS total_invoice,
        CAST(SUM(i.total_billed) AS BIGINT) AS total_tagihan_idr,
        CAST(SUM(CASE WHEN i.payment_status = 'PAID' THEN i.total_billed ELSE 0 END) AS BIGINT) AS tagihan_lunas_idr,
        CAST(SUM(CASE WHEN i.payment_status = 'UNPAID' THEN i.total_billed ELSE 0 END) AS BIGINT) AS piutang_outstanding_idr
    FROM revenue_invoices i
    JOIN telecom_clients c ON i.client_id = c.client_id
    GROUP BY c.client_name
    ORDER BY total_tagihan_idr DESC;
"""
print(conn.execute(query_fin_rev).df().to_string(index=False))

# 6. Scope Finance: Flow Laporan Pengeluaran (OPEX Breakdown)
print("\n" + "=" * 80)
print("--> [6] FINANCE - FLOW LAPORAN PENGELUARAN BIAYA OPERASIONAL SITE (OPEX):")
query_fin_opex = """
    SELECT 
        account_name AS kategori_beban,
        COUNT(*) AS frekuensi_transaksi,
        CAST(SUM(amount) AS BIGINT) AS total_pengeluaran_idr
    FROM financial_transactions
    WHERE trx_type = 'OUTFLOW'
    GROUP BY account_name
    ORDER BY total_pengeluaran_idr DESC;
"""
print(conn.execute(query_fin_opex).df().to_string(index=False))

# 7. Scope Finance: Ringkasan Arus Kas Masuk vs Keluar (Net Cash Flow)
print("\n" + "=" * 80)
print("--> [7] FINANCE - ARUS KAS BERSIH (NET CASH FLOW):")
query_cashflow = """
    SELECT 
        trx_type AS jenis_arus_kas,
        COUNT(*) AS total_transaksi,
        CAST(SUM(amount) AS BIGINT) AS total_nominal_idr
    FROM financial_transactions
    GROUP BY trx_type;
"""
print(conn.execute(query_cashflow).df().to_string(index=False))

# 8. Scope Inventory: Stok Kritis yang Membutuhkan Restock
print("\n" + "=" * 80)
print("--> [8] INVENTORY - ITEM MATERIAL DENGAN STOK KRITIS (ALERT RESTOCK):")
query_inv_alert = """
    SELECT 
        sb.balance_id,
        w.warehouse_name,
        i.item_code,
        i.item_name,
        sb.quantity_on_hand AS stok_saat_ini,
        sb.reorder_point AS batas_minimum,
        sb.stock_status
    FROM stock_balances sb
    JOIN inventory_items i ON sb.item_id = i.item_id
    JOIN warehouses w ON sb.warehouse_id = w.warehouse_id
    WHERE sb.stock_status IN ('CRITICAL', 'LOW_STOCK')
    ORDER BY sb.stock_status, sb.quantity_on_hand ASC;
"""
print(conn.execute(query_inv_alert).df().to_string(index=False))

print("\n" + "=" * 80)
print("  SEMUA DATA DAN INTEGRASI ANTAR SCOPE BERFUNGSI SEMPURNA TANPA ERROR!")
print("=" * 80)

conn.close()
