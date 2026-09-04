# Implementation Plan - Person 1 (Frontend, Admin UI & Workflow Scoping)

> **Role**: Fullstack Frontend & Admin Orchestration Engineer  
> **PIC**: Teman Anda (Device Teman Anda)  
> **Tool**: Antigravity IDE  
> **Git Branch**: `feature/admin-tools-ui`  
> **Starting Point**: Repository `AutoRestock-Agent` (State Baseline)

---

## 🎯 Fokus & Tanggung Jawab Utama

Anda bertanggung jawab atas antarmuka pengguna (Admin & Dashboard), pendaftaran dan visualisasi tools, serta pengelolaan alokasi workflow per user:
1. **Menu Tools Explorer di Admin Page** (Kebutuhan #1): Membuat tab/menu baru di `admin.html` untuk melihat daftar tools yang tersedia, fungsinya, parameter input, serta kategori building block.
2. **User-Scoped Workflow UI & Admin API** (Kebutuhan #2 - Frontend & Admin Management): Menambahkan kontrol penentuan target user/tenant saat membuat atau mengedit workflow, serta menampilkan kepemilikan workflow di daftar UI untuk 3 domain industri nyata:
   - **User A (TENANT_A)**: Manufaktur Komponen Elektronika (SAP/ERP)
   - **User B (TENANT_B)**: Farmasi & F&B / Kimia (WMS Expiry Batch)
   - **User C (TENANT_C)**: Logistik Armada & Sparepart Alat Berat (CMMS Fleet)
3. **Handling Safe Fallback di Dashboard Copilot** (Kebutuhan #4 - Frontend): Memastikan respon out-of-scope/unrecognized intent dari backend (yang dibuat Person 2) ditampilkan secara ramah, informatif, dan edukatif kepada pengguna (tidak error dan tidak halu).

---

## 📂 File yang Dimodifikasi & Dimiliki oleh Person 1

Untuk mencegah **git merge conflict** dengan Person 2, Anda **HANYA** akan memodifikasi file-file frontend dan admin API berikut:
- [MODIFY] [`web/static/admin.html`](file:///d:/Code/AutoRestock-Agent/web/static/admin.html)
- [MODIFY] [`api/routers/auth_routes.py`](file:///d:/Code/AutoRestock-Agent/api/routers/auth_routes.py)
- [MODIFY] [`web/static/js/dashboard.js`](file:///d:/Code/AutoRestock-Agent/web/static/js/dashboard.js)
- [MODIFY] [`web/static/css/dashboard.css`](file:///d:/Code/AutoRestock-Agent/web/static/css/dashboard.css) *(opsional jika perlu style tambahan)*

> [!NOTE]
> File core agent (`router.py`, `json_executor.py`), migrasi database nyata (`seed_data.py`, `schema_adapters.py`), dan MCP tools (`mcp_server/tools.py`) dikerjakan oleh **Person 2**. Anda tidak perlu menyentuh file-file tersebut.

---

## 📋 Langkah-Langkah Pengerjaan (Step-by-Step)

### Tahap 1: Menu Lihat Tools di Admin Page (`admin.html`)

#### 1.1 Tambahkan Tab Navigasi "Tools Registry" di Header
Buka [`web/static/admin.html`](file:///d:/Code/AutoRestock-Agent/web/static/admin.html):
- Cari elemen `.nav-tabs` (sekitar line 695).
- Tambahkan tombol tab ketiga:
```html
<button class="tab-btn" id="tabToolsBtn" onclick="switchAdminTab('tools')">
  <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
  <span>Agent Tools Registry</span>
</button>
```

#### 1.2 Buat Section Content "Agent Tools Registry" di Main Container
Di dalam `<main class="container">`, tambahkan container `#sectionTools` (default `display: none;`):
- Buat header kartu ringkasan jumlah tools, filter pencarian berdasarkan nama dan kategori (Building Blocks: *Reasoning & Validation*, *Inventory Operations*, *Notification & Dispatch*, *Document Generation*).
- Buat card grid interaktif yang menampilkan:
  - **Tool Identifier** (contoh: `inventory.get_low_stock_products`)
  - **Kategori / Building Block**
  - **Deskripsi Fungsi**
  - **Parameter Input / Payload Schema**
  - **Contoh Penggunaan dalam Workflow**

#### 1.3 Implementasikan Logika JS untuk Fetch Tools
Di bagian script `admin.html`:
- Perbarui fungsi `switchAdminTab(tabName)` untuk mendukung `'tools'`.
- Buat fungsi `loadAgentTools()`:
```javascript
async function loadAgentTools() {
  const container = document.getElementById('toolsListContainer');
  try {
    const res = await fetch('/api/agent/tools', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await res.json();
    renderToolsGrid(data.available_tools || []);
  } catch (err) {
    console.error("Gagal memuat tools:", err);
  }
}
```

---

### Tahap 2: Workflow Spesifik per User (Frontend & Admin API)

#### 2.1 Tambah Input Pemilihan Target User pada Form Workflow
Di form builder workflow (`#sectionWorkflows` di `admin.html`):
- Tambahkan field dropdown `<select id="wfTenantId" class="form-input">`:
  - `ALL` — Global (Bisa Diakses Semua User)
  - `TENANT_A` — Khusus User A (Manufaktur Elektronika - SAP/ERP)
  - `TENANT_B` — Khusus User B (Farmasi & F&B - WMS Batch)
  - `TENANT_C` — Khusus User C (Logistik Armada & Sparepart - CMMS)
- Letakkan di baris form input Nama Workflow dan Deskripsi.

#### 2.2 Update Endpoint Admin Workflow di `api/routers/auth_routes.py`
Buka [`api/routers/auth_routes.py`](file:///d:/Code/AutoRestock-Agent/api/routers/auth_routes.py):
- Perbarui Pydantic Model `CreateWorkflowRequest`:
```python
class CreateWorkflowRequest(BaseModel):
    name: str
    description: str
    business_instruction: str
    tenant_id: str = "ALL"  # ALL, TENANT_A, TENANT_B, TENANT_C
```
- Update `create_workflow`:
```python
@router.post("/admin/workflows")
async def create_workflow(req: CreateWorkflowRequest, admin: TokenData = Depends(get_current_admin)):
    ...
    conn.execute(
        "INSERT INTO workflows (id, name, description, business_instruction, compiled_json, tenant_id) VALUES (?, ?, ?, ?, ?, ?)", 
        [wf_id, req.name, req.description, req.business_instruction, json.dumps(compiled_json), req.tenant_id]
    )
    ...
```
- Update `edit_workflow` agar menyimpan `tenant_id`:
```python
@router.put("/admin/workflows/{wf_id}")
async def edit_workflow(wf_id: str, req: CreateWorkflowRequest, admin: TokenData = Depends(get_current_admin)):
    ...
    conn.execute(
        "UPDATE workflows SET name = ?, description = ?, business_instruction = ?, compiled_json = ?, tenant_id = ? WHERE id = ?", 
        [req.name, req.description, req.business_instruction, json.dumps(compiled_json), req.tenant_id, wf_id]
    )
    ...
```
- Update query `get_workflows` agar mengembalikan kolom `tenant_id`.

#### 2.3 Update Tampilan Card Workflow di `admin.html`
- Pada fungsi `loadWorkflows()`, tambahkan badge status kepemilikan tenant:
  - Jika `tenant_id === 'ALL'`: Badge abu-abu/biru `"GLOBAL (ALL USERS)"`.
  - Jika `tenant_id === 'TENANT_A'`: Badge khusus `"KHUSUS: USER A (ELEKTRONIK)"`.
  - Jika `tenant_id === 'TENANT_B'`: Badge khusus `"KHUSUS: USER B (FARMASI/WMS)"`.
  - Jika `tenant_id === 'TENANT_C'`: Badge khusus `"KHUSUS: USER C (ARMADA/ALAT BERAT)"`.
- Pastikan tombol edit memuat kembali nilai `tenant_id` ke form.

---

### Tahap 3: Visualisasi Fallback / Anti-Halu di Dashboard User (`dashboard.js`)

#### 3.1 Tangani Respon "Unrecognized Intent"
Buka [`web/static/js/dashboard.js`](file:///d:/Code/AutoRestock-Agent/web/static/js/dashboard.js):
- Cari fungsi yang menangani respon `/api/agent/custom-prompt` (sekitar line 715).
- Saat `data.action_type === 'unrecognized_intent'`:
  - Render bubble pesan peringatan yang elegan:
    - Judul: *"Instruksi Tidak Dikenali dalam Alur Kerja Akun Anda"*
    - Tampilkan daftar workflow yang diizinkan untuk akun user tersebut (`data.available_workflows`).
    - Tampilkan tombol bantuan atau saran instruksi yang valid sesuai domain akun.
  - Jangan buat tabel order kosong atau memicu pembuatan PR palsu.

---

## 🧪 Rencana Verifikasi & Testing (Person 1)

1. **Uji Menu Tools**:
   - Login sebagai `admin` / `admin123`.
   - Klik tab **Agent Tools Registry**. Pastikan seluruh tools muncul beserta deskripsi dan kategorinya.
   - Coba fitur filter/search tool.
2. **Uji Pembatasan Workflow**:
   - Buat workflow baru dengan memilih target **User A (TENANT_A)**.
   - Pastikan badge pada card bertuliskan `"KHUSUS: USER A (ELEKTRONIK)"`.
   - Edit workflow dan ubah targetnya ke **User B (TENANT_B)**. Pastikan perubahan tersimpan.
3. **Uji Dashboard Fallback**:
   - Login sebagai `usera` / `user123`.
   - Ketikkan prompt di luar konteks (contoh: *"siapkan tiket pesawat ke Bali"*).
   - Pastikan UI menampilkan respon aman (panduan workflow yang tersedia untuk User A) dan **tidak** menghasilkan PR atau mengeksekusi workflow lain.
