import json
import re

from core.config import settings
from core.llm_client import gateway
from database.db import get_db_connection

def extract_recipient_email(prompt: str) -> str | None:
    """Helper to detect any email address or named person/role mentioned in the prompt text."""
    if not prompt:
        return None

    # 1. Direct standard RFC email regex pattern (e.g. user@balitower.co.id)
    match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', prompt)
    if match:
        email = match.group(0).strip().rstrip(".,;:!?")
        return email

    p_lower = prompt.lower().strip()

    # Guard: If user literally asks to send to email without specifying an email address,
    # do NOT resolve to any fallback account! Clarification MUST be requested instead.
    if re.search(r'\b(?:ke\s+email|via\s+email|kirimkan?\s+(?:ke\s+)?email)\b', p_lower):
        return None

    # 2. Dynamic employee & corporate role recipient resolution
    # Named contact aliases
    if "zeiniah" in p_lower:
        return "zeiniahalfiah@gmail.com"
    if "daffa" in p_lower and any(w in p_lower for w in ["ke daffa", "kepada daffa", "untuk daffa", "daffa"]):
        return getattr(settings, "DEFAULT_RECIPIENT_EMAIL", None) or "muhammaddaffaarigoh@gmail.com"

    # Default recipient for roles and internal colleague resolution
    user_email = getattr(settings, "DEFAULT_RECIPIENT_EMAIL", None) or "muhammaddaffaarigoh@gmail.com"

    # NOTE: "pengadaan" and "procurement" are explicitly excluded from bare role match
    # because in Indonesian, "pengadaan barang" is the operational noun phrase, never an email recipient!
    role_keys = ["hr.operations", "hrd", "hr", "personalia", "manager", "manajer", "boss", "bos"]
    for role_key in role_keys:
        # Must be explicitly preceded by direction indicators like 'ke', 'kepada', 'teruskan ke'
        if re.search(r'(?:ke|kepada|teruskan\s+ke|kirim\s+ke)\s+(?:rekan\s+|tim\s+|email\s+)?\b' + re.escape(role_key) + r'\b', p_lower):
            return user_email

    conn = None
    try:
        conn = get_db_connection(read_only=True)
        tables = set(r[0] for r in conn.execute("SHOW TABLES;").fetchall())
        if "employees" in tables:
            emp_rows = conn.execute("SELECT full_name FROM employees WHERE full_name IS NOT NULL;").fetchall()
            for (full_name,) in emp_rows:
                if not full_name:
                    continue
                first_name = full_name.split()[0].lower()
                # Check for explicit recipient context: "ke <nama>" or "kepada <nama>"
                if (len(first_name) >= 3 and re.search(r'(?:ke|kepada|teruskan\s+ke|kirim\s+ke)\s+(?:rekan\s+|staf\s+)?' + re.escape(first_name) + r'\b', p_lower)) or (f"ke {full_name.lower()}" in p_lower):
                    return user_email
    except Exception:
        pass
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return None


