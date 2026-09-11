import json
import re

from core.llm_client import ModelGateway
from database.db import get_db_connection

def _extract_item_attributes_from_text(prompt: str) -> dict:
    """Helper to extract product attributes from natural language prompt."""
    item = {}
    
    # 1. Extract Name
    name_match = re.search(r'(?:nama\s+produk|nama\s+barang|nama|produk|barang)\s*[:=]?\s*([A-Za-z0-9\s\-]+?)(?=,\s*|\s+kategori|\s+stok|\s+batas|\s+min|\s+harga|\s+dam|$)', prompt, re.IGNORECASE)
    if name_match:
        name_val = name_match.group(1).strip()
        name_val = re.sub(r'^(?:baru\s+|tambah\s+|tambahkan\s+|bernama\s+)+', '', name_val, flags=re.IGNORECASE).strip()
        if name_val and name_val.lower() not in ["baru", "produk", "barang"]:
            item["name"] = name_val
            
    # 2. Extract Category
    cat_match = re.search(r'kategori\s*[:=]?\s*([A-Za-z0-9\s]+?)(?=,\s*|\s+stok|\s+batas|\s+min|\s+harga|\s+dam|$)', prompt, re.IGNORECASE)
    if cat_match:
        item["category"] = cat_match.group(1).strip().capitalize()
    else:
        if any(w in prompt.lower() for w in ["hp", "samsung", "sensor", "module", "esp", "stm", "elektronik", "electronics", "phone"]):
            item["category"] = "Electronics"
        else:
            item["category"] = "General"
            
    # 3. Extract Current Stock
    stock_match = re.search(r'stok\s*(?:awal|fisik)?\s*[:=]?\s*(\d+)', prompt, re.IGNORECASE)
    if stock_match:
        item["current_stock"] = int(stock_match.group(1))
        
    # 4. Extract Min/Max Threshold
    min_match = re.search(r'(?:batas\s+min(?:imum)?|min(?:imum)?\s+threshold|threshold\s+min(?:imal)?|min)\s*[:=]?\s*(\d+)', prompt, re.IGNORECASE)
    if min_match:
        item["min_threshold"] = int(min_match.group(1))
        
    max_match = re.search(r'(?:batas\s+mak(?:simal)?|mak(?:simal)?\s+threshold|threshold\s+mak(?:simal)?|max)\s*[:=]?\s*(\d+)', prompt, re.IGNORECASE)
    if max_match:
        item["max_threshold"] = int(max_match.group(1))
        
    # 5. Extract Burn Rate / Daily Usage
    usage_match = re.search(r'(?:konsumsi|burn\s+rate|daily\s+usage|pakai)\s*[:=]?\s*([\d\.]+)', prompt, re.IGNORECASE)
    if usage_match:
        item["avg_daily_usage"] = float(usage_match.group(1))
    else:
        item["avg_daily_usage"] = 1.0
        
    # 6. Extract Lead Time Days
    lt_match = re.search(r'lead\s*time\s*[:=]?\s*(\d+)', prompt, re.IGNORECASE)
    if lt_match:
        item["lead_time_days"] = int(lt_match.group(1))
    else:
        item["lead_time_days"] = 3
        
    # 7. Extract Unit
    unit_match = re.search(r'satuan\s*(?:unit)?\s*[:=]?\s*([a-zA-Z]+)', prompt, re.IGNORECASE)
    if unit_match:
        item["unit"] = unit_match.group(1).strip()
    else:
        item["unit"] = "pcs"
        
    # 8. Extract Unit Price
    price_match = re.search(r'harga\s*[:=]?\s*(?:rp|rp\.|idr)?\s*(\d+(?:\.\d+)*)', prompt, re.IGNORECASE)
    if price_match:
        price_str = price_match.group(1).replace('.', '') # remove dots if any
        item["unit_price"] = int(price_str)
        
    return item


