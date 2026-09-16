# 📋 Dokumen Ringkasan Refactoring & Hardening Arsitektur
## AutoRestock-Agent Enterprise Refactor

Dokumen ini ditujukan untuk tim engineer dan coding agent di kantor sebagai panduan lengkap mengenai seluruh perubahan, perbaikan celah keamanan, optimasi konkurensi, dan pembersihan *dead code* yang telah diterapkan pada repositori.

Branch: `refactor/enterprise-architecture-cleanup`  
Tanggal: 16 September 2026

---

## 🎯 1. Ikhtisar Masalah & Solusi (Executive Summary)

Sebelum refactoring, audit kode menemukan beberapa masalah fundamental yang menyebabkan sistem rentan, lambat pada beban tinggi, dan berisiko *crash* saat dijalankan di server Linux kantor:

1. **Security Vulnerability (CORS & Auth Bypass):**
   - Wildcard CORS (`allow_origins=["*"]`) dipadukan dengan `allow_credentials=True`, membuka celah eksploitasi CSRF/XSS.
   - Endpoint SSE Agent (`/api/stream/agent-run`) tidak memiliki validasi JWT Token (`Depends(get_current_user)`), memungkinkan siapa saja memicu eksekusi agent dan membakar kuota vLLM.
   - `SECRET_KEY` memakai fallback default statis tanpa peringatan di log produksi.

2. **Event Loop Starvation & Blocking Concurrency:**
   - Pemanggilan `smtplib.SMTP` (email dispatch) dan `bcrypt.checkpw` / `verify_password` dijalankan secara sinkronus langsung di dalam thread utama FastAPI (event loop), menyebabkan server mengalami freeze (lag) ratusan milidetik per request.
   - Eksekusi LangGraph membuat `ThreadPoolExecutor(max_workers=1)` baru dan `asyncio.run()` pada setiap iterasi LLM (*anti-pattern* yang memboroskan resource dan rentan thread leak).

3. **DuckDB Database Lock & Concurrency Collisions:**
   - DuckDB adalah single-writer database berbasis file (`balitower.db`). Beberapa route melakukan write (`UPDATE`/`INSERT`/`DELETE`) tanpa locking atau retry, sehingga menyebabkan error fatal `duckdb.IOException: Could not set lock on file` ketika diakses oleh banyak user/worker secara bersamaan.
   - Terdapat DDL dinamis (`ALTER TABLE purchase_orders ADD COLUMN pr_number VARCHAR;`) yang dipanggil berulang kali saat approval.
   - State Purchase Requisition (PR) hanya disimpan di memori (`PR_STORE`), sehingga ketika server restart, seluruh riwayat PR hilang.

4. **Hardcoded Sensitive Data & Privacy Leak:**
   - Alamat email pribadi pengembang (`zeiniahalfiah@gmail.com`, `muhammaddaffaarigoh@gmail.com`) di-hardcode ke dalam routing logika bisnis dan prompt executor.

5. **Resource Redundancy & Dead Code:**
   - Instansiasi `ModelGateway()` berulang kali membuat connection pool baru untuk setiap panggilan LLM tanpa keep-alive reuse dan tanpa proteksi circuit breaker.
   - File duplikat `docs/flowchart.html` berukuran 1.2MB identik dengan `web/static/flowchart.html`.
   - Script generator usang `scripts/build_flowchart_html.py` dengan hardcoded path linux lokal.
   - Dummy method `calculate_safety_stock` di MCP server hanya mengembalikan input tanpa logika kalkulasi.

---

## 🛠️ 2. Rincian Perubahan per File / Komponen

### A. Security & Configuration
#### 1. `core/config.py`
- Menambahkan konfigurasi `ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"]` yang dapat dioverride melalui environment variable.
- Menambahkan validasi saat startup: jika `SECRET_KEY` masih menggunakan default dev key pada production mode, sistem akan mencetak peringatan keamanan kritis (`CRITICAL SECURITY WARNING`).

#### 2. `api/main.py`
- Mengganti `allow_origins=["*"]` dengan `allow_origins=settings.ALLOWED_ORIGINS`, mematuhi standar keamanan W3C CORS ketika `allow_credentials=True`.

#### 3. `api/routers/stream_routes.py`
- Menambahkan dependensi autentikasi `current_user: TokenData = Depends(get_current_user)` pada endpoint `@router.get("/agent-run")`.
- Menyelaraskan filtering data SSE agent dengan `current_user.tenant_id` (mencegah *cross-tenant data leakage*).

---

### B. Network, LLM Gateway & Circuit Breaker
#### 4. `core/llm_client.py`
- Mengubah `ModelGateway` menjadi singleton pattern murni (`gateway = ModelGateway()`).
- Menambahkan HTTP Connection Pool sharing via `get_client()` (`httpx.AsyncClient(limits=Limits(max_keepalive_connections=20, max_connections=50))`) untuk mencegah soket TCP ke vLLM exhaustion.
- Mengimplementasikan **Circuit Breaker Pattern** (`CLOSED`, `OPEN`, `HALF_OPEN`) dengan fail count threshold dan cool-off period 30 detik. Jika endpoint vLLM kantor sedang down, request langsung di-fail-fast tanpa membuat ribuan request gantung di server FastAPI.

---

### C. Concurrency, Asynchronous & Anti-Event Loop Blocking
#### 5. `core/dispatcher.py`
- Menghapus email pribadi hardcoded, beralih ke dynamic resolver dengan corporate fallback (`manager@balitower.co.id`).
- Membungkus pengiriman email SMTP sinkronus dengan `await asyncio.to_thread(_send_smtp_sync, ...)`, sehingga proses pengiriman email tidak memblokir event loop asyncio FastAPI.