def check_clarification_needs(prompt: str, tenant_id: str = "ALL", recipient_email: str | None = None) -> dict | None:
    """
    Evaluates whether the user's natural language request lacks critical parameters.
    If so, returns structured clarification payload so agent can query the user back.
    """
    if not prompt:
        return None
    p_lower = prompt.lower().strip()
    
    # 1. Email clarification: User requested email dispatch/approval, but provided no recipient email address
    has_email_intent = (
        any(w in p_lower for w in ["kirimkan ke email", "kirim ke email", "kirim via email", "kirimkan via email", "ke email", "via email", "kirim email", "notif email", "emailkan"])
        or (("email" in p_lower or "surel" in p_lower) and any(w in p_lower for w in ["kirim", "send", "notif", "teruskan", "approve", "persetujuan", "surat"]))
    )
    extracted_email = extract_recipient_email(prompt) or recipient_email
    if has_email_intent and not extracted_email:
        clean_prompt = prompt.strip()
        default_target = getattr(settings, "DEFAULT_RECIPIENT_EMAIL", None) or "muhammaddaffaarigoh@gmail.com"
        
        # Build clean suggestion hint
        if re.search(r'ke\s+email\s*$', clean_prompt, re.IGNORECASE):
            hint_str = re.sub(r'ke\s+email\s*$', f'ke {default_target}', clean_prompt, flags=re.IGNORECASE)
        elif re.search(r'ke\s+email\b', clean_prompt, re.IGNORECASE):
            hint_str = re.sub(r'ke\s+email\b', f'ke {default_target}', clean_prompt, flags=re.IGNORECASE)
        else:
            hint_str = f"{clean_prompt} ke {default_target}"

        return {
            "needs_clarification": True,
            "field": "recipient_email",
            "title": "Alamat Email Diperlukan",
            "message": f"Anda meminta pengiriman notifikasi/persetujuan via email, namun alamat email penerima belum disebutkan. Mohon tentukan alamat email tujuan (contoh: *{default_target}* atau *manager@balitower.co.id*).",
            "hint": hint_str
        }
        
    # 2. Threshold update clarification: wants to update threshold but lacks value or item name
    wants_threshold = any(w in p_lower for w in ["ubah threshold", "ganti ambang", "update batas stok", "atur threshold", "ubah batas", "set threshold", "edit batas"])
    has_number = bool(re.search(r'\d+', prompt))
    if wants_threshold:
        if not has_number:
            return {
                "needs_clarification": True,
                "field": "threshold_parameters",
                "title": "Detail Batas Stok Diperlukan",
                "message": "Untuk memperbarui batas minimum atau maksimum stok, mohon sebutkan nama barang serta nilai batas baru yang diinginkan (contoh: *'Ubah batas minimum SFP Transceiver menjadi 25'*).",
                "hint": "Ubah batas minimum SFP Transceiver menjadi 25"
            }
        
        # Check if item name is missing (e.g. "ubah batas minimum menjadi 25" without specifying which item)
        inventory_words = ["sfp", "kabel", "patch", "drop", "otb", "adapter", "baterai", "transceiver", "core", "fo", "fiber", "router", "switch", "clamp", "odc", "odp", "closure"]
        has_item_mention = any(iw in p_lower for iw in inventory_words) or any(len(word) > 3 and word not in ["ubah", "ganti", "update", "atur", "batas", "minimum", "maksimum", "menjadi", "threshold", "stok", "stoknya", "tolong", "buat", "biar"] for word in p_lower.split())
        # If the words are strictly command words without an item subject
        command_only_words = {"ubah", "ganti", "update", "atur", "batas", "minimum", "maksimum", "menjadi", "threshold", "stok", "stoknya", "tolong", "buat", "biar", "ke", "di", "dan", "ya", "dong"}
        tokens = set(re.findall(r'[a-zA-Z]+', p_lower))
        if tokens.issubset(command_only_words):
            match_num = re.search(r'\d+', prompt)
            val_num = match_num.group(0) if match_num else "25"
            return {
                "needs_clarification": True,
                "field": "threshold_item_name",
                "title": "Nama Barang Diperlukan",
                "message": f"Mohon sebutkan nama barang material yang ingin diperbarui batas stoknya menjadi {val_num} (contoh: *'Ubah batas minimum SFP Transceiver menjadi {val_num}'*).",
                "hint": f"Ubah batas minimum SFP Transceiver menjadi {val_num}"
            }
        
    # 3. Product registration clarification: wants to register/add new product but no details provided
    wants_register = any(w in p_lower for w in ["tambah produk", "tambah barang", "daftarkan barang", "daftarkan produk", "registrasi produk", "registrasi barang", "tambah material"])
    has_spec = bool(re.search(r'(stok|batas|min|harga|satuan|\d+)', p_lower))
    if wants_register and not has_spec:
        return {
            "needs_clarification": True,
            "field": "product_details",
            "title": "Spesifikasi Produk Diperlukan",
            "message": "Untuk mendaftarkan produk baru ke database inventaris, mohon sertakan informasi nama produk dan jumlah stok awal (contoh: *'Tambah produk Baterai Lithium 48V, stok 15, batas min 5'*).",
            "hint": "Tambah produk Baterai Lithium 48V, stok 15, batas min 5"
        }

    # 4. Goods receipt clarification: wants to record received goods but no PO number
    wants_receipt = any(w in p_lower for w in ["catat penerimaan", "penerimaan barang", "barang sudah sampai", "terima po", "catat po tiba", "barang tiba"])
    if wants_receipt and not re.search(r'\bpo[-_]?\d+', p_lower):
        return {
            "needs_clarification": True,
            "field": "po_number_required",
            "title": "Nomor PO Diperlukan",
            "message": "Untuk mencatat penerimaan barang masuk ke gudang, mohon sebutkan nomor Purchase Order (PO) yang diterima (contoh: *'Barang untuk PO-2026-006 sudah sampai di Gudang Bandung, tolong catat penerimaannya'*).",
            "hint": "Barang untuk PO-2026-006 sudah sampai di Gudang Bandung, tolong catat penerimaannya"
        }

    # 5. PO document lookup clarification: wants to view PO document without PO number
    wants_po_doc = any(w in p_lower for w in ["lihat dokumen po", "tampilkan berkas po", "unduh po", "cetak pdf po", "lihat berkas po", "tampilkan po", "download po", "lihat po"])
    if wants_po_doc and not re.search(r'\bpo[-_]?\d+', p_lower):
        return {
            "needs_clarification": True,
            "field": "po_lookup_id",
            "title": "Nomor Purchase Order Diperlukan",
            "message": "Mohon sebutkan nomor Purchase Order (PO) yang ingin dilihat atau diunduh dokumen PDF resminya (contoh: *'Tolong tampilkan dokumen PDF untuk PO-2026-006'*).",
            "hint": "Tolong tampilkan dokumen PDF untuk PO-2026-006"
        }

    # 6. Specific item stock query clarification: asks for stock but specifies no item
    wants_specific_stock = any(w in p_lower for w in ["berapa stok barang", "cek stok barang", "tampilkan stok barang", "cek saldo barang", "stok barang apa", "cek ketersediaan barang"])
    generic_only = tokens = set(re.findall(r'[a-zA-Z]+', p_lower))
    generic_stock_words = {"berapa", "cek", "tampilkan", "saldo", "stok", "barang", "barangnya", "material", "saat", "ini", "ada", "apa", "saja", "tolong", "gudang"}
    if wants_specific_stock and tokens.issubset(generic_stock_words):
        return {
            "needs_clarification": True,
            "field": "item_name_required",
            "title": "Nama Barang Diperlukan",
            "message": "Mohon sebutkan nama atau SKU barang material yang ingin Anda periksa stoknya (contoh: *'Berapa stok SFP Transceiver 10G saat ini?'*).",
            "hint": "Berapa stok SFP Transceiver 10G saat ini?"
        }

    return None