def extract_recipient_email(prompt: str) -> str | None:
    """Helper to detect any email address or named person/role mentioned in the prompt text."""
    if not prompt:
        return None

    # 1. Direct standard email regex pattern
    match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', prompt)
    if match:
        email = match.group(0).strip()
        email = email.rstrip(".,;:!?")
        return email

    # 2. Named recipient resolution (colleagues, roles, and corporate staff)
    p_lower = prompt.lower()
    named_map = {
        "zeiniah": "zeiniahalfiah@gmail.com",
        "daffa": "muhammaddaffaarigoh@gmail.com",
        "muhammad daffa": "muhammaddaffaarigoh@gmail.com",
        "daffaarigoh": "muhammaddaffaarigoh@gmail.com",
        "daffaarigoh02": "daffaarigoh02@gmail.com",
        "hr.operations": "hr.operations@balitower.co.id",
        "hrd": "hr.operations@balitower.co.id",
        "hr": "hr.operations@balitower.co.id",
        "personalia": "hr.operations@balitower.co.id",
        "manager": "manager@balitower.co.id",
        "manajer": "manager@balitower.co.id",
        "boss": "manager@balitower.co.id",
        "bos": "manager@balitower.co.id",
        "procurement": "procurement@balitower.co.id",
        "pengadaan": "procurement@balitower.co.id",
        "budi santoso": "budi.santoso@balitower.co.id",
        "budi": "budi.santoso@balitower.co.id",
        "dedi kurniawan": "dedi.kurniawan@balitower.co.id",
        "dedi": "dedi.kurniawan@balitower.co.id",
        "rian hidayat": "rian.hidayat@balitower.co.id",
        "rian": "rian.hidayat@balitower.co.id",
        "siti rahmawati": "siti.rahmawati@balitower.co.id",
        "siti": "siti.rahmawati@balitower.co.id",
        "fajar nugraha": "fajar.nugraha@balitower.co.id",
        "fajar": "fajar.nugraha@balitower.co.id",
        "dewi lestari": "dewi.lestari@balitower.co.id",
        "dewi": "dewi.lestari@balitower.co.id",
        "hendra gunawan": "hendra.gunawan@balitower.co.id",
        "hendra": "hendra.gunawan@balitower.co.id",
        "yusuf maulana": "yusuf.maulana@balitower.co.id",
        "yusuf": "yusuf.maulana@balitower.co.id",
        "agus setiawan": "agus.setiawan@balitower.co.id",
        "agus": "agus.setiawan@balitower.co.id",
    }

    # Match directional phrases: "ke <nama>", "kirim ke <nama>", "email ke <nama>", "kepada <nama>"
    for key, target_email in named_map.items():
        pat = r'(?:ke|kepada|untuk|email(?:kan)?|kirim(?:kan)?|tujukan)\s+(?:rekan\s+)?(?:sdr\s+|bapak\s+|ibu\s+|pak\s+|bu\s+)?' + re.escape(key) + r'\b'
        if re.search(pat, p_lower):
            return target_email

    return None


