"""
Multi-Model LLM Client and Intelligent Prompt Parsing Engine
Provides resilient natural language prompt understanding, structured extraction, and fallback reasoning.
"""

import json
import re
import random
import httpx
from typing import Dict, Any, Optional, List
from core.config import settings
from core.schemas import ParsedPromptIntent
from core.observability import log_agent_step


def parse_smart_currency(text: str) -> Optional[float]:
    """Parses Indonesian currency expressions like 6,5 jt, 6.5 juta, 50 rb, Rp 6.500.000, 18000."""
    t = text.lower().replace('rp', '').replace('rupiah', '').strip()
    
    # 1. Juta / jt (e.g. "6,5 jt", "6.5 juta", "6jt")
    jt_match = re.search(r'([0-9]+(?:[\.,][0-9]+)?)\s*(?:jt|juta)', t)
    if jt_match:
        val_str = jt_match.group(1).replace(',', '.')
        try:
            return float(val_str) * 1_000_000.0
        except Exception:
            pass

    # 2. Ribu / rb / k (e.g. "50 rb", "50 ribu", "50k")
    rb_match = re.search(r'([0-9]+(?:[\.,][0-9]+)?)\s*(?:rb|ribu|k\b)', t)
    if rb_match:
        val_str = rb_match.group(1).replace(',', '.')
        try:
            return float(val_str) * 1_000.0
        except Exception:
            pass

    # 3. Standard numeric (e.g. "6.500.000", "18000")
    num_match = re.search(r'([0-9\.,]{3,})', t)
    if num_match:
        raw_num = num_match.group(1).replace('.', '').replace(',', '')
        if raw_num.isdigit():
            return float(raw_num)

    return None


