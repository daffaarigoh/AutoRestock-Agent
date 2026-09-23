# Rencana kerja AutoRestock-Agent untuk Antigravity

Tanggal: 23 September 2026. Basis pemeriksaan: GitHub `main` pada commit `183958a8f7188a65d99cf104794694fb48ed6718` dan salinan lokal proyek. Ini adalah evaluasi statis dan rencana eksekusi, bukan bukti bahwa seluruh kemungkinan cacat sudah ditemukan. Saya tidak mengubah kode, database, kredensial, atau layanan server pada tahap perencanaan ini.

## Kesepakatan kerja yang perlu dipertahankan

- Codex bertindak sebagai **planner/reviewer**: membaca proyek, menemukan risiko, menulis urutan kerja dan kriteria penerimaan, lalu meninjau hasil Antigravity. Codex tidak mengedit kode, mengubah server, melakukan push, atau deploy kecuali pengguna mengubah pembagian tugas ini secara tegas.
- Antigravity bertindak sebagai **executor**: mengimplementasikan, menguji, membuat commit/push, dan menerapkan perubahan sesuai batas lingkup.
- GitHub `daffaarigoh/AutoRestock-Agent` adalah sumber kode. Server target hanya `/home/jds2/AutoRestock-Agent-Dap` dan port `8060`. Pertahankan `.env`, `storage/`, serta perubahan lokal pada tiga CSV di `data/balitower/`; jangan menyentuh proyek atau port lain.
- Antigravity mengirimkan ringkasan diff, temuan yang diputuskan, hasil pengujian Linux, commit/CI, kondisi `git status` server, dan hasil pemeriksaan port 8060 kepada Codex untuk review berikutnya.

## Permintaan kata sandi

Pengguna meminta akun `admin` memakai `admin123`, dan seluruh akun pengguna biasa memakai `user123` lagi. **Belum dilakukan pada tahap ini.** File `scratch/codex-audit-20260923/rotated-credentials.txt` hanyalah catatan; mengeditnya tidak mengubah hash di DuckDB. Empat akun yang sebelumnya dirotasi adalah `admin`, `usera`, `userb`, `userc`.

Hambatan kode saat ini: `api/routers/auth_routes.py:62` menolak dua kata sandi tersebut saat `APP_ENV=production`/`staging`, walaupun hash database diganti. Hash contoh masih ada di `database/seed_data.py:135` dan `scripts/generate_balitower_data.py:554`; `README.md:321` memperingatkan bahwa nilai ini untuk pengujian lokal. Aplikasi di port 8060 memakai HTTP dan mode produksi. Memakai kata sandi yang sama dan sudah dipublikasikan untuk semua user memberi akses mudah ke data HR, keuangan, dan inventory. Ini bertentangan dengan target keamanan proyek.

Instruksi eksekusi untuk Antigravity: siapkan jalur penggantian kata sandi yang transaksional melalui API admin yang ada (`PUT /api/auth/admin/users/{user_id}`) atau migrasi terkontrol, cadangkan database terlebih dahulu, dan cabut sesi lama ketika hash berubah. Jangan menaruh kata sandi baru atau hash produksi dalam commit, log, atau catatan kredensial lama. Jika nilai demo memang harus aktif di port 8060, batasi akses ke port tersebut untuk lingkungan uji yang disetujui dan jadikan izin kata sandi demo sebagai konfigurasi yang **mati secara default**. Perbarui dokumentasi agar pengguna tahu kapan mode uji aktif. Jika pembatasan akses ini tidak dapat dipenuhi, laporkan tugas kata sandi sebagai berisiko sebelum mengaktifkannya.

## Gelombang 1 — perbaikan risiko akses dan keamanan