def check_clarification_needs(prompt: str, tenant_id: str = "ALL") -> dict | None:
    """
    Evaluates whether the user's natural language request lacks critical parameters.
    If so, returns structured clarification payload so agent can query the user back.
    """
    if not prompt:
        return None
    p_lower = prompt.lower().strip()
    
    # 1. Email clarification: User requested email dispatch/approval, but provided no email address
    has_email_intent = ("email" in p_lower or "surel" in p_lower) and any(w in p_lower for w in ["kirim", "send", "notif", "teruskan", "approve", "persetujuan", "surat"])
    extracted_email = extract_recipient_email(prompt)
    if has_email_intent and not extracted_email:
        return {
            "needs_clarification": True,
            "field": "recipient_email",
            "title": "Alamat Email Diperlukan",
            "message": "Anda meminta pengiriman notifikasi/persetujuan via email, namun alamat email penerima belum disebutkan. Mohon tentukan alamat email tujuan (contoh: *manager@balitower.co.id*).",
            "hint": "Kirimkan dokumen PR ini ke manager@balitower.co.id"
        }
        
    # 2. Threshold update clarification: wants to update threshold but neither item nor value given
    wants_threshold = any(w in p_lower for w in ["ubah threshold", "ganti ambang", "update batas stok", "atur threshold", "ubah batas"])
    has_number = bool(re.search(r'\d+', prompt))
    if wants_threshold and not has_number:
        return {
            "needs_clarification": True,
            "field": "threshold_parameters",
            "title": "Detail Batas Stok Diperlukan",
            "message": "Untuk memperbarui batas minimum atau maksimum stok, mohon sebutkan nama barang serta nilai batas baru yang diinginkan (contoh: *'Ubah batas minimum SFP Transceiver menjadi 25'*).",
            "hint": "Ubah batas minimum SFP Transceiver menjadi 25"
        }
        
    # 3. Product registration clarification: wants to register/add new product but no details provided
    wants_register = any(w in p_lower for w in ["tambah produk", "tambah barang", "daftarkan barang", "daftarkan produk", "registrasi produk", "registrasi barang"])
    extracted_item = _extract_item_attributes_from_text(prompt)
    raw_name = extracted_item.get("name", "")
    filler_words = {'dong', 'ya', 'baru', 'gan', 'min', 'tolong', 'pls', 'please', 'deh', 'sih', 'lah', 'ini', 'itu', 'dulu'}
    valid_name_tokens = [w for w in raw_name.lower().split() if w not in filler_words]
    if wants_register and (not valid_name_tokens and "current_stock" not in extracted_item):
        return {
            "needs_clarification": True,
            "field": "product_details",
            "title": "Spesifikasi Produk Diperlukan",
            "message": "Untuk mendaftarkan produk baru ke database inventaris, mohon sertakan informasi nama produk dan jumlah stok awal (contoh: *'Tambah produk Baterai Lithium 48V, stok 15, batas min 5'*).",
            "hint": "Tambah produk Baterai Lithium 48V, stok 15, batas min 5"
        }
        
    return None


