import json
from database.db import get_db_connection

def migrate():
    conn = get_db_connection()
    try:
        # 1. Update existing workflows tenant_id
        conn.execute("UPDATE workflows SET tenant_id = 'INVENTORY' WHERE id = 'WF-001';")
        conn.execute("UPDATE workflows SET tenant_id = 'HR' WHERE id IN ('WF-002', 'WF-003');")
        conn.execute("UPDATE workflows SET tenant_id = 'FINANCE' WHERE id IN ('WF-004', 'WF-005', 'WF-006');")

        # 2. Insert WF-ALL-01, WF-ALL-02, WF-ALL-03 if not exists
        all_wfs = [
            ("WF-ALL-01", "Cek Profil Akun & Hak Akses", "Melihat informasi profil pengguna yang sedang login, role, divisi tenant, dan modul yang dapat diakses.", "Periksa akun yang sedang login dan tampilkan detail hak akses serta batasan divisi.", json.dumps({"workflow": "check_user_profile", "steps": [{"type": "tool", "tool": "system.check_profile"}]}), "ALL"),
            ("WF-ALL-02", "Informasi Sistem & Status Layanan", "Melihat ringkasan status operasional server, versi aplikasi, database DuckDB, dan gateway AI.", "Cek status operasional seluruh modul sistem AutoRestock-Agent.", json.dumps({"workflow": "system_health_info", "steps": [{"type": "tool", "tool": "system.get_system_info"}]}), "ALL"),
            ("WF-ALL-03", "Panduan Operasional & Kontak Darurat", "Panduan SOP penggunaan sistem AutoRestock-Agent, navigasi modul, dan kontak darurat IT/Operasional.", "Tampilkan panduan operasional perusahaan dan kontak darurat lintas divisi.", json.dumps({"workflow": "company_guidelines", "steps": [{"type": "tool", "tool": "system.get_company_guidelines"}]}), "ALL")
        ]

        for wf in all_wfs:
            existing = conn.execute("SELECT id FROM workflows WHERE id = ?", [wf[0]]).fetchone()
            if existing:
                conn.execute("UPDATE workflows SET name = ?, description = ?, business_instruction = ?, compiled_json = ?, tenant_id = ? WHERE id = ?", [wf[1], wf[2], wf[3], wf[4], wf[5], wf[0]])
            else:
                conn.execute("INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?)", wf)
        
        conn.commit()
        print("Successfully migrated workflows in DuckDB!")
        rows = conn.execute("SELECT id, name, tenant_id FROM workflows ORDER BY id ASC").fetchall()
        for r in rows:
            print(f"  - {r[0]}: {r[1]} [{r[2]}]")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