| Prioritas | Bukti | Tugas Antigravity | Kriteria penerimaan |
| --- | --- | --- | --- |
| P0 | `api/routers/balitower_routes.py:33-63` memberi akses berdasarkan username `admin`, `usera`, `userb`, `userc` dan memberi `MANAGER` semua domain | Satukan kebijakan RBAC pada role/tenant yang tersimpan di database; hapus pengecualian username dan audit semua route mutasi | Mengubah tenant/role akun langsung mengubah haknya; user lintas tenant menerima 403 pada baca dan tulis |
| P0 | `api/routers/auth_routes.py:358-400` mengembalikan `business_instruction` dan `compiled_json` workflow tanpa autentikasi; `api/main.py:67` menyediakan alias publik | Wajibkan autentikasi, filter tenant dari token, sediakan respons ringkas untuk UI; tinjau `/api/agent/tools` | Tanpa token 401; user hanya melihat workflow miliknya atau yang memang global; detail internal tidak bocor |
| P0 | `web/static/admin.html:5081` dan banyak `onclick` lain memasukkan data ke kode JavaScript melalui HTML string; `escapeHtml` tidak cukup untuk konteks atribut JavaScript | Ganti handler inline dan `innerHTML` berbasis data dengan DOM API dan `addEventListener`; audit `web/static/js/dashboard.js` dan `web/static/login.html` | Teks dari user/database ditampilkan sebagai teks; tanda kutip dan HTML dalam nama tidak menjadi kode |
| P0 | `web/static/js/dashboard.js:242` mengembalikan HTML dari `localStorage` ke `innerHTML`; token tersimpan di `sessionStorage` (`web/static/login.html:437`) | Hilangkan pemulihan HTML mentah; nilai tersimpan harus berupa data terstruktur dan dirender aman. Setelah XSS tertutup, rencanakan sesi cookie HTTP-only dengan proteksi CSRF untuk seluruh API | Konten tersimpan tidak dapat menjalankan skrip; token tidak dapat dicuri melalui jalur XSS yang ditemukan |
| P0 | `core/security.py:53-65` hanya memeriksa role/tenant saat memvalidasi JWT; `api/routers/auth_routes.py:85` logout hanya menghapus cookie | Tambahkan versi sesi atau waktu perubahan password pada user; validasi klaim itu pada setiap request; atur pencabutan saat reset password/logout | Token lama gagal segera setelah password diubah atau sesi dicabut |
| P1 | `api/routers/auth_routes.py:872-1069` menyediakan CRUD generik untuk seluruh tabel DuckDB, termasuk `users` | Ganti `SHOW TABLES` sebagai izin otomatis dengan allowlist tabel/kolom; jangan izinkan ubah `password_hash` lewat CRUD generik; batasi `limit`, `offset`, dan pencarian | CRUD hanya menjangkau tabel/kolom bisnis yang disetujui; perubahan akun lewat API khusus |
| P1 | `core/action_links.py:13` memberi masa aktif tautan persetujuan tujuh hari dan tidak menyimpan status pemakaian | Jadikan token sekali pakai, kaitkan ke penerima/keputusan dan status objek; pertahankan GET sebagai halaman konfirmasi, POST untuk perubahan | POST ulang tidak mengubah keputusan atau menimbulkan efek samping kedua |
| P1 | `api/routers/auth_routes.py:24-75` menyimpan limit login di dictionary proses | Batasi ukuran dan masa simpan state; pakai penyimpanan bersama jika layanan nanti memakai beberapa proses; tentukan IP tepercaya di belakang proxy | Limit konsisten dan tidak tumbuh tanpa batas |

## Gelombang 2 — konsistensi data dan operasi

| Prioritas | Bukti | Tugas Antigravity | Kriteria penerimaan |
| --- | --- | --- | --- |
| P0 | `api/routers/approval_routes.py:89` memakai `PR_STORE` di memori; route agen dan stream menulis ke sana | Jadikan DuckDB sumber status PR; cache hanya opsional dan dapat dibangun ulang | PR dan statusnya tetap sama setelah proses 8060 dihidupkan ulang |
| P1 | `api/routers/approval_routes.py:1570-1670` memiliki reset/clear yang menghapus tabel, CSV, dan PDF | Pindahkan fungsi demo/reset dari layanan produksi atau berikan mode khusus, pemeriksaan dampak, dan backup sebelum operasi | Tidak ada tombol atau endpoint yang dapat menghapus data produksi tanpa alur yang disengaja |
| P1 | `api/routers/balitower_routes.py:765-800` menganggap semua action selain `APPROVE` sebagai `REJECTED`; update bisa melaporkan sukses walau ID tidak ada | Gunakan enum aksi, validasi keberadaan dan transisi status, transaksi untuk perubahan saldo cuti | Aksi tak dikenal 422/400; ID tak ada 404; saldo cuti berubah tepat sekali |
| P1 | `api/main.py:88-111` dan `api/routers/auth_routes.py:358` melakukan perubahan skema saat startup/request | Buat migrasi database berversi dan jalankan sebelum proses menerima traffic | Request baca tidak mengubah skema; restart tidak mengulang migrasi secara berbahaya |
| P1 | `api/main.py:164-185` membuat `/health` bergantung pada layanan LLM luar | Pisahkan liveness lokal dari readiness LLM/DB | Gangguan LLM tidak membuat pengawas mematikan proses yang sehat; dashboard tetap menunjukkan status LLM terpisah |
| P1 | `database/db.py:12-69` mengunci hanya di dalam satu proses; banyak route membuka koneksi tulis langsung | Pusatkan transaksi tulis dan aturan concurrency; tetapkan satu worker sampai pengujian multi proses selesai | Tidak ada lock collision atau transaksi setengah jalan pada beban bersamaan |
| P2 | `requirements.txt` memakai batas bawah tanpa batas atas dan memasukkan `pytest` ke runtime | Kunci versi yang teruji, pisahkan dev dependencies, catat prosedur pembaruan | Instalasi ulang di Ubuntu menghasilkan versi konsisten dan CI tetap hijau |
| P2 | `deployment/deploy.sh` menulis `/etc/systemd/system/autorestock.service`, sedangkan layanan 8060 sekarang berjalan lewat `nohup` | Rancang unit bernama khusus untuk proyek Dap, rollback cepat, dan pemulihan setelah reboot. Jangan membuat unit atau menyentuh `/etc` sebelum batas folder yang ditetapkan pengguna diperluas | Hanya proyek Dap/8060 yang berubah; restart/reboot mempertahankan layanan setelah izin lokasi unit diberikan |