#### 6. `api/routers/auth_routes.py`
- Membungkus verifikasi password bcrypt (`verify_password`) dan password hashing (`get_password_hash`) dengan `await asyncio.to_thread(...)`. CPU-intensive task tidak lagi memacetkan request lain.
- Mengoptimasi query pencarian user di `/login` dengan `fetchone()` langsung alih-alih mengalokasikan pandas DataFrame.
- Mengamankan operasi user management ke DuckDB menggunakan write serialization.

#### 7. `agents/workflow.py`
- Menghilangkan *anti-pattern* pembuatan `ThreadPoolExecutor(max_workers=1)` berulang kali di `_run_sync`. Menggantinya dengan **Dedicated Async Loop Bridge** (`WorkflowAsyncBridge`) yang berjalan secara persistent sebagai daemon thread terisolasi menggunakan `asyncio.run_coroutine_threadsafe`.
- Mengganti instansiasi manual `gateway = ModelGateway()` di `planner_node` dan `audit_node` dengan shared singleton `from core.llm_client import gateway`.
- Membungkus update DuckDB (`record_orders_to_db` dan `update_db_orders_status`) dengan `execute_db_write`.

---

### D. DuckDB Concurrency, Persistence & Idempotency
#### 8. `database/db.py`
- Mengimplementasikan `DuckDBManager` dengan re-entrant lock (`threading.RLock()`) dan connection retry backoff (`duckdb.IOException`).
- Menambahkan method helper `DuckDBManager.transaction(callback)` dan `execute_db_write(func_or_query)` untuk menjamin seluruh operasi INSERT/UPDATE/DELETE DuckDB dilakukan secara terserialisasi dan bebas race-condition.

#### 9. `database/seed_data.py`
- Menambahkan DDL `CREATE TABLE IF NOT EXISTS purchase_requests` secara otomatis pada fase startup/inisialisasi.
- Menambahkan migrasi otomatis untuk kolom `pr_number` pada `purchase_orders` dan `tenant_id` pada `workflows`.

#### 10. `api/routers/approval_routes.py`
- Menghapus dynamic DDL `ALTER TABLE purchase_orders ADD COLUMN pr_number VARCHAR;` dari handler request runtime.
- Memodifikasi `_ensure_pr_in_store` dan `get_all_requisitions`: jika data PR belum ada di in-memory `PR_STORE`, sistem membaca dan merekonstruksi dokumen dari tabel `orders` maupun `purchase_requests` di DuckDB.
- Menambahkan fungsi `persist_pr_to_db` sehingga setiap PR baru atau perubahan status tersimpan persisten ke disk DuckDB dan bertahan meskipun service direstart.
- Mengamankan `_update_db_status`, `reset_sample_data`, dan `clear_all_prs_and_pos` menggunakan `execute_db_write`.

---

### E. Privacy, Multi-Tenancy & MCP Tooling
#### 11. `agents/router.py` & `agents/json_executor.py`
- Menghilangkan hardcoded email pribadi pengembang (`zeiniahalfiah@gmail.com`, `muhammaddaffaarigoh@gmail.com`).
- Mengimplementasikan dynamic database lookup ke tabel `employees` dan fallback ke corporate address (`manager@balitower.co.id`).
- Memakai shared singleton `gateway` dari `core.llm_client`.

#### 12. `mcp_server/tools.py`
- Memperbarui fungsi `calculate_safety_stock(min_threshold, avg_daily_usage, lead_time_days)` dengan rumus safety stock buffer inventaris berbasis burn rate dan lead time riil (`max(round(usage * lead_time * 0.5), min_threshold)`), menggantikan fungsi dummy lama yang hanya mengembalikan parameter mentah.

---

### F. File Cleanup & Dead Code Removal
- Menghapus `docs/flowchart.html` (1.2 MB file duplikat redundant dari `web/static/flowchart.html`).
- Menghapus `scripts/build_flowchart_html.py` (script lokal ad-hoc yang tidak lagi digunakan).

---

## 🚀 3. Panduan untuk Agent & Engineer di Kantor (Handover Guide)

Untuk melanjutkan pekerjaan atau memverifikasi perubahan ini di server kantor:

1. **Checkout Branch Baru:**
   ```bash
   git fetch origin
   git checkout refactor/enterprise-architecture-cleanup
   ```

2. **Verifikasi Kompilasi & Kode Bersih:**
   ```bash
   python -m compileall -q .
   ```
   *(Harus keluar dengan returncode 0 tanpa error)*

3. **Jalankan Inisialisasi Database DuckDB:**
   ```bash
   python -m database.seed_data
   ```

4. **Jalankan Test Suite:**
   ```bash
   pytest tests/
   ```

5. **Jalankan Server Dashboard & API:**
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
   ```

6. **Environment Variable Baru (Opsional di `.env`):**
   ```env
   # Daftar origin yang diizinkan untuk CORS (pisahkan dengan koma bila lebih dari satu)
   ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000,http://YOUR_OFFICE_IP:8000
   
   # Ganti secret key untuk production deployment
   SECRET_KEY=isi_dengan_random_secret_string_32_karakter
   ```

---

*Refactoring selesai dengan aman tanpa mengubah fungsionalitas inti bisnis aplikasi AutoRestock-Agent.*