class SemanticRouter:
    @classmethod
    async def route_prompt(
        cls, 
        prompt: str, 
        tenant_id: str = "ALL", 
        history: list[dict[str, str]] | None = None
    ) -> dict:
        """
        Matches user prompt strictly to a predefined workflow ID allowed for this tenant.
        Does NOT hallucinate or pick an arbitrary workflow if intent is out-of-scope.
        Returns workflow_id: None and is_unrelated: True if the prompt is out of scope.
        Supports multi-turn context history.
        """
        conn = get_db_connection(read_only=True)
        query_cols = "id, name, description, business_instruction, example_prompts, tenant_id"
        if tenant_id in ["ALL", "admin", "ADMIN", "SUPERADMIN"]:
            workflows = conn.execute(f"""
                SELECT {query_cols} 
                FROM workflows 
                ORDER BY id ASC
            """).fetchall()
        else:
            tenant_variants = [tenant_id, "ALL"]
            if tenant_id in ["INVENTORY", "TENANT_A", "usera"]:
                tenant_variants.extend(["INVENTORY", "TENANT_A", "usera"])
            elif tenant_id in ["HR", "TENANT_B", "userb"]:
                tenant_variants.extend(["HR", "TENANT_B", "userb"])
            elif tenant_id in ["FINANCE", "TENANT_C", "userc"]:
                tenant_variants.extend(["FINANCE", "TENANT_C", "userc"])
            placeholders = ", ".join(["?"] * len(tenant_variants))
            workflows = conn.execute(f"""
                SELECT {query_cols} 
                FROM workflows 
                WHERE tenant_id IN ({placeholders})
                ORDER BY id ASC
            """, tenant_variants).fetchall()
        conn.close()
        
        if not workflows:
            return {
                "workflow_id": None,
                "send_email": False,
                "threshold_updates": [],
                "target_item_name": None,
                "is_fallback": False
            }

        prompt_clean = prompt.strip().lower()
        # Guard against single-word, ambiguous, or too-short inputs without clear command
        if len(prompt_clean) < 3 or prompt_clean in ["pr", "po", "stok", "cek", "halo", "hi", "tes", "test", "help", "menu", "workflow", "buat", "pesan"]:
            return {
                "workflow_id": None,
                "is_unrelated": True,
                "send_email": False,
                "threshold_updates": [],
                "target_item_name": None,
                "is_fallback": False
            }

        # Build enriched workflows context including business instructions and example prompts
        workflow_entries = []
        for row in workflows:
            wf_id, wf_name, wf_desc, wf_inst, wf_ex, wf_tenant = row
            entry = f"- ID: {wf_id}\n  Nama: {wf_name}\n  Deskripsi: {wf_desc or '-'}"
            if wf_inst:
                entry += f"\n  Instruksi Bisnis: {wf_inst}"
            if wf_ex:
                try:
                    examples = json.loads(wf_ex) if isinstance(wf_ex, str) else wf_ex
                    if isinstance(examples, list) and examples:
                        entry += f"\n  Contoh Prompt: {'; '.join(str(x) for x in examples)}"
                except Exception:
                    entry += f"\n  Contoh Prompt: {wf_ex}"
            workflow_entries.append(entry)
        workflows_str = "\n\n".join(workflow_entries)
        
        system_prompt = f"""You are a Strict Semantic Router for an Enterprise Management System (PT Bali Towerindo Sentra Tbk).
Match the user's operational command to EXACTLY ONE of the following permitted workflows:

{workflows_str}

CRITICAL RULES:
1. Prioritize matching based on the workflow's Description, Business Instruction, and Example Prompts.
2. If the user's prompt is UNRELATED, vague, ambiguous, programming questions, chit-chat, or general greetings without clear command, return:
   {{"workflow_id": null, "is_unrelated": true}}
3. DO NOT match to a restock/procurement pipeline (like WF-A01) unless the user EXPLICITLY commands to restock, draft/issue a PR, or order depleted material.
4. If the user wants to register, add, or create a new inventory item, extract "new_item_data": {{"name": string, "category": string, "current_stock": int, "min_threshold": int, "max_threshold": int, "avg_daily_usage": float, "lead_time_days": int, "unit": string}}.
5. If the user wants to update a threshold, extract "threshold_updates": [{{"item_name": "name of item", "new_min_threshold": 100, "new_max_threshold": 300}}].
6. If the user specifies an item name to inspect, extract "target_item_name".
7. If the user explicitly asks to send an email, report, or notify via email, extract "send_email": true. Otherwise, "send_email": false.
8. If the user's command is missing a critical parameter required to execute (e.g. requested sending via email but gave no recipient address, wants to update threshold but gave no value or item, etc.), return:
   {{"workflow_id": "clarification_needed", "needs_clarification": true, "clarification": {{"title": "string", "message": "string", "hint": "string"}}}}

Output strictly valid JSON with exact keys:
- "workflow_id" (string or null)
- "is_unrelated" (boolean)
- "needs_clarification" (optional boolean)
- "clarification" (optional object with title, message, hint)
- "new_item_data" (optional object)
- "threshold_updates" (optional array)
- "target_item_name" (optional string)
- "send_email" (boolean)
"""
        messages = [{"role": "system", "content": system_prompt}]
        if history and isinstance(history, list):
            for turn in history[-6:]:
                if isinstance(turn, dict) and turn.get("role") and turn.get("content"):
                    messages.append({"role": turn["role"], "content": str(turn["content"])})
        messages.append({"role": "user", "content": prompt})

        prompt_lower = prompt.lower()
        extracted_email = extract_recipient_email(prompt)

        # Check for direct workflow ID mention (e.g. user explicitly writes "WF-A01")
        for row in workflows:
            wf_id_term = row[0].lower()
            if wf_id_term in prompt_lower:
                return {
                    "workflow_id": row[0],
                    "send_email": bool(extracted_email) or ("email" in prompt_lower),
                    "recipient_email": extracted_email,
                    "is_fallback": False
                }

        # ----------------------------------------------------
        # LAYER 1: LLM-FIRST ROUTING (Primary Decision Maker)
        # ----------------------------------------------------
        try:
            response_str = await gateway.chat_completion("nemotron-35", messages, temperature=0.1, response_format_json=True)
            json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if json_match:
                response_str = json_match.group(0)
            parsed = json.loads(response_str)

            if parsed.get("needs_clarification") or parsed.get("workflow_id") == "clarification_needed":
                return {
                    "workflow_id": "clarification_needed",
                    "action_type": "clarification_needed",
                    "needs_clarification": True,
                    "clarification": parsed.get("clarification") or {
                        "title": "Klarifikasi Diperlukan",
                        "message": "Mohon lengkapi parameter instruksi Anda.",
                        "hint": prompt
                    },
                    "message": (parsed.get("clarification") or {}).get("message", "Mohon lengkapi parameter instruksi Anda."),
                    "is_fallback": False
                }

            valid_ids = {r[0] for r in workflows}
            if parsed.get("workflow_id") and parsed["workflow_id"] in valid_ids:
                if extracted_email:
                    parsed["send_email"] = True
                    parsed["recipient_email"] = extracted_email
                parsed["is_fallback"] = False
                return parsed
            if parsed.get("is_unrelated") or parsed.get("workflow_id") is None:
                return {
                    "workflow_id": None,
                    "is_unrelated": True,
                    "send_email": False,
                    "threshold_updates": [],
                    "target_item_name": None,
                    "is_fallback": False
                }
        except Exception as e:
            print(f"[SEMANTIC ROUTER] LLM offline or timed out ({e}). Activating fail-safe heuristic matcher.")

        # ----------------------------------------------------
        # LAYER 2: FAIL-SAFE HEURISTIC MATCHER (Only on LLM Error)
        # ----------------------------------------------------
        # 1. Match example_prompts & titles of all registered workflows (including Admin-created workflows)
        for row in workflows:
            wf_id, wf_name, wf_desc, wf_inst, wf_ex, wf_tenant = row
            if wf_ex:
                try:
                    ex_list = json.loads(wf_ex) if isinstance(wf_ex, str) else wf_ex
                    if isinstance(ex_list, list):
                        for ex_p in ex_list:
                            ex_clean = str(ex_p).lower().strip()
                            if ex_clean and (ex_clean in prompt_lower or prompt_lower in ex_clean):
                                return {
                                    "workflow_id": wf_id,
                                    "send_email": bool(extracted_email) or ("email" in prompt_lower),
                                    "recipient_email": extracted_email,
                                    "is_fallback": True
                                }
                except Exception:
                    pass
            if wf_name and len(wf_name) > 6 and wf_name.lower() in prompt_lower:
                return {
                    "workflow_id": wf_id,
                    "send_email": bool(extracted_email) or ("email" in prompt_lower),
                    "recipient_email": extracted_email,
                    "is_fallback": True
                }

        # 2. Schema ALL Workflows
        if any(k in prompt_lower for k in ["profil", "siapa saya", "info akun", "hak akses", "wewenang"]):
            for row in workflows:
                if row[0] == "WF-ALL-01" or any(w in row[1].lower() for w in ["profil", "hak akses", "user"]):
                    return {"workflow_id": row[0], "send_email": False, "is_fallback": True}

        if any(k in prompt_lower for k in ["info sistem", "status sistem", "status server", "health check", "kesehatan sistem", "status kesehatan", "kesehatan"]):
            for row in workflows:
                if row[0] == "WF-ALL-02" or any(w in row[1].lower() for w in ["informasi sistem", "status layanan", "health"]):
                    return {"workflow_id": row[0], "send_email": False, "is_fallback": True}

        if any(k in prompt_lower for k in ["panduan operasional", "sop", "helpdesk"]):
            for row in workflows:
                if row[0] == "WF-ALL-03" or any(w in row[1].lower() for w in ["panduan", "darurat", "sop"]):
                    return {"workflow_id": row[0], "send_email": False, "is_fallback": True}

        # 3. Client Onboarding (Finance / Schema C)
        if any(k in prompt_lower for k in ["onboarding", "mla", "kontrak baru", "sewa baru", "daftarkan operator"]):
            for row in workflows:
                if any(w in row[1].lower() for w in ["onboard", "klien", "kontrak", "mla"]):
                    return {
                        "workflow_id": row[0],
                        "send_email": True,
                        "recipient_email": extracted_email,
                        "is_fallback": True
                    }

        # 4. HR Candidates / Recruitment Screening (Schema B)
        if any(k in prompt_lower for k in ["kandidat", "pelamar", "rigger", "tkpk", "rekrutmen", "screening"]):
            for row in workflows:
                if row[0] == "WF-003" or any(w in row[1].lower() for w in ["pelamar", "kandidat", "rigger"]):
                    return {"workflow_id": row[0], "send_email": False, "is_fallback": True}

        # 5. HR Attendance & Overtime (Schema B)
        if any(k in prompt_lower for k in ["absensi", "absen", "lembur", "overtime", "geofencing", "kunjungan site"]):
            for row in workflows:
                if row[0] == "WF-002" or any(w in row[1].lower() for w in ["absensi", "lembur", "kehadiran"]):
                    return {"workflow_id": row[0], "send_email": False, "is_fallback": True}

        # 6. HR Leave Audit & Approval (Schema B)
        if "cuti" in prompt_lower and any(k in prompt_lower for k in ["audit", "pending", "periksa", "daftar", "status"]):
            for row in workflows:
                if "cuti" in row[1].lower() and ("pending" in row[1].lower() or "audit" in row[1].lower() or "otorisasi" in row[1].lower()):
                    return {
                        "workflow_id": row[0],
                        "send_email": True,
                        "recipient_email": extracted_email,
                        "is_fallback": True
                    }

        # 7. HR Leave Quota (Schema B)
        if any(k in prompt_lower for k in ["sisa cuti", "kuota cuti", "saldo cuti", "jatah cuti"]):
            for row in workflows:
                if any(w in row[1].lower() for w in ["kuota", "saldo", "sisa cuti"]):
                    return {"workflow_id": row[0], "send_email": False, "is_fallback": True}

        # 8. Finance Workflows (Schema C)
        if any(k in prompt_lower for k in ["pendapatan", "revenue", "invoice operator", "tagihan operator", "sewa menara"]):
            for row in workflows:
                if row[0] == "WF-004" or any(w in row[1].lower() for w in ["pendapatan", "revenue", "invoice"]):
                    return {"workflow_id": row[0], "send_email": False, "is_fallback": True}

        if any(k in prompt_lower for k in ["beban operasional", "opex", "listrik pln", "beban listrik", "sewa lahan", "listrik dan sewa"]):
            for row in workflows:
                if row[0] == "WF-005" or any(w in row[1].lower() for w in ["beban listrik", "opex", "sewa lahan", "beban operasional"]):
                    return {"workflow_id": row[0], "send_email": False, "is_fallback": True}

        if any(k in prompt_lower for k in ["arus kas", "cash flow", "cashflow", "kas masuk", "kas keluar"]):
            for row in workflows:
                if row[0] == "WF-006" or any(w in row[1].lower() for w in ["arus kas", "cash flow", "cashflow"]):
                    return {"workflow_id": row[0], "send_email": False, "is_fallback": True}

        # 9. Inventory - Product Registration
        if any(k in prompt_lower for k in ["tambah barang", "tambah produk", "registrasi produk", "tambah material"]):
            for row in workflows:
                if any(w in row[1].lower() for w in ["daftar", "tambah", "registrasi"]):
                    return {
                        "workflow_id": row[0],
                        "new_item_data": {},
                        "send_email": bool(extracted_email),
                        "recipient_email": extracted_email,
                        "is_fallback": True
                    }

        # 10. Inventory - Threshold Update
        if any(k in prompt_lower for k in ["threshold", "ambang", "ubah batas"]):
            for row in workflows:
                if row[0] == "WF-002" or "threshold" in row[1].lower():
                    return {"workflow_id": row[0], "threshold_updates": [], "send_email": False, "is_fallback": True}

        # 11. Restock / PR Creation Pipeline
        if any(k in prompt_lower for k in ["buatkan pr", "bikin pr", "terbitkan pr", "draf pr", "draft pr", "restock material", "pesan material"]):
            send_mail = bool(extracted_email) or ("email" in prompt_lower)
            for row in workflows:
                if any(w in row[1].lower() for w in ["restock", "pengadaan"]):
                    return {
                        "workflow_id": row[0],
                        "send_email": send_mail,
                        "recipient_email": extracted_email,
                        "threshold_updates": [],
                        "target_item_name": None,
                        "is_fallback": True
                    }

        # Anti-Hallucination Guardrail:
        return {
            "workflow_id": None,
            "is_unrelated": True,
            "send_email": False,
            "threshold_updates": [],
            "target_item_name": None,
            "is_fallback": True
        }