## Gelombang 3 — pembuktian dan pembersihan dead code

Jangan menghapus berkas hanya karena tidak ditemukan `import`: FastAPI memakai dekorator route, HTML memakai URL, Typst memakai template, dan skrip `scripts/` mungkin dijalankan manual. Buat inventaris setiap file, route, fungsi, aset, dan tabel; tandai pemanggil runtime, UI, CI, dokumentasi, dan operasi manual. Gunakan `ruff` untuk import/variabel tak terpakai dan `vulture` sebagai daftar kandidat, lalu periksa manual sebelum menghapus. Hapus dalam perubahan kecil yang bisa di-review bersama semua pemanggilnya.

Kandidat konkret yang sudah terlihat:

1. `api/main.py:95-101`: pembuatan PDF PR contoh saat startup membaca `PR_STORE` yang mulai kosong; contoh hanya dimasukkan oleh alur lain atau endpoint reset. Periksa apakah cabang startup pernah benar-benar berjalan; hapus jika tidak, atau pindahkan ke fixture demo.
2. `api/routers/balitower_routes.py:1080-1093`: `finance/transactions` dan `finance/chart-of-accounts` selalu `[]`. UI masih memanggil keduanya (`web/static/js/dashboard.js:1175,1225`), jadi pilih implementasi nyata atau hapus route, pemanggil UI, dan kontrak pengujian bersama-sama.
3. `api/main.py:12-15`: manipulasi `sys.path` saat impor perlu dinilai terhadap cara paket dijalankan; hapus bila tak diperlukan dalam instalasi dan CI.
4. `tests/audit_results_50_queries.json` ditulis ulang oleh `tests/test_50_queries_comprehensive.py:215`; putuskan apakah ini fixture tetap atau artefak hasil. Jika artefak, keluarkan dari Git dan arahkan keluaran ke folder sementara.
5. `REFACTORING_SUMMARY.md` memuat kondisi/prompt lama (termasuk rujukan 1.600 baris) yang perlu diverifikasi; arsipkan atau perbarui bila tidak lagi mencerminkan kode.
6. `agents/json_executor.py` sekitar 2.100 baris, `web/static/admin.html` sekitar 6.100 baris, dan `web/static/js/dashboard.js` sekitar 4.000 baris: pecah menurut domain dan kontrak yang ada, sambil menghapus cabang/alias yang terbukti tak dipakai. Ukuran file sendiri bukan bukti dead code.

## Urutan eksekusi dan keluaran yang harus diserahkan Antigravity

1. Buat inventaris dependensi dan cadangan data target; catat SHA `main`, proses pemilik port 8060, serta perubahan lokal server. Jangan memulihkan/menimpa tiga CSV yang sudah berubah.
2. Kerjakan Gelombang 1 dalam PR/commit terpisah; lakukan review Codex sebelum deploy. Tangani permintaan kata sandi dengan pembatasan lingkungan yang disebut di atas.
3. Kerjakan Gelombang 2. Gunakan migrasi yang dapat dibatalkan dan jangan menjalankan generator data terhadap database produksi.
4. Kerjakan Gelombang 3 bertahap. Untuk setiap penghapusan, cantumkan bukti tidak ada pemanggil atau tunjukkan pengganti UI/API yang dipakai.
5. Pada Ubuntu/Python 3.10 dan 3.11, verifikasi login dan izin empat akun, alur inventory/HR/finance, email approval, PDF, restart PR, migrasi, dan operasi database. Catat hasil CI GitHub. Pemeriksaan port 8060 harus mencakup UI, health lokal, penolakan tanpa autentikasi, dan alur sah dengan autentikasi.
6. Deploy hanya commit yang lulus review dan CI ke `/home/jds2/AutoRestock-Agent-Dap`; laporkan SHA dan diff server, status proses 8060, hasil smoke check, dan rollback path. Hindari perubahan pada folder/port lain.

## Instruksi singkat siap kirim ke Antigravity

> Jalankan rencana di `ANTIGRAVITY_EXECUTION_PLAN.md` sebagai executor proyek AutoRestock-Agent. Prioritaskan P0, gunakan commit kecil, dan kirim diff serta bukti ke Codex untuk review sebelum deploy. Pertahankan data server yang sudah berubah dan batasi perubahan ke `/home/jds2/AutoRestock-Agent-Dap` serta port 8060. Pengguna meminta `admin123` untuk admin dan `user123` untuk user; implementasikan hanya lewat perubahan hash akun yang benar, pencabutan sesi lama, dan pembatasan akses lingkungan uji. Jangan menganggap file `rotated-credentials.txt` sebagai sumber autentikasi. Jangan menghapus kandidat dead code tanpa memeriksa pemanggil API/UI/operasional.
