# Implementation Plan - Person 2 (Backend, Real Schemas & AI Guardrails)

> **Role**: Core AI & Data Engine Backend Engineer  
> **PIC**: Anda (Device Anda)  
> **Tool**: Antigravity IDE  
> **Git Branch**: `feature/real-database-engine`  
> **Starting Point**: Repository `AutoRestock-Agent` (State Baseline)

---

## 🎯 Fokus & Tanggung Jawab Utama

Anda bertanggung jawab atas core backend, integrasi database nyata dengan 3 skema berbeda per user/industri, layer adaptasi data (*Schema Adapter*), router semantic yang ketat, dan mekanisme anti-halusinasi:
1. **Migrasi Database & 3 Skema Heterogen Nyata** (Kebutuhan #3): Menghapus ketergantungan pada dummy table tunggal `items` dan membuat 3 tabel data nyata dengan nama kolom, variabel, dan karakteristik industri yang benar-benar berbeda untuk User A, User B, dan User C.
2. **Schema Adapter Layer** (`database/schema_adapters.py`): Membangun adapter yang memetakan kolom-kolom heterogen dari ketiga tabel ke bentuk entitas terstandar (*Standard Procurement Entity*) yang dibutuhkan oleh MCP Tools dan JSON Execution Engine.
3. **Strict Semantic Router & Anti-Halusinasi** (Kebutuhan #4): Memperbaiki `agents/router.py` agar **tidak sembarangan** memilih workflow secara acak/default saat prompt user tidak cocok. Jika prompt di luar alur kerja yang diizinkan untuk user tersebut, sistem harus menolak dengan aman (*graceful out-of-scope rejection*).
4. **Isolasi Workflow per User pada Backend** (Kebutuhan #2 - Backend & Routing): Memastikan Semantic Router dan JSON Executor hanya memuat, mencocokkan, dan mengeksekusi workflow yang diizinkan untuk `tenant_id` user yang sedang aktif.

---

## 📂 File yang Dimodifikasi & Dimiliki oleh Person 2

Untuk mencegah **git merge conflict** dengan Person 1, Anda **HANYA** akan memodifikasi file-file backend berikut:
- [MODIFY] [`database/seed_data.py`](file:///d:/Code/AutoRestock-Agent/database/seed_data.py) (migrasi DDL 3 tabel nyata + kolom `tenant_id` pada tabel `workflows`)
- [NEW] [`database/schema_adapters.py`](file:///d:/Code/AutoRestock-Agent/database/schema_adapters.py) (layer penerjemah skema heterogen)
- [MODIFY] [`mcp_server/tools.py`](file:///d:/Code/AutoRestock-Agent/mcp_server/tools.py) (arahkan query ke TenantSchemaAdapter)
- [MODIFY] [`agents/router.py`](file:///d:/Code/AutoRestock-Agent/agents/router.py) (filter tenant & eliminasi fallback asal pilih)
- [MODIFY] [`agents/json_executor.py`](file:///d:/Code/AutoRestock-Agent/agents/json_executor.py) (eksekusi berbasis adapter skema user)
- [MODIFY] [`api/routers/agent_routes.py`](file:///d:/Code/AutoRestock-Agent/api/routers/agent_routes.py) (handling graceful fallback out-of-scope)

> [!NOTE]
> File antarmuka frontend (`admin.html`, `dashboard.js`) dan API admin workflow (`auth_routes.py`) dikerjakan oleh **Person 1**. Anda tidak perlu menyentuh file-file tersebut.

---

## 🏭 Spesifikasi 3 Skema Database Nyata (Real-World Schemas)

Ketiga user memiliki jenis bisnis, skema tabel, dan struktur kolom yang sangat berbeda nyata:

### 1. User A: Manufaktur Komponen Elektronika (Format SAP/ERP)
* **Tabel**: `mfg_electronics_inventory`
* **Karakteristik**: Komponen chip/SMD, bin rak lini perakitan, dan tipe packaging reel/tray pabrik.
* **Struktur Kolom**:
  - `part_number` (VARCHAR, PK) — Contoh: `STM32F401RE`, `ESP32-WROOM-32D`, `AMS1117-3.3`
  - `component_name` (VARCHAR) — Contoh: `Microcontroller ARM Cortex-M4`, `Wi-Fi Bluetooth Module`
  - `package_type` (VARCHAR) — Contoh: `Reel 5000pcs`, `Tray 250pcs`, `Tube 50pcs`
  - `bin_location` (VARCHAR) — Contoh: `BIN-A1-04`, `BIN-B2-12`
  - `qty_on_hand` (INTEGER) — Stok fisik di pabrik
  - `safety_reorder_point` (INTEGER) — Batas minimum sebelum restock
  - `max_bin_capacity` (INTEGER) — Batas tampung rak
  - `daily_consumption_burn` (FLOAT) — Konsumsi harian lini perakitan
  - `vendor_lead_days` (INTEGER) — Lead time pabrikan
  - `unit_cost_idr` (FLOAT) — Harga pokok per part

### 2. User B: Farmasi & F&B / Kimia (Format Warehouse Management System / WMS)
* **Tabel**: `pharma_fmcg_inventory`
* **Karakteristik**: Batch lot produksi, tanggal kedaluwarsa (*expiry date*), dan kecepatan jual harian.
* **Struktur Kolom**:
  - `sku_code` (VARCHAR, PK) — Contoh: `SKU-ALCOHOL-99`, `SKU-PARACETAMOL-500`, `SKU-AMOXICILLIN`
  - `product_label` (VARCHAR) — Contoh: `Industrial Isopropyl Alcohol 99% 5L`, `Paracetamol 500mg Box`
  - `batch_lot_number` (VARCHAR) — Contoh: `LOT-202603A`, `LOT-202511B`
  - `expiry_date` (DATE / VARCHAR) — Contoh: `2026-11-20`, `2027-12-31`
  - `stock_warehouse` (INTEGER) — Jumlah stok di gudang farmasi
  - `min_reorder_level` (INTEGER) — Titik reorder darurat
  - `sales_velocity_per_day` (FLOAT) — Kecepatan keluar barang per hari
  - `procurement_sla_days` (INTEGER) — Waktu kirim prinsipal farmasi
  - `uom_unit` (VARCHAR) — Contoh: `Canister`, `Box 100 Strip`, `Botol 500ml`
  - `selling_price_idr` (FLOAT) — Harga beli per satuan

### 3. User C: Logistik Armada & Sparepart Alat Berat (Format CMMS / Fleet Maintenance)
* **Tabel**: `fleet_maintenance_parts`
* **Karakteristik**: Suku cadang alat berat/truk, kompatibilitas armada, zona bengkel workshop, dan tingkat keausan.
* **Struktur Kolom**:
  - `asset_tag_id` (VARCHAR, PK) — Contoh: `FLT-BRAKE-HINO`, `FLT-HYD-KOMATSU`, `FLT-OIL-CAT`
  - `sparepart_name` (VARCHAR) — Contoh: `Brake Shoe Set Dump Truck`, `Hydraulic Seal Kit PC200`
  - `equipment_compatibility` (VARCHAR) — Contoh: `Dump Truck Hino 500`, `Excavator Komatsu PC200`
  - `workshop_bay_zone` (VARCHAR) — Contoh: `ZONA-HEAVY-01`, `RAK-HIDROLIK-B`
  - `available_qty` (INTEGER) — Suku cadang tersedia di bengkel
  - `critical_safety_threshold` (INTEGER) — Batas kritis keselamatan armada
  - `wear_rate_per_month` (FLOAT) — Estimasi aus/ganti per bulan
  - `supplier_eta_days` (INTEGER) — Lead time distributor suku cadang
  - `measure_metric` (VARCHAR) — Contoh: `Set`, `Unit`, `Pcs`
  - `replacement_cost_idr` (FLOAT) — Biaya suku cadang

---

## 📋 Langkah-Langkah Pengerjaan (Step-by-Step)

### Tahap 1: Migrasi Database & Seeding Data Nyata

Buka [`database/seed_data.py`](file:///d:/Code/AutoRestock-Agent/database/seed_data.py):
1. **Tambahkan kolom `tenant_id` ke tabel `workflows`**:
   ```sql
   CREATE TABLE IF NOT EXISTS workflows (
       id VARCHAR PRIMARY KEY,
       name VARCHAR NOT NULL,
       description TEXT,
       business_instruction TEXT NOT NULL,
       compiled_json TEXT NOT NULL,
       tenant_id VARCHAR DEFAULT 'ALL'
   );
   ```
2. **Buat DDL untuk 3 Tabel Data Nyata**:
   Buat tabel `mfg_electronics_inventory`, `pharma_fmcg_inventory`, dan `fleet_maintenance_parts`.
3. **Isi Seed Data Nyata** (minimal 8–10 item realistis per tabel dengan status stok aman dan stok kritis).
4. **Seed Default Workflows Khusus Tiap User**:
   - `WF-A01` (User A): *"Auto Restock Komponen Assembly Line Elektronik (Berdasarkan safety_reorder_point & bin_location)"* -> `tenant_id = 'TENANT_A'`
   - `WF-B01` (User B): *"Audit Kedaluwarsa (<90 hari) & Restock Batch Farmasi WMS"* -> `tenant_id = 'TENANT_B'`
   - `WF-C01` (User C): *"Pengadaan Suku Cadang Kritis Armada Alat Berat Bengkel"* -> `tenant_id = 'TENANT_C'`

---

### Tahap 2: Buat Schema Adapter Layer (`database/schema_adapters.py`)

Buat file baru [`database/schema_adapters.py`](file:///d:/Code/AutoRestock-Agent/database/schema_adapters.py):
```python
from database.db import get_db_connection

class TenantSchemaAdapter:
    """
    Abstraksi yang menerjemahkan struktur kolom unik dari 3 skema database berbeda
    menjadi dictionary seragam (Standard Procurement Entity).
    """
    TENANT_CONFIG = {
        "TENANT_A": {
            "table": "mfg_electronics_inventory",
            "col_id": "part_number",
            "col_name": "component_name",
            "col_stock": "qty_on_hand",
            "col_min": "safety_reorder_point",
            "col_max": "max_bin_capacity",
            "col_usage": "daily_consumption_burn",
            "col_lead": "vendor_lead_days",
            "col_unit": "package_type",
            "col_price": "unit_cost_idr"
        },
        "TENANT_B": {
            "table": "pharma_fmcg_inventory",
            "col_id": "sku_code",
            "col_name": "product_label",
            "col_stock": "stock_warehouse",
            "col_min": "min_reorder_level",
            "col_max": "min_reorder_level * 3",
            "col_usage": "sales_velocity_per_day",
            "col_lead": "procurement_sla_days",
            "col_unit": "uom_unit",
            "col_price": "selling_price_idr",
            "extra_filter": "expiry_date"
        },
        "TENANT_C": {
            "table": "fleet_maintenance_parts",
            "col_id": "asset_tag_id",
            "col_name": "sparepart_name",
            "col_stock": "available_qty",
            "col_min": "critical_safety_threshold",
            "col_max": "critical_safety_threshold * 4",
            "col_usage": "wear_rate_per_month / 30.0",
            "col_lead": "supplier_eta_days",
            "col_unit": "measure_metric",
            "col_price": "replacement_cost_idr",
            "extra_filter": "equipment_compatibility"
        }
    }

    @classmethod
    def get_low_stock_items(cls, tenant_id: str) -> list[dict]:
        cfg = cls.TENANT_CONFIG.get(tenant_id)
        if not cfg:
            return []
        
        conn = get_db_connection(read_only=True)
        query = f"""
            SELECT {cfg['col_id']} AS item_id,
                   {cfg['col_name']} AS name,
                   {cfg['col_stock']} AS current_stock,
                   {cfg['col_min']} AS min_threshold,
                   {cfg['col_usage']} AS avg_daily_usage,
                   {cfg['col_lead']} AS lead_time_days,
                   {cfg['col_unit']} AS unit,
                   {cfg['col_price']} AS unit_price
            FROM {cfg['table']}
            WHERE {cfg['col_stock']} <= {cfg['col_min']}
            ORDER BY ({cfg['col_min']} - {cfg['col_stock']}) DESC;
        """
        rows = conn.execute(query).fetchall()
        columns = [d[0] for d in conn.description]
        conn.close()

        items = []
        for r in rows:
            d = dict(zip(columns, r))
            d["reorder_qty"] = max(d["min_threshold"] * 2 - d["current_stock"], 1)
            items.append(d)
        return items

    @classmethod
    def get_all_items(cls, tenant_id: str) -> list[dict]:
        ...
```

Hubungkan `mcp_server/tools.py` agar memanggil `TenantSchemaAdapter.get_low_stock_items(tenant_id)` dan `TenantSchemaAdapter.get_all_items(tenant_id)`.

---

### Tahap 3: Perombakan Semantic Router & Anti-Halusinasi (`agents/router.py`)

Buka [`agents/router.py`](file:///d:/Code/AutoRestock-Agent/agents/router.py):
1. **Filter Workflow Berdasarkan Tenant Pengguna**:
   ```python
   conn = get_db_connection(read_only=True)
   workflows = conn.execute("""
       SELECT id, name, description, tenant_id 
       FROM workflows 
       WHERE tenant_id = ? OR tenant_id = 'ALL'
   """, [tenant_id]).fetchall()
   conn.close()
   ```
2. **Perketat System Prompt**:
   Instruksikan model untuk mengembalikan `"workflow_id": null` jika prompt pengguna tidak relevan dengan alur kerja yang terdaftar di daftar di atas.
3. **Hapus Hardcoded Fallback yang Menyebabkan Halu**:
   Hapus line 156–164:
   ```python
   # HAPUS BARIS INI:
   # if not matched_wf_id and len(workflows) > 0:
   #     matched_wf_id = workflows[0][0]
   ```
   Ganti dengan:
   ```python
   if not matched_wf_id:
       return {
           "workflow_id": None,
           "send_email": False,
           "threshold_updates": [],
           "target_item_name": None
       }
   ```

---

### Tahap 4: Handling Respon Out-of-Scope di `agent_routes.py`

Buka [`api/routers/agent_routes.py`](file:///d:/Code/AutoRestock-Agent/api/routers/agent_routes.py) pada fungsi `execute_custom_prompt_workflow` (line 295):
1. Panggil router:
   ```python
   route_result = await SemanticRouter.route_prompt(request.prompt, current_user.tenant_id)
   workflow_id = route_result.get("workflow_id")
   ```
2. **Jika `workflow_id is None`**:
   Tarik daftar alur kerja yang tersedia untuk user tersebut, lalu kembalikan payload penolakan aman:
   ```python
   if not workflow_id:
       conn = get_db_connection(read_only=True)
       user_wfs = conn.execute(
           "SELECT id, name, description FROM workflows WHERE tenant_id = ? OR tenant_id = 'ALL'",
           [current_user.tenant_id]
       ).fetchall()
       conn.close()

       wf_list_text = "\n".join([f"• **{r[1]}**: {r[2]}" for r in user_wfs])
       return {
           "parsed_intent": {"workflow_id": None},
           "action_type": "unrecognized_intent",
           "message": (
               f"Instruksi yang Anda masukkan belum dapat dipetakan ke alur kerja aktif akun Anda.\n\n"
               f"Alur kerja yang tersedia untuk peran Anda:\n{wf_list_text}\n\n"
               f"Silakan sesuaikan instruksi Anda dengan alur kerja di atas."
           ),
           "available_workflows": [{"id": r[0], "name": r[1]} for r in user_wfs],
           "generated_prs": [],
           "affected_items": [],
           "execution_steps": []
       }
   ```
3. **Otorisasi Ketat**:
   Jika user mencoba memanggil ID workflow milik tenant lain secara langsung, kembalikan `HTTPException(status_code=403, detail="Akses workflow tidak diizinkan.")`.

---

## 🧪 Rencana Verifikasi & Testing (Person 2)

1. **Test Migrasi Database**:
   - Jalankan `python database/seed_data.py`.
   - Pastikan tabel `mfg_electronics_inventory`, `pharma_fmcg_inventory`, dan `fleet_maintenance_parts` terbuat dan terisi data.
2. **Test Schema Adapter**:
   - Jalankan script tes kecil untuk memanggil `TenantSchemaAdapter.get_low_stock_items("TENANT_A")` -> Harus mengembalikan komponen elektronik dari kolom `part_number` & `qty_on_hand`.
   - Panggil untuk `TENANT_B` -> Harus mengembalikan obat/kimia dari kolom `sku_code` & `stock_warehouse`.
   - Panggil untuk `TENANT_C` -> Harus mengembalikan suku cadang armada dari `asset_tag_id` & `available_qty`.
3. **Test Anti-Halusinasi**:
   - Kirim prompt out-of-scope: *"buatkan saya resep nasi goreng"* atau *"jadwalkan meeting besok"*.
   - Verifikasi bahwa sistem **TIDAK** menjalankan workflow restock atau menerbitkan PR, melainkan mengembalikan `action_type: "unrecognized_intent"` dengan daftar workflow yang relevan untuk akun tersebut.