class SemanticRouter:
    @classmethod
    async def route_prompt(cls, prompt: str, tenant_id: str = "ALL") -> dict:
        """
        Matches user prompt strictly to a predefined workflow ID allowed for this tenant.
        Does NOT hallucinate or pick an arbitrary workflow if intent is out-of-scope.
        Returns workflow_id: None and is_unrelated: True if the prompt is out of scope.
        """
        conn = get_db_connection(read_only=True)
        tenant_variants = [tenant_id, "ALL"]
        if tenant_id in ["INVENTORY", "TENANT_A", "usera"]:
            tenant_variants.extend(["INVENTORY", "TENANT_A", "usera"])
        elif tenant_id in ["HR", "TENANT_B", "userb"]:
            tenant_variants.extend(["HR", "TENANT_B", "userb"])
        elif tenant_id in ["FINANCE", "TENANT_C", "userc"]:
            tenant_variants.extend(["FINANCE", "TENANT_C", "userc"])
        placeholders = ", ".join(["?"] * len(tenant_variants))
        workflows = conn.execute(f"""
            SELECT id, name, description, tenant_id 
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
                "target_item_name": None
            }

        prompt_clean = prompt.strip().lower()
        # Guard against single-word, ambiguous, or too-short inputs without clear command
        if len(prompt_clean) < 3 or prompt_clean in ["pr", "po", "stok", "cek", "halo", "hi", "tes", "test", "help", "menu", "workflow", "buat", "pesan"]:
            return {
                "workflow_id": None,
                "is_unrelated": True,
                "send_email": False,
                "threshold_updates": [],
                "target_item_name": None
            }

        workflows_str = "\n".join([f"- ID: {row[0]}, Name: {row[1]}, Desc: {row[2]}" for row in workflows])
        
        system_prompt = f"""You are a Strict Semantic Router for an Enterprise Inventory & Restock system.
Match the user's prompt ONLY to one of the following permitted workflows:

{workflows_str}

CRITICAL RULES:
1. If the user's prompt is UNRELATED, vague, ambiguous, or lacks a clear operational command (e.g. single words like "pr", "po", "stok", general greetings, chit-chat, weather, programming questions), you MUST return:
   {{"workflow_id": null, "is_unrelated": true}}
2. DO NOT force or default any prompt to a workflow unless it clearly matches the intent of that workflow.
3. DO NOT match to a restock/procurement pipeline (like WF-A01) unless the user EXPLICITLY commands to create/draft/issue a PR or restock depleted material (e.g., "buatkan PR", "terbitkan PR untuk stok menipis", "restock material"). Mere queries about stock or single keywords do NOT match procurement pipelines.
4. If the user wants to register, add, or create a new inventory item, extract "new_item_data": {{"name": string, "category": string, "current_stock": int, "min_threshold": int, "max_threshold": int, "avg_daily_usage": float, "lead_time_days": int, "unit": string}} (extract whatever fields the user provided, leaving unmentioned fields out).
5. If the user wants to update a threshold, extract "threshold_updates": [{{"item_name": "name of item", "new_min_threshold": 100, "new_max_threshold": 300}}]. Include only the thresholds the user specified.
6. If the user specifies an item name to check, extract it as "target_item_name".
7. If the user explicitly asks to send an email, report, or notify via email, extract "send_email": true. Otherwise, "send_email": false.

Output strictly valid JSON with exact keys: "workflow_id" (string or null), "is_unrelated" (boolean), "new_item_data" (optional object), "threshold_updates" (optional array), "target_item_name" (optional string), "send_email" (boolean).
If no workflow matches or the request is unrelated, return "workflow_id": null, "is_unrelated": true.
"""
        gateway = ModelGateway()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        prompt_lower = prompt.lower()
        extracted_email = extract_recipient_email(prompt)

        # Check for client operator onboarding intent first (User C)
        is_onboarding_intent = any(k in prompt_lower for k in ["klien", "operator", "sewa", "onboarding", "mla", "menara", "kontrak"]) and any(k in prompt_lower for k in ["daftar", "daftarkan", "baru", "onboard", "tambah", "ajukan"])
        if is_onboarding_intent:
            for row in workflows:
                if any(w in row[1].lower() for w in ["onboard", "klien", "kontrak", "mla"]) or ("daftar" in row[1].lower() and "operator" in row[1].lower()):
                    return {
                        "workflow_id": row[0],
                        "send_email": True,
                        "recipient_email": extracted_email
                    }

        # Check for Restock / PR creation pipeline intent (User A)
        is_pr_pipeline = (
            any(k in prompt_lower for k in ["buat pr", "buatkan pr", "draf pr", "draft pr", "terbitkan pr", "kirim pr", "kirimkan pr", "restock", "order barang"])
            or ("pr" in prompt_lower and any(k in prompt_lower for k in ["kirim", "email", "ajukan", "buat", "terbit", "menipis"]))
        )
        if is_pr_pipeline:
            for row in workflows:
                if row[0] == "WF-A01" or "pipeline_pengadaan" in row[1].lower() or "pengadaan" in row[1].lower():
                    res = {
                        "workflow_id": row[0],
                        "send_email": bool(extracted_email),
                        "threshold_updates": [],
                        "target_item_name": None
                    }
                    if extracted_email:
                        res["recipient_email"] = extracted_email
                    return res

        # Check for product registration intent (only if user workflow has registration and not onboarding)
        if not is_onboarding_intent and any(k in prompt_lower for k in ["tambah", "tambahkan", "daftar", "daftarkan", "registrasi", "masukkan produk", "tambah produk", "tambah barang", "tambahkan nama produk", "buat barang"]):
            for row in workflows:
                if any(w in row[1].lower() for w in ["daftar", "pendaftaran", "tambah", "registrasi", "register"]) and not any(w in row[1].lower() for w in ["klien", "operator", "sewa", "kontrak"]):
                    extracted_item = _extract_item_attributes_from_text(prompt)
                    res = {
                        "workflow_id": row[0],
                        "new_item_data": extracted_item,
                        "send_email": bool(extracted_email)
                    }
                    if extracted_email:
                        res["recipient_email"] = extracted_email
                    return res

        try:
            response_str = await gateway.chat_completion("nemotron-35", messages, temperature=0.1, response_format_json=True)
            json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if json_match:
                response_str = json_match.group(0)
            parsed = json.loads(response_str)
            valid_ids = {r[0] for r in workflows}
            if parsed.get("workflow_id") and parsed["workflow_id"] in valid_ids:
                if extracted_email:
                    parsed["send_email"] = True
                    parsed["recipient_email"] = extracted_email
                return parsed
            if parsed.get("is_unrelated") or parsed.get("workflow_id") is None:
                return {
                    "workflow_id": None,
                    "is_unrelated": True,
                    "send_email": False,
                    "threshold_updates": [],
                    "target_item_name": None
                }
        except Exception as e:
            print(f"[SEMANTIC ROUTER] LLM unavailable ({e}). Using intelligent heuristic matcher.")
            
        # 0. Check for Schema ALL Utility Workflows
        # A. User Profile & Access Rights (WF-ALL-01)
        if any(k in prompt_lower for k in ["profil", "siapa saya", "info akun", "hak akses", "wewenang", "role saya", "user info"]):
            for row in workflows:
                if row[0] == "WF-ALL-01" or any(w in row[1].lower() for w in ["profil", "hak akses", "user"]):
                    return {"workflow_id": row[0], "send_email": False}

        # B. System Info & Health Status (WF-ALL-02)
        if any(k in prompt_lower for k in ["info sistem", "status sistem", "status server", "health check", "spesifikasi sistem", "informasi sistem", "versi sistem"]):
            for row in workflows:
                if row[0] == "WF-ALL-02" or any(w in row[1].lower() for w in ["informasi sistem", "status layanan", "health"]):
                    return {"workflow_id": row[0], "send_email": False}

        # C. Company Guidelines & Emergency Contacts (WF-ALL-03)
        if any(k in prompt_lower for k in ["panduan operasional", "sop perusahaan", "kontak darurat", "helpdesk", "aturan kerja", "panduan", "sop"]):
            for row in workflows:
                if row[0] == "WF-ALL-03" or any(w in row[1].lower() for w in ["panduan", "darurat", "sop", "guideline"]):
                    return {"workflow_id": row[0], "send_email": False}

        # Check for New Client Operator Onboarding & Lease Contract (Approval Workflow)
        if is_onboarding_intent or any(k in prompt_lower for k in ["klien baru", "operator baru", "daftar operator", "sewa baru", "kontrak baru", "onboarding", "daftarkan operator", "sewa menara baru", "tambah operator"]):
            for row in workflows:
                if any(w in row[1].lower() for w in ["onboard", "klien", "kontrak", "mla"]) or ("daftar" in row[1].lower() and "operator" in row[1].lower()):
                    return {
                        "workflow_id": row[0],
                        "send_email": True,
                        "recipient_email": extracted_email
                    }

        # 1. Check for Finance Workflows (Schema C) - If permitted for this tenant
        if not is_onboarding_intent and (
            any(k in prompt_lower for k in ["pendapatan sewa", "pendapatan menara", "pendapatan operator", "revenue", "invoice operator", "tagihan operator", "invoice sewa", "tagihan sewa", "laporan pendapatan", "status pembayaran"])
            or ("invoice" in prompt_lower and any(w in prompt_lower for w in ["sewa", "operator", "menara", "status"]))
            or ("tagihan" in prompt_lower and any(w in prompt_lower for w in ["sewa", "operator", "menara"]))
        ):
            for row in workflows:
                if row[0] == "WF-004" or any(w in row[1].lower() for w in ["pendapatan", "revenue", "invoice"]):
                    return {"workflow_id": row[0], "send_email": False}

        if any(k in prompt_lower for k in ["beban operasional", "opex", "listrik pln", "beban listrik", "sewa lahan", "biaya genset", "beban site"]):
            for row in workflows:
                if row[0] == "WF-005" or any(w in row[1].lower() for w in ["beban listrik", "opex", "sewa lahan"]):
                    return {"workflow_id": row[0], "send_email": False}

        if any(k in prompt_lower for k in ["arus kas", "cash flow", "cashflow", "kas masuk", "kas keluar", "saldo kas", "net cash flow"]):
            for row in workflows:
                if row[0] == "WF-006" or any(w in row[1].lower() for w in ["arus kas", "cash flow", "cashflow"]):
                    return {"workflow_id": row[0], "send_email": False}

        # 2. Check for specific item stock query (only if explicitly asking stock check)
        is_stock_query = (
            any(k in prompt_lower for k in ["cek stok", "lihat stok", "status stok", "cek ketersediaan", "stok barang"])
            or ("berapa" in prompt_lower and any(w in prompt_lower for w in ["stok", "sisa", "unit", "persediaan", "tersedia", "ada barang", "part", "item", "produk"]))
        ) and not any(k in prompt_lower for k in ["pdf", "dokumen", "pr", "restock", "buatkan"])

        if is_stock_query:
            for row in workflows:
                if row[0] == "WF-005" or "spesifik" in row[1].lower() or "cek" in row[1].lower():
                    clean_target = prompt.lower().replace("berapa", "").replace("cek stok", "").replace("stok", "").strip()
                    return {"workflow_id": row[0], "target_item_name": clean_target, "send_email": False}
        
        # 3. Check for threshold update
        if any(k in prompt_lower for k in ["threshold", "ambang", "ubah batas"]):
            for row in workflows:
                if row[0] == "WF-002" or "threshold" in row[1].lower():
                    return {"workflow_id": row[0], "threshold_updates": [], "send_email": False}
        
        # 4. Check for warehouse audit
        if any(k in prompt_lower for k in ["seluruh gudang", "audit gudang", "audit", "rekap seluruh", "rekap seluruh inventaris"]):
            for row in workflows:
                if row[3] == tenant_id and "audit" in row[1].lower():
                    return {"workflow_id": row[0], "send_email": False}
            for row in workflows:
                if row[0] in ["WF-004", "WF-B01"] or "audit" in row[1].lower():
                    return {"workflow_id": row[0], "send_email": False}
                    
        # 5. Check for restock / pengadaan / menipis / kritis / PR
        is_restock_intent = any(k in prompt_lower for k in [
            "buatkan pr", "bikin pr", "terbitkan pr", "buat draft pr", "buatkan draf pr", "draf pr", "draft pr",
            "proses pengadaan", "pipeline pengadaan", "restock material", "pesan material", "order material",
            "restock", "menipis", "kritis", "pengadaan", "pesan barang", "beli barang", "order barang", "purchase requisition", "kehabisan"
        ]) or bool(re.search(r'\bpr\b', prompt_lower))

        if is_restock_intent:
            send_mail = bool(extracted_email) or ("email" in prompt_lower or "notifikasi" in prompt_lower)
            # Check tenant-specific restock workflow first
            for row in workflows:
                if len(row) > 3 and row[3] == tenant_id and any(w in row[1].lower() for w in ["restock", "pengadaan"]):
                    res = {"workflow_id": row[0], "send_email": send_mail, "threshold_updates": [], "target_item_name": None}
                    if extracted_email:
                        res["recipient_email"] = extracted_email
                    return res

            # Fallback to global restock if allowed
            for row in workflows:
                if any(w in row[1].lower() for w in ["restock", "pengadaan"]) or bool(re.search(r'\bpr\b', row[1].lower())):
                    res = {"workflow_id": row[0], "send_email": send_mail, "threshold_updates": [], "target_item_name": None}
                    if extracted_email:
                        res["recipient_email"] = extracted_email
                    return res

        # 6. ANTI-HALUSINASI GUARDRAIL:
        # If no recognized intent matched, return workflow_id: None! Do NOT pick a default workflow!
        return {
            "workflow_id": None,
            "is_unrelated": True,
            "send_email": False,
            "threshold_updates": [],
            "target_item_name": None
        }