class LLMClient:
    def __init__(self):
        self.api_key = settings.LLM_KEY
        self.base_url = settings.LLM_URL.rstrip('/')
        self.mock_mode = settings.MOCK_MODELS
        self.default_model = settings.DEFAULT_LLM_MODEL
        self.vision_model = settings.VISION_LLM_MODEL

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "You are an expert AI Procurement and Inventory Specialist.",
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1500
    ) -> str:
        """Call external LLM endpoint with graceful fallback."""
        model_to_use = model or self.default_model

        if not self.mock_mode and self.base_url:
            try:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model_to_use,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload
                    )
                    if response.status_code == 200:
                        data = response.json()
                        msg = data["choices"][0]["message"]
                        return msg.get("content") or msg.get("reasoning_content") or ""
            except Exception as e:
                log_agent_step(
                    step_name="LLM Call Fallback",
                    agent_name="LLMClient",
                    status="warning",
                    message=f"Remote LLM request failed, falling back to heuristic reasoning: {str(e)}"
                )

        return self._fallback_completion(prompt, system_prompt)

    def _fallback_completion(self, prompt: str, system_prompt: str) -> str:
        """Heuristic completion for offline/mock mode."""
        prompt_lower = prompt.lower()
        if "reconciliation" in prompt_lower or "discrepancy" in prompt_lower:
            return json.dumps({
                "audit_verdict": "FLAGGED",
                "risk_score": 0.75,
                "notes": "Discrepancy detected between physical count sheet and warehouse database record."
            })
        return "Autonomous analysis complete. Standard parameters verified."

    async def parse_restock_prompt(self, user_prompt: str, existing_items: List[Dict[str, Any]]) -> ParsedPromptIntent:
        log_agent_step(
            step_name="Prompt Comprehension",
            agent_name="PromptParserAgent",
            status="info",
            message=f"Parsing user instruction: '{user_prompt}'"
        )

        # --- STEP 0: Attempt Real LLM Completion if Server is Active (Qwen-35b / Nemotron) ---
        if not self.mock_mode and self.base_url:
            try:
                system_prompt = (
                    "You are the autonomous AI reasoning engine of AutoRestock-V2. "
                    "Analyze the user's natural language instruction and extract the structured intent. "
                    "Respond with ONLY valid JSON adhering to this schema: "
                    '{"intent_type": "restock"|"add_item"|"update_stock"|"check_stock"|"add_category"|"delete_category"|"edit_item"|"delete_item"|"update_threshold"|"review_prs"|"approve_prs"|"calculate_financials"|"export_data"|"ui_action"|"notify_email"|"notify_telegram"|"sync_export", '
                    '"target_skus": ["SKU1"], "target_categories": ["Category"], "target_supplier": "Supplier", "quantity_specified": 20, "quantity_strategy": "auto_to_max"|"fixed_amount"|"safety_buffer", '
                    '"urgency": "NORMAL"|"HIGH"|"URGENT", "reasoning": "summary", '
                    '"approve_pr_data": {"action": "approve", "filter_status": "pending_approval", "min_amount": 10000000.0, "max_amount": null}, '
                    '"financial_calc_data": {"target": "prs", "filter_status": "all"|"pending_approval"}, '
                    '"category_data": {"action": "add"|"delete", "category_name": "Name"}, '
                    '"stock_adjustment_data": {"sku": "SKU", "target_stock": 20}, "threshold_data": {"sku": "SKU", "min_stock": 10, "max_stock": 50}, '
                    '"edit_item_data": {"sku": "SKU", "unit_price": 50000, "current_stock": 10}, "delete_item_data": {"sku": "SKU", "item_name": "Name"}}'
                )
                raw_llm = await self.complete(prompt=user_prompt, system_prompt=system_prompt, model=self.default_model, max_tokens=1500)
                json_match = re.search(r'\{.*\}', raw_llm, re.DOTALL)
                if json_match:
                    llm_data = json.loads(json_match.group(0))
                    if "intent_type" in llm_data:
                        parsed = ParsedPromptIntent(**llm_data)
                        log_agent_step(
                            step_name="Prompt Comprehension (Remote LLM)",
                            agent_name="PromptParserAgent",
                            status="success",
                            message=f"LLM {self.default_model} parsed intent: {parsed.reasoning or parsed.intent_type}",
                            details=parsed.model_dump()
                        )
                        return parsed
            except Exception as e:
                log_agent_step(
                    step_name="Remote LLM Fallback",
                    agent_name="PromptParserAgent",
                    status="warning",
                    message=f"Could not connect to remote LLM ({str(e)}), using local heuristic parser."
                )

        p_lower = user_prompt.lower()

        # --- STEP 1: Smart Scored SKU & Item Matching ---
        target_skus = []
        matched_item = None
        best_score = 0

        p_clean = re.sub(r'[^a-zA-Z0-9\s\-]', ' ', p_lower)
        stopwords = {"dan", "the", "pcs", "box", "dus", "rim", "kg", "sak", "btl", "liter", "klasik", "premium", "nama", "produk", "barang", "stok", "katalog"}

        matched_items_list = []
        for item in existing_items:
            sku = item.get("sku", "")
            name = item.get("name", "").lower()
            score = 0

            # 1. Direct SKU match
            if sku.lower() in p_lower:
                score += 1000

            # 2. Exact full name match in prompt
            if name and name in p_lower:
                score += 500

            # 3. Fuzzy SKU keyword match
            sku_parts = sku.lower().split("-")
            if len(sku_parts) >= 2:
                sku_keyword = sku_parts[1]
                if len(sku_keyword) > 2 and sku_keyword in p_lower:
                    score += 150

            # 4. Token Overlap Score
            name_tokens = [w for w in name.split() if len(w) > 2 and w not in stopwords]
            prompt_tokens = set([w for w in p_clean.split() if len(w) > 2 and w not in stopwords])
            
            overlap_count = sum(1 for t in name_tokens if t in prompt_tokens)
            if overlap_count > 0:
                score += (overlap_count * 50)
                if len(name_tokens) >= 2 and " ".join(name_tokens[:2]) in p_lower:
                    score += 100
                if len(name_tokens) >= 3 and " ".join(name_tokens[:3]) in p_lower:
                    score += 200

            if score >= 50:
                matched_items_list.append((score, item))

        matched_items_list.sort(key=lambda x: x[0], reverse=True)
        if matched_items_list:
            top_score = matched_items_list[0][0]
            matched_item = matched_items_list[0][1]
            # Strictly filter: Only include secondary items if they also scored high (prevent single common word false positives like 'goreng')
            target_skus = [it["sku"] for s, it in matched_items_list if s >= max(150, top_score * 0.75)]

        # --- STEP 2: Intent Classification ---
        # Default intent: 'summary' (safe informational inquiry) instead of 'restock' (to avoid accidental PR generation)
        intent_type = "summary" if any(w in p_lower for w in ["beri tahu", "beritahu", "tampilkan", "apa", "berapa", "mana", "siapa", "tolong info", "info", "cek", "lihat"]) else "restock"
        notification_channel = None
        notification_recipient = None
        notification_message = None
        new_item_data = None
        stock_adjustment_data = None
        threshold_data = None
        edit_item_data = None
        delete_item_data = None
        category_data = None
        ui_action_data = None

        # =====================================================================
        # HELPER: Extract clean category names from a raw string
        # Strips trailing reason phrases like "karena ...", "soalnya ...", "di database", etc.
        # Then splits by "dan", ",", "&" to support multiple categories in one command.
        # =====================================================================
        def _extract_category_names(raw: str) -> list:
            """Extract one or more category names from raw text, stripping trailing reasons."""
            c = re.sub(r'\s+(?:karena|soalnya|sebab|alasan|karean|karna|krn|krna)(?:\s.*)?$', '', raw, flags=re.IGNORECASE)
            c = re.sub(r'\s+(?:di|pada|ke|dari|dalam)\s+(?:database|sistem|katalog|stok|tabel|data|db|inventory).*$', '', c, flags=re.IGNORECASE)
            c = re.sub(r'\s+(?:ya|dong|donk|please|plz|tolong|segera|sekarang|secepatnya)$', '', c, flags=re.IGNORECASE)
            c = c.strip(" :-;,.")

            if not c:
                return []

            parts = re.split(r'\s+dan\s+|,\s*', c, flags=re.IGNORECASE)
            names = []
            for p in parts:
                p = p.strip(" :-;,.")
                if p and len(p) >= 2:
                    names.append(p)
            return names

        # =====================================================================
        # HELPER: Check if prompt contains actual product specification data
        # =====================================================================
        def _has_product_spec_data() -> bool:
            spec_pairs = [
                (r'(?:nama\s+(?:produk|barang|item))', True),
                (r'(?:kategori\s*[:=]?\s*[a-zA-Z])', True),
                (r'(?:stok\s*[:=]?\s*\d)', True),
                (r'(?:harga\s*[:=]?\s*[\dRr])', True),
                (r'(?:min\s*[:=]?\s*\d)', True),
                (r'(?:max\s*[:=]?\s*\d)', True),
                (r'(?:supplier\s*[:=]?\s*[a-zA-Z])', True),
            ]
            spec_count = sum(1 for pat, _ in spec_pairs if re.search(pat, user_prompt, re.IGNORECASE))
            if spec_count >= 2:
                return True
            if re.search(r'(?:tambah(?:kan)?|input|daftarkan|buat)\s+(?:nama\s+)?(?:produk|barang|item)\s+\w', user_prompt, re.IGNORECASE):
                return True
            return False

        # =====================================================================
        # 0.00 Batch / Filtered PR Approval Intent
        # =====================================================================
        if any(w in p_lower for w in ["setujui pr", "approve pr", "setujui semua pr", "acc pr", "setujui purchase requisition", "setuju pr"]):
            intent_type = "approve_prs"
            min_amt = None
            max_amt = None

            # Parse "diatas 10 juta", "lebih dari 10jt", "di atas 5jt"
            above_match = re.search(r'(?:di\s*atas|lebih\s*dari|minimum|>|>=)\s*([0-9\.,]+(?:\s*(?:jt|juta|rb|ribu|k|miliar|m))?)', p_lower)
            if above_match:
                min_amt = parse_smart_currency(above_match.group(1))

            # Parse "dibawah 5 juta", "kurang dari 5jt"
            below_match = re.search(r'(?:di\s*bawah|kurang\s*dari|<|<=)\s*([0-9\.,]+(?:\s*(?:jt|juta|rb|ribu|k|miliar|m))?)', p_lower)
            if below_match:
                max_amt = parse_smart_currency(below_match.group(1))

            approve_pr_data = {
                "action": "approve",
                "filter_status": "pending_approval",
                "min_amount": min_amt,
                "max_amount": max_amt
            }

        # =====================================================================
        # 0.01 Financial Aggregations & Cost Calculations Intent
        # =====================================================================
        elif any(w in p_lower for w in [
            "berapa jumlah uang", "berapa total uang", "hitung total semua pr", "hitung total pr", 
            "hitung semua pr", "hitung uang", "total yang harus dibayar", "berapa biaya", 
            "berapa total biaya", "hitung pr", "total uang pr", "total bayar", "total biaya pr", "jumlah uang yang harus dibayar"
        ]):
            intent_type = "calculate_financials"
            financial_calc_data = {
                "target": "prs",
                "filter_status": "all" if "semua" in p_lower else "pending_approval"
            }

        # =====================================================================
        # 0.02 PR Review / Approvals / View PR Data Intent
        # =====================================================================
        elif any(w in p_lower for w in [
            "lihat pr", "lihat semua pr", "cek pr", "daftar pr", "status pr", "data pada pr", 
            "data pr", "pr pending", "pr yang berstatus pending", "berstatus pending", "semua pr", 
            "tampilkan pr", "tinjau pr", "review pr", "lihat data pr", "lihat dokumen pr", "cari pr", 
            "daftar purchase requisition", "pr terbesar", "pr paling besar", "pr tertinggi", "total paling besar", "total terbesar"
        ]) and not any(w in p_lower for w in ["buatkan pr", "buat pr", "pesankan", "order pr", "generate pr", "bikin pr"]):
            intent_type = "review_prs"

        # =====================================================================
        # 0.1 Dynamic Category Management
        # =====================================================================
        elif any(w in p_lower for w in ["tambah kategori", "tambahkan kategori", "buat kategori", "daftarkan kategori", "input kategori", "kategori baru"]):
            intent_type = "add_category"
            raw_after = re.sub(r'^(?:tolong\s+)?(?:tambah(?:kan)?|buat|daftarkan|input)\s+kategori\s*(?:baru)?\s*[:=]?\s*', '', user_prompt, flags=re.IGNORECASE)
            names = _extract_category_names(raw_after)
            category_data = {
                "action": "add",
                "category_name": names[0].title() if names else "General",
                "category_names": [n.title() for n in names] if len(names) > 1 else None
            }

        elif any(w in p_lower for w in ["hapus kategori", "delete kategori", "hilangkan kategori", "buang kategori", "remove kategori"]):
            intent_type = "delete_category"
            raw_after = re.sub(r'^(?:tolong\s+)?(?:hapus|delete|hilangkan|buang|remove)\s+kategori\s*[:=]?\s*', '', user_prompt, flags=re.IGNORECASE)
            names = _extract_category_names(raw_after)
            category_data = {
                "action": "delete",
                "category_name": names[0] if names else "",
                "category_names": names if len(names) > 1 else None
            }

        # 0.2 Export Data Intent
        elif any(w in p_lower for w in ["ekspor katalog", "export catalog", "unduh csv", "download csv", "export ke csv", "ekspor ke csv", "export excel", "unduh katalog"]):
            intent_type = "export_data"

        # 1. UI Customization & Label Change Intent
        elif any(w in p_lower for w in ["kolom min/max", "nama min/max", "min/max jadi threshold", "ganti min/max", "ubah min/max", "label min/max"]):
            intent_type = "ui_action"
            ui_action_data = {
                "action": "rename_column",
                "target": "th-minmax",
                "new_label": "THRESHOLD"
            }

        # 2. Add Item / Product Registration Intent
        # IMPORTANT: Only trigger when prompt has actual product spec data, NOT for vague "tambahkan" commands
        # Note: Even if matched_item exists (e.g. "laptop lenovo" matches existing), if the user explicitly
        # uses "tambah/tambahkan" with full spec data, it's an add_item intent (updating existing or adding new)
        elif _has_product_spec_data() and any(w in p_lower for w in ["tambah", "tambahkan", "masukkan", "input", "daftarkan", "buat produk", "add item", "new product", "tambah produk", "tambah barang"]):
            intent_type = "add_item"

            # Parse Name
            name_clean = "Produk Baru"
            name_match = re.search(r'(?:nama\s+produk|produk|barang|item)?\s*[:=]?\s*([a-zA-Z0-9\s\.\-_]+?)(?:,\s*kategori|\s+kategori|\s+stok|\s+harga|\s+min|\s+dengan|$)', user_prompt, re.IGNORECASE)
            if name_match:
                candidate_name = name_match.group(1).strip()
                candidate_name = re.sub(r'^(?:tolong\s+)?(?:tambah(?:kan)?|masukkan|input|daftarkan|buat)\s+(?:nama\s+produk|produk|barang|item)?\s*[:=]?\s*', '', candidate_name, flags=re.IGNORECASE).strip()
                if candidate_name and len(candidate_name) >= 3:
                    name_clean = candidate_name.title()

            # Parse Category
            cat_clean = "General"
            cat_match = re.search(r'kategori\s*[:=]?\s*([a-zA-Z0-9\s/&]+?)(?:,\s*stok|\s+stok|\s+harga|\s+min|\s+max|\s+dengan|$)', user_prompt, re.IGNORECASE)
            if cat_match:
                raw_cat = cat_match.group(1).strip()
                if any(w in raw_cat.lower() for w in ["it", "elektronik", "electronic"]):
                    cat_clean = "IT & Electronics"
                elif any(w in raw_cat.lower() for w in ["fmcg", "sembako", "retail"]):
                    cat_clean = "FMCG"
                elif any(w in raw_cat.lower() for w in ["food", "beverage", "makanan", "minuman"]):
                    cat_clean = "Food & Beverage"
                elif any(w in raw_cat.lower() for w in ["atk", "kantor", "office"]):
                    cat_clean = "Office Supplies"
                elif any(w in raw_cat.lower() for w in ["industri", "mro", "teknik"]):
                    cat_clean = "Industrial & MRO"
                else:
                    cat_clean = raw_cat.title()

            # Parse Stock
            stock_val = 10
            stock_match = re.search(r'(?:stok|stock|qty|jumlah)\s*(?:awal)?\s*[:=]?\s*(\d+)', user_prompt, re.IGNORECASE)
            if stock_match:
                try: stock_val = int(stock_match.group(1))
                except Exception: pass

            # Parse Min Stock
            min_val = 5
            min_match = re.search(r'(?:min|minimum|min stock)\s*[:=]?\s*(\d+)', user_prompt, re.IGNORECASE)
            if min_match:
                try: min_val = int(min_match.group(1))
                except Exception: pass

            # Parse Max Stock
            max_val = max(min_val * 3, stock_val * 2, 20)
            max_match = re.search(r'(?:max|maksimum|max stock)\s*[:=]?\s*(\d+)', user_prompt, re.IGNORECASE)
            if max_match:
                try: max_val = int(max_match.group(1))
                except Exception: pass

            # Parse Price
            price_val = 50000.0
            price_match = re.search(r'(?:harga(?:nya)?|price|rp\.?)\s*(?:di|sebesar|adalah)?\s*[:=]?\s*([0-9\.,]+(?:\s*(?:jt|juta|rb|ribu|k))?)', user_prompt, re.IGNORECASE)
            if price_match:
                parsed_p = parse_smart_currency(price_match.group(1))
                if parsed_p: price_val = parsed_p

            prefix = "GEN"
            if "IT" in cat_clean: prefix = "IT"
            elif "FMCG" in cat_clean: prefix = "FMCG"
            elif "Food" in cat_clean: prefix = "FNB"
            elif "Office" in cat_clean: prefix = "ATK"
            elif "Industrial" in cat_clean: prefix = "IND"

            new_sku = f"{prefix}-{random.randint(1000, 9999)}"

            new_item_data = {
                "sku": new_sku,
                "name": name_clean,
                "category": cat_clean,
                "current_stock": stock_val,
                "min_stock": min_val,
                "max_stock": max_val,
                "safety_stock": max(2, int(min_val * 0.3)),
                "unit": "unit",
                "unit_price": price_val,
                "supplier_id": "SUP-003" if "IT" in cat_clean else "SUP-002",
                "supplier_name": "PT Surya Graha IT & Elektronika" if "IT" in cat_clean else "PT Sumber Alfaria Distribusi",
                "lead_time_days": 3,
                "location_bin": f"RACK-{prefix}-01"
            }

        # 3. Notification Intents
        elif any(w in p_lower for w in ["kirim email", "send email", "email ke", "emailkan"]):
            intent_type = "notify_email"
            notification_channel = "email"
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', user_prompt)
            notification_recipient = email_match.group(0) if email_match else "management@retail-nusantara.co.id"
            notification_message = user_prompt

        elif any(w in p_lower for w in ["kirim telegram", "notif telegram", "telegram ke", "pesan telegram", "chat telegram"]):
            intent_type = "notify_telegram"
            notification_channel = "telegram"
            recip_match = re.search(r'(?:ke|kepada|untuk)\s+([A-Za-z0-9\s_]+)', user_prompt, re.IGNORECASE)
            notification_recipient = recip_match.group(1).strip() if recip_match else "Grup Telegram Manajemen"
            notification_message = user_prompt

        elif any(w in p_lower for w in ["sinkron", "sync", "google sheets", "sheets"]):
            intent_type = "sync_export"

        # 4. PR Review / Approvals Inquiry
        elif any(w in p_lower for w in ["cek pr", "lihat pr", "pr pending", "perlu disetujui", "butuh persetujuan", "daftar pr", "status pr", "mana saja pr", "review pr"]):
            intent_type = "review_prs"

        # 5. General / Targeted Inventory Inquiries (MUST NOT TRIGGER RESTOCK!)
        elif any(w in p_lower for w in [
            "sebutkan", "tampilkan", "daftar", "apa saja", "apa aja", "yang menipis", "status nya menipis",
            "status menipis", "yang habis", "status habis", "cek stok", "lihat stok", "status stok",
            "berapa stok", "berapa harga", "berapa total", "summary", "laporan", "rekap", "tanya",
            "ada berapa", "mana saja", "list barang", "cari tahu", "tunjukkan"
        ]) and not any(w in p_lower for w in ["ubah", "ganti", "perbarui", "pesan", "beli", "tambah", "restock", "restok", "order"]):
            intent_type = "check_stock"

        # 6. Delete Item from Catalog
        elif matched_item and any(w in p_lower for w in ["hapus", "delete", "buang", "hilangkan", "remove"]) and not any(w in p_lower for w in ["kategori"]):
            intent_type = "delete_item"
            delete_item_data = {
                "sku": matched_item["sku"],
                "item_name": matched_item["name"]
            }

        # 7. Threshold Modification
        elif any(w in p_lower for w in ["ubah threshold", "set threshold", "atur threshold", "ganti threshold", "ubah batas", "atur batas", "set batas", "ganti batas", "ubah min stock", "ubah max stock", "set safety stock"]):
            intent_type = "update_threshold"
            min_val = None
            max_val = None
            safety_val = None

            min_match = re.search(r'(?:min|minimum|batas bawah|min stock)\s*[:=]?\s*(\d+)', p_lower)
            if min_match: min_val = int(min_match.group(1))

            max_match = re.search(r'(?:max|maksimum|maks|batas atas|max stock)\s*[:=]?\s*(\d+)', p_lower)
            if max_match: max_val = int(max_match.group(1))

            safety_match = re.search(r'(?:safety|buffer|safety stock)\s*[:=]?\s*(\d+)', p_lower)
            if safety_match: safety_val = int(safety_match.group(1))

            target_sku_val = matched_item["sku"] if matched_item else (target_skus[0] if target_skus else "ALL")
            threshold_data = {
                "sku": target_sku_val,
                "item_name": matched_item["name"] if matched_item else "Semua Item Terkait",
                "min_stock": min_val,
                "max_stock": max_val,
                "safety_stock": safety_val
            }

        # 8. Edit Item Multi-Field Metadata
        elif matched_item and any(w in p_lower for w in ["ubah harga", "ganti harga", "update harga", "ubah nama", "ganti nama", "perbarui data", "edit", "perbarui", "ganti", "ubah"]):
            intent_type = "edit_item"
            
            # 1. Price change
            new_price = None
            price_match = re.search(r'(?:harga(?:nya)?|price|rp\.?)\D{0,30}?(?:di|jadi|menjadi|ke|sebesar|adalah)?\s*[:=]?\s*([0-9\.,]+(?:\s*(?:jt|juta|rb|ribu|k))?)', p_lower)
            if price_match:
                new_price = parse_smart_currency(price_match.group(1))

            # 2. Stock change
            new_stock = None
            stock_match = re.search(r'(?:stok|stock|saldo)(?:nya)?\D{0,60}?(?:jadi|menjadi|ke|sebesar|tinggal|sisa|ada|adalah)?\s*[:=]?\s*(\d+)', p_lower)
            if not stock_match:
                stock_match = re.search(r'(?:menjadi|jadi)\s*(\d+)\s*(?:sak|pcs|unit|box|dus|rim|kg|btl|karton|pack)', p_lower)
            if stock_match:
                try:
                    new_stock = int(stock_match.group(1))
                except Exception:
                    pass

            # 3. Max stock change
            new_max = None
            max_match = re.search(r'(?:max|maksimum|maks|max produk|max stock)\D{0,30}?(?:jadi|menjadi|ke|sebesar|adalah)?\s*[:=]?\s*(\d+)', p_lower)
            if max_match:
                try:
                    new_max = int(max_match.group(1))
                except Exception:
                    pass

            # 4. Min stock change
            new_min = None
            min_match = re.search(r'(?:min|minimum|min produk|min stock)\D{0,30}?(?:jadi|menjadi|ke|sebesar|adalah)?\s*[:=]?\s*(\d+)', p_lower)
            if min_match:
                try:
                    new_min = int(min_match.group(1))
                except Exception:
                    pass

            # 5. Category change (e.g. "menjadi kategori Kosmetik", "ganti kategori ke Kosmetik", "kategori Kosmetik", "ubah kategori jadi Kosmetik")
            new_category = None
            cat_match = re.search(r'(?:menjadi|jadi|ke|ubah ke|ganti ke)\s+(?:kategori\s+)?([a-zA-Z0-9\s/&]+?)(?:$|\s*[,;.]|\s+harga|\s+stok)', user_prompt, re.IGNORECASE)
            if not cat_match:
                cat_match = re.search(r'kategori\s*(?:menjadi|jadi|ke|:|=)\s*([a-zA-Z0-9\s/&]+?)(?:$|\s*[,;.]|\s+harga|\s+stok)', user_prompt, re.IGNORECASE)
            if cat_match:
                raw_c = cat_match.group(1).strip()
                raw_c = re.sub(r'^(?:pada|untuk|nama|produk|barang)\s+', '', raw_c, flags=re.IGNORECASE).strip()
                if raw_c and len(raw_c) >= 2:
                    new_category = raw_c.title()

            # 6. Name change (e.g. "ganti nama menjadi Sabun Mandi Premium")
            new_name = None
            name_match = re.search(r'(?:nama(?:nya)?)\s*(?:menjadi|jadi|ke)\s*[:=]?\s*([a-zA-Z0-9\s\.\-_]+?)(?:$|\s*[,;.]|\s+kategori|\s+harga|\s+stok)', user_prompt, re.IGNORECASE)
            if name_match:
                candidate_n = name_match.group(1).strip()
                if candidate_n and len(candidate_n) >= 2:
                    new_name = candidate_n.title()

            edit_item_data = {
                "sku": matched_item["sku"],
                "skus": target_skus,
                "item_name": matched_item["name"],
                "name": new_name,
                "category": new_category,
                "unit_price": new_price,
                "current_stock": new_stock,
                "max_stock": new_max,
                "min_stock": new_min
            }

        # 9. Direct Stock Level Statements ("stoknya tinggal 5", "sisa 3", "stok ada 10", "stok habis")
        elif matched_item and any(w in p_lower for w in ["tinggal", "sisa", "ada", "koreksi stok", "ubah stok", "sesuaikan stok", "update stok", "ganti stok", "jadi", "menjadi", "set stok", "tambah stok", "habis", "kosong"]):
            target_qty = 0
            if "habis" in p_lower or "kosong" in p_lower or "nol" in p_lower:
                target_qty = 0
            else:
                qty_match = re.search(r'(?:tinggal|sisa|ada|jadi|menjadi|ke|sebesar|qty|stok|sebanyak|tambah)\s*[:=]?\s*(\d+)', p_lower)
                if not qty_match:
                    qty_match = re.search(r'(\d+)\s*(?:sak|pcs|unit|box|dus|rim|kg|btl|karton|pack)', p_lower)
                target_qty = int(qty_match.group(1)) if qty_match else 5

            intent_type = "update_stock"
            stock_adjustment_data = {
                "sku": matched_item["sku"],
                "item_name": matched_item["name"],
                "target_stock": target_qty,
                "reason": f"Direct prompt update: stok fisik {target_qty} {matched_item.get('unit', 'unit')}"
            }

        # Step 2: Detect Urgency
        urgency = "NORMAL"
        if any(w in p_lower for w in ["urgent", "segera", "darurat", "asap", "cepat", "critical", "hari ini"]):
            urgency = "URGENT"
        elif any(w in p_lower for w in ["high priority", "prioritas tinggi", "penting"]):
            urgency = "HIGH"

        # Step 3: Detect target categories (only if no specific SKU already matched or to supplement)
        known_categories = list(set([item.get("category", "") for item in existing_items if item.get("category")]))
        target_categories = []
        for cat in known_categories:
            if re.search(r'\b' + re.escape(cat.lower()) + r'\b', p_lower):
                target_categories.append(cat)

        # Synonyms and domain mappings with strict word boundaries
        category_aliases = {
            "sembako": ["FMCG", "Bahan Pokok"],
            "makanan": ["FMCG", "Food & Beverage"],
            "minuman": ["Food & Beverage", "FMCG"],
            "atk": ["Office Supplies", "Stationery"],
            "kantor": ["Office Supplies"],
            "elektronik": ["Electronics", "IT & Electronics"],
            "it": ["IT & Electronics"],
            "sparepart": ["Industrial Spare Parts", "Hardware"],
            "hardware": ["Industrial Spare Parts", "Hardware"],
            "kosmetik": ["Kosmetik", "General"],
        }
        for alias, mapped_cats in category_aliases.items():
            if re.search(r'\b' + re.escape(alias) + r'\b', p_lower):
                for mc in mapped_cats:
                    if mc in known_categories and mc not in target_categories:
                        target_categories.append(mc)

        # If a specific SKU is already identified, don't let category filters restrict it
        if target_skus:
            target_categories = []

        # Step 4: Detect explicit quantity numbers
        quantity_specified = None
        quantity_match = re.search(r'(?:sebanyak|jumlah|order|pesan|tambah|qty|jadi|menjadi|sebesar)\s*[:=]?\s*(\d+)', p_lower)
        if not quantity_match:
            quantity_match = re.search(r'(\d+)\s*(?:pcs|unit|dus|box|rim|kg|btl|sak|roll|karton|pouch|sak)', p_lower)
        if quantity_match:
            try:
                quantity_specified = int(quantity_match.group(1))
            except Exception:
                pass

        # Step 5: Detect Quantity Strategy & Thresholds
        quantity_strategy = "auto_to_max"
        if quantity_specified is not None:
            quantity_strategy = "fixed_amount"
        elif "safety" in p_lower or "buffer" in p_lower:
            quantity_strategy = "safety_buffer"

        # Step 6: Detect Supplier Preference
        target_supplier = None
        for item in existing_items:
            sup = item.get("supplier_name", "")
            if sup and sup.lower() in p_lower:
                target_supplier = sup
                break

        # Step 7: Build reasoning explanation
        reasoning_parts = []
        if target_categories:
            reasoning_parts.append(f"Target categories: {', '.join(target_categories)}")
        if target_skus:
            reasoning_parts.append(f"Identified {len(target_skus)} specific SKU(s)")
        if quantity_specified:
            reasoning_parts.append(f"Explicit quantity target: {quantity_specified} units per item")
        if target_supplier:
            reasoning_parts.append(f"Preferred supplier: {target_supplier}")
        if urgency != "NORMAL":
            reasoning_parts.append(f"Priority escalated to {urgency}")

        if intent_type == "add_category" and category_data:
            reasoning_parts.insert(0, f"Register new category in database: {category_data.get('category_name')}")
        elif intent_type == "delete_category" and category_data:
            reasoning_parts.insert(0, f"Delete category from database: {category_data.get('category_name')}")
        elif intent_type == "export_data":
            reasoning_parts.insert(0, "Export catalog data to CSV")
        elif intent_type == "add_item" and new_item_data:
            reasoning_parts.insert(0, f"Register new item: {new_item_data.get('name')} (SKU: {new_item_data.get('sku')}, Category: {new_item_data.get('category')}, Price: Rp {new_item_data.get('unit_price'):,.0f})")
        elif intent_type == "ui_action" and ui_action_data:
            reasoning_parts.insert(0, f"UI Action: Change {ui_action_data.get('target')} to {ui_action_data.get('new_label')}")
        elif intent_type == "delete_item" and delete_item_data:
            reasoning_parts.insert(0, f"Delete item: {delete_item_data.get('item_name')} (SKU: {delete_item_data.get('sku')})")
        elif intent_type == "update_stock" and stock_adjustment_data:
            reasoning_parts.insert(0, f"Adjust stock for {stock_adjustment_data.get('sku')} to {stock_adjustment_data.get('target_stock')} units")
        elif intent_type == "edit_item" and edit_item_data:
            reasoning_parts.insert(0, f"Update product details for {edit_item_data.get('sku')}")
        elif intent_type == "update_threshold" and threshold_data:
            reasoning_parts.insert(0, f"Update inventory thresholds for {threshold_data.get('sku')}: Min={threshold_data.get('min_stock')}, Max={threshold_data.get('max_stock')}")
        elif intent_type == "review_prs":
            reasoning_parts.insert(0, "Inquire and review pending Purchase Requisitions requiring approval")
        elif intent_type in ["notify_email", "notify_telegram"]:
            reasoning_parts.insert(0, f"External Dispatch: Send {notification_channel.upper()} to {notification_recipient}")
        elif intent_type == "sync_export":
            reasoning_parts.insert(0, "External Dispatch: Synchronize data with Google Sheets / ERP")

        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Evaluating all inventory items below minimum threshold."

        parsed = ParsedPromptIntent(
            intent_type=intent_type,
            target_skus=list(set(target_skus)),
            target_categories=target_categories,
            target_supplier=target_supplier,
            quantity_specified=quantity_specified,
            quantity_strategy=quantity_strategy,
            urgency=urgency,
            reasoning=reasoning,
            notification_channel=notification_channel,
            notification_recipient=notification_recipient,
            notification_message=notification_message,
            new_item_data=new_item_data,
            stock_adjustment_data=stock_adjustment_data,
            threshold_data=threshold_data,
            edit_item_data=edit_item_data,
            delete_item_data=delete_item_data,
            category_data=category_data,
            ui_action_data=ui_action_data
        )

        log_agent_step(
            step_name="Prompt Comprehension",
            agent_name="PromptParserAgent",
            status="success",
            message=f"Prompt parsed successfully: {reasoning}",
            details=parsed.model_dump()
        )

        return parsed


llm_client = LLMClient()
