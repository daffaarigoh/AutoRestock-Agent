import json
import re

from core.llm_client import ModelGateway

class WorkflowCompiler:
    @classmethod
    async def compile_business_instruction(cls, name: str, instruction: str) -> dict:
        """
        Translates a natural language business instruction into a structured JSON workflow
        using the 4 Core Agentic Building Blocks.
        """
        system_prompt = """You are a Workflow Compiler for an Enterprise Agentic Inventory & Restock System (PT Bali Towerindo Sentra Tbk).
Convert the user's natural language business instruction into a strict, structured JSON workflow execution definition.

You must build the execution pipeline using the official Agentic Building Blocks:

1. REASONING & VALIDATION (Agent Tasks):
   - {"type": "agent", "task": "agent.reason_and_validate"} -> Validates mandatory parameters (e.g. 7 required attributes for new item registration), verifies business rules, or evaluates constraints.
   - {"type": "agent", "task": "calculate_reorder_quantity"} -> Calculates restock needs, EOQ, safety stock, and supplier budget matching.

2. INVENTORY & DATABASE OPERATIONS (Tools):
   - {"type": "tool", "tool": "inventory.register_product"} -> Registers and inserts new product items into the active tenant's inventory database.
   - {"type": "tool", "tool": "inventory.get_low_stock_products"} -> Queries products below minimum threshold.
   - {"type": "tool", "tool": "inventory.get_all_products"} -> Queries all products for warehouse audits.
   - {"type": "tool", "tool": "inventory.check_specific_stock"} -> Queries specific product stock level.
   - {"type": "tool", "tool": "inventory.update_threshold"} -> Updates product safety threshold.
   - {"type": "tool", "tool": "inventory.crud_record"} -> Generic database record operations.
   - {"type": "tool", "tool": "po.query_orders"} -> Queries Purchase Orders (PO) filtered by status ("ACTIVE", "IN_TRANSIT", "PENDING_APPROVAL", "APPROVED").
   - {"type": "tool", "tool": "po.approve"} -> Approves a Purchase Order and updates its status to "APPROVED".
   - {"type": "tool", "tool": "hr.submit_leave_request"} -> Records an employee leave application into the DuckDB database.
   - {"type": "tool", "tool": "hr.query_pending_leaves"} -> Queries all employee leave applications with PENDING_APPROVAL status from DuckDB for review and dispatch.
   - {"type": "tool", "tool": "finance.draft_client_onboarding"} -> Prepares a draft onboarding for a new telecom client operator and tower lease contract (MLA) with PENDING_APPROVAL status.
   - {"type": "tool", "tool": "finance.approve_client_onboarding"} -> Approves an onboarding request and activates client, contract, and invoice.
   - {"type": "tool", "tool": "finance.audit_client_onboardings"} -> Queries all pending client onboarding and lease contract requests.
   - {"type": "tool", "tool": "finance.revenue_report"} -> Generates operator revenue and billed accounts receivable report.
   - {"type": "tool", "tool": "finance.opex_audit"} -> Audits operational expenses (PLN electricity, land lease, fuel).
   - {"type": "tool", "tool": "finance.cashflow_summary"} -> Calculates net operational cash flow.

3. NOTIFICATION & DISPATCH (Tools):
   - {"type": "tool", "tool": "notification.dispatch"} or {"type": "tool", "tool": "notification.send_email"} -> Sends email notifications, alert dispatches, or operational reports.

4. DOCUMENT GENERATION (Tools):
   - {"type": "tool", "tool": "docgen.compile"} -> Generates Purchase Requisition (PR) draf documents and Typst PDFs.
   - {"type": "tool", "tool": "docgen.compile_po"} -> Compiles official Purchase Order (PO) PDF documents with PT Bali Towerindo Sentra Tbk letterhead.
   - {"type": "tool", "tool": "docgen.compile_leave_pdf"} -> Compiles official Employee Leave Request PDF documents with PT Bali Towerindo Sentra Tbk letterhead.

CRITICAL RULES:
- DO NOT use MongoDB syntax (such as $in, collection, projection). The database is DuckDB SQL.
- DO NOT use bracket variables like {{step_2_output}}. Data is passed automatically through the engine context.
- Use ONLY the tools and tasks listed above.
- For End-to-End procurement / restock pipelines (from stock inspection to PR / PO draft and email notification), use the sequence: inventory.get_low_stock_products -> calculate_reorder_quantity -> docgen.compile -> notification.dispatch. Do NOT select inventory.update_threshold unless the instruction explicitly asks to re-configure or edit the threshold limit of an item.

Output format MUST be strictly valid JSON:
{
  "workflow": "<workflow_name_slug>",
  "version": 1,
  "steps": [
    ... // Array of step objects
  ],
  "example_prompts": [
    "Contoh kalimat pertanyaan atau instruksi chat bahasa Indonesia 1",
    "Contoh kalimat pertanyaan atau instruksi chat bahasa Indonesia 2"
  ]
}
Generate 2 realistic natural language question prompts in Indonesian that an operator or manager would type in chat to trigger this workflow.
Do not output any markdown formatting or extra commentary outside the JSON.
"""
        gateway = ModelGateway()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Workflow Name: {name}\n\nInstruction:\n{instruction}"}
        ]
        
        try:
            response_str = await gateway.chat_completion("nemotron-35", messages, temperature=0.1, response_format_json=True)
            json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if json_match:
                response_str = json_match.group(0)
            parsed = json.loads(response_str)
            if parsed.get("steps") and len(parsed["steps"]) > 0:
                if not parsed.get("example_prompts") or not isinstance(parsed.get("example_prompts"), list) or len(parsed["example_prompts"]) == 0:
                    parsed["example_prompts"] = cls.generate_heuristic_examples(name, instruction)
                return parsed
        except Exception as e:
            print(f"[WORKFLOW COMPILER] LLM compilation exception: {e}. Utilizing deterministic heuristic compiler.")

        # Heuristic compiler fallback ensuring high-quality standard compilation
        text_lower = f"{name} {instruction}".lower()
        slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        
        steps = []
        # Case 1: Product Registration & Validation
        if any(k in text_lower for k in ["daftar", "pendaftaran", "tambah barang", "tambah material", "register", "registrasi", "validasi", "catat item", "material baru", "item baru", "sku baru", "produk baru"]):
            steps.append({"type": "agent", "task": "agent.reason_and_validate"})
            steps.append({"type": "tool", "tool": "inventory.register_product"})
            if "email" in text_lower or "notifikasi" in text_lower or "lapor" in text_lower:
                steps.append({"type": "tool", "tool": "notification.dispatch"})
        
        # Case 2: Standard Restock / Procurement (End-to-End) & PR-to-PO Pipeline (HIGHEST PRIORITY OVER THRESHOLD)
        elif any(k in text_lower for k in ["restock", "pengadaan", "reorder", "pipeline", "pr-to-po", "pr to po", "draf pr", "draft pr", "purchase requisition", "beli", "pesan barang", "kritis", "menipis", "habis"]):
            steps.append({"type": "tool", "tool": "inventory.get_low_stock_products"})
            steps.append({"type": "agent", "task": "calculate_reorder_quantity"})
            steps.append({"type": "tool", "tool": "docgen.compile"})
            steps.append({"type": "tool", "tool": "notification.dispatch"})

        # Case 3: Explicit Update Threshold Action (hanya jika ada kata kerja ubah/update/ganti batas)
        elif any(k in text_lower for k in ["update threshold", "ubah threshold", "ganti threshold", "atur threshold", "set threshold", "ubah ambang", "update batas", "ubah batas", "atur batas", "set batas"]):
            steps.append({"type": "tool", "tool": "inventory.update_threshold"})
            if "email" in text_lower or "notifikasi" in text_lower:
                steps.append({"type": "tool", "tool": "notification.dispatch"})
                
        # Case 4: Warehouse Audit
        elif any(k in text_lower for k in ["audit", "seluruh gudang", "semua barang"]):
            steps.append({"type": "tool", "tool": "inventory.get_all_products"})
            steps.append({"type": "tool", "tool": "notification.dispatch"})
            
        # Case 5: Goods Receipt / Penerimaan Fisik Barang
        elif any(k in text_lower for k in ["penerimaan", "kedatangan", "tiba", "sampai", "delivered"]):
            steps.append({"type": "tool", "tool": "inventory.check_specific_stock"})
            steps.append({"type": "tool", "tool": "inventory.crud_record"})
            steps.append({"type": "tool", "tool": "notification.dispatch"})

        # Case 6: Purchase Order (PO) Tracking, Approval, and PDF Document Generation
        elif any(k in text_lower for k in ["purchase order", "po", "surat pesanan", "berkas po", "monitoring po", "cetak po"]):
            if any(k in text_lower for k in ["setujui", "approve", "persetujuan"]):
                steps.append({"type": "tool", "tool": "po.query_orders"})
                steps.append({"type": "tool", "tool": "po.approve"})
                steps.append({"type": "tool", "tool": "docgen.compile_po"})
            else:
                steps.append({"type": "tool", "tool": "po.query_orders"})
                steps.append({"type": "tool", "tool": "docgen.compile_po"})
            if "email" in text_lower or "notifikasi" in text_lower:
                steps.append({"type": "tool", "tool": "notification.dispatch"})

        # Case 7: Audit / Query Pending Employee Leaves & HR Notification
        elif any(k in text_lower for k in ["pending", "status cuti", "cek cuti", "audit cuti", "rekap cuti", "belum disetujui", "daftar cuti"]):
            steps.append({"type": "tool", "tool": "hr.query_pending_leaves"})
            if any(k in text_lower for k in ["email", "notifikasi", "kirim", "dispatch", "persetujuan", "approve"]):
                from agents.router import extract_recipient_email
                extracted = extract_recipient_email(instruction)
                disp_step = {"type": "tool", "tool": "notification.dispatch"}
                if extracted:
                    disp_step["params"] = {"recipient_email": extracted}
                steps.append(disp_step)

        # Case 8: Employee Leave Request, PDF Compilation & HR Notification
        elif any(k in text_lower for k in ["cuti", "leave", "permohonan cuti", "pengajuan cuti", "izin cuti"]):
            steps.append({"type": "tool", "tool": "hr.submit_leave_request"})
            steps.append({"type": "tool", "tool": "docgen.compile_leave_pdf"})
            if any(k in text_lower for k in ["email", "notifikasi", "kirim", "dispatch", "surat"]):
                from agents.router import extract_recipient_email
                extracted = extract_recipient_email(instruction)
                disp_step = {"type": "tool", "tool": "notification.dispatch"}
                if extracted:
                    disp_step["params"] = {"recipient_email": extracted}
                steps.append(disp_step)

        # Case 9: Telecom Client Onboarding & Tower Lease Contract (Approval Workflow)
        elif any(k in text_lower for k in ["klien baru", "operator baru", "daftar operator", "sewa baru", "kontrak baru", "onboarding", "daftarkan operator", "sewa menara baru", "draft kontrak"]):
            steps.append({"type": "tool", "tool": "finance.draft_client_onboarding"})
            steps.append({"type": "tool", "tool": "notification.send_email"})

        # Case 10: Specific stock check
        elif any(k in text_lower for k in ["spesifik", "cek stok"]):
            steps.append({"type": "tool", "tool": "inventory.check_specific_stock"})

        # Fallback default: Safe general informational agent task (never default to Restock PR)
        else:
            steps.append({
                "type": "agent",
                "task": "agent.reason_and_validate",
                "params": {"instruction": instruction}
            })
            
        return {
            "workflow": slug or "custom_workflow",
            "version": 1,
            "steps": steps,
            "example_prompts": cls.generate_heuristic_examples(name, instruction)
        }

    @classmethod
    def generate_heuristic_examples(cls, name: str, instruction: str) -> list[str]:
        """Generates 2 clean natural language prompt examples based on name and instruction."""
        clean_name = re.sub(r'^(?:alur|workflow|pipeline|proses)\s+', '', name, flags=re.IGNORECASE).strip()
        text_lower = f"{name} {instruction}".lower()
        
        # Domain specific prompt templates
        if any(k in text_lower for k in ["cuti", "leave"]):
            return [
                "Ajukan permohonan cuti tahunan karyawan untuk teknisi lapangan",
                "Audit daftar pengajuan cuti yang masih berstatus pending approval"
            ]
        elif any(k in text_lower for k in ["absensi", "presensi", "lembur"]):
            return [
                "Tampilkan rekap absensi kunjungan site menara dan jam lembur teknisi",
                "Cek validasi presensi geofencing teknisi lapangan minggu ini"
            ]
        elif any(k in text_lower for k in ["rigger", "pelamar", "kandidat", "rekrutmen"]):
            return [
                "Filter kandidat rigger tower yang memiliki sertifikat TKPK tingkat 1",
                "Tampilkan pelamar yang lolos uji medis kelayakan bekerja di ketinggian"
            ]
        elif any(k in text_lower for k in ["invoice", "tagihan", "sewa menara", "mla"]):
            return [
                "Tampilkan rekapitulasi invoice sewa menara per operator dan status pembayarannya",
                "Daftarkan kontrak sewa menara baru untuk operator telekomunikasi"
            ]
        elif any(k in text_lower for k in ["listrik", "pln", "genset", "lahan", "sewa tanah"]):
            return [
                "Audit pengeluaran operasional listrik PLN dan sewa lahan menara",
                "Tampilkan beban utilitas genset dan tagihan listrik site tertinggi"
            ]
        elif any(k in text_lower for k in ["arus kas", "cash flow", "kas"]):
            return [
                "Tampilkan ringkasan arus kas masuk dan keluar beserta posisi saldo bersih terkini",
                "Berapa saldo kas operasional saat ini?"
            ]
        elif any(k in text_lower for k in ["penerimaan", "kedatangan", "tiba", "gudang", "po-"]):
            return [
                "PO-2026-001 sudah sampai di gudang, tolong catat penerimaan barangnya"
            ]
        elif any(k in text_lower for k in ["lacak", "tracking", "status po", "in transit"]):
            return [
                "Lacak status pengiriman PO yang sedang aktif dalam perjalanan",
                "Tampilkan daftar purchase order berstatus in transit dan unduh dokumen resminya"
            ]
        elif any(k in text_lower for k in ["restock", "pengadaan", "pr-to-po", "kritis", "menipis"]):
            return [
                f"Periksa kondisi stok untuk {clean_name} dan buat draft pengadaan barang",
                f"Jalankan evaluasi alur kerja {clean_name}"
            ]
        else:
            return [
                f"Jalankan alur kerja {clean_name}",
                f"Periksa status operasional untuk {clean_name}"
            ]

