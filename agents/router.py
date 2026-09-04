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


class SemanticRouter:
    @classmethod
    async def route_prompt(cls, prompt: str, tenant_id: str = "ALL") -> dict:
        """
        Matches user prompt strictly to a predefined workflow ID allowed for this tenant.
        Does NOT hallucinate or pick an arbitrary workflow if intent is out-of-scope.
        """
        conn = get_db_connection(read_only=True)
        workflows = conn.execute("""
            SELECT id, name, description, tenant_id 
            FROM workflows 
            WHERE tenant_id = ? OR tenant_id = 'ALL'
        """, [tenant_id]).fetchall()
        conn.close()
        
        if not workflows:
            return {
                "workflow_id": None,
                "send_email": False,
                "threshold_updates": [],
                "target_item_name": None
            }

        workflows_str = "\n".join([f"- ID: {row[0]}, Name: {row[1]}, Desc: {row[2]}" for row in workflows])
        
        system_prompt = f"""You are a Strict Semantic Router for an Enterprise Inventory & Restock system.
Match the user's prompt ONLY to one of the following permitted workflows:

{workflows_str}

If the user wants to register, add, or create a new inventory item, extract "new_item_data": {{"name": string, "category": string, "current_stock": int, "min_threshold": int, "max_threshold": int, "avg_daily_usage": float, "lead_time_days": int, "unit": string}} (extract whatever fields the user provided, leaving unmentioned fields out).
If the user wants to update a threshold, extract "threshold_updates": [{{"item_name": "name of item", "new_min_threshold": 100, "new_max_threshold": 300}}]. Include only the thresholds the user specified.
If the user specifies an item name to check, extract it as "target_item_name".
If the user explicitly asks to send an email, report, or notify via email, extract "send_email": true. Otherwise, "send_email": false.
If the user asks to generate, create, or compile a PDF, Purchase Requisition (PR), or document, you MUST match it to a restock workflow that creates PR documents (e.g. WF-001 or tenant-specific restock workflow like WF-A01, WF-B01, WF-C01), NOT a report-only workflow.

CRITICAL GUARDRAIL:
Do not assume any default workflow. If the prompt does NOT clearly relate to any of the workflows listed above (for example, chit-chat, poetry, general questions, unrelated tasks), you MUST return "workflow_id": null.

Output strictly valid JSON with exact keys: "workflow_id", "new_item_data" (optional object), "threshold_updates" (optional array), "target_item_name" (optional string), "send_email" (boolean).
"""
        gateway = ModelGateway()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        prompt_lower = prompt.lower()

        # Check for product registration intent first (only if user workflow has registration)
        if any(k in prompt_lower for k in ["tambah", "tambahkan", "daftar", "daftarkan", "registrasi", "masukkan produk", "tambah produk", "tambah barang", "tambahkan nama produk", "buat barang"]):
            for row in workflows:
                if any(w in row[1].lower() for w in ["daftar", "pendaftaran", "tambah", "registrasi", "register"]):
                    extracted_item = _extract_item_attributes_from_text(prompt)
                    return {
                        "workflow_id": row[0],
                        "new_item_data": extracted_item,
                        "send_email": False
                    }

        try:
            response_str = await gateway.chat_completion("qwen-35b", messages, temperature=0.1, response_format_json=True)
            json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if json_match:
                response_str = json_match.group(0)
            parsed = json.loads(response_str)
            # Verify parsed workflow_id is actually in the permitted list
            valid_ids = {r[0] for r in workflows}
            if parsed.get("workflow_id") in valid_ids:
                return parsed
            elif parsed.get("workflow_id") is None:
                return {
                    "workflow_id": None,
                    "send_email": False,
                    "threshold_updates": [],
                    "target_item_name": None
                }
        except Exception as e:
            print(f"[SEMANTIC ROUTER] LLM unavailable ({e}). Using intelligent heuristic matcher.")
            
        # 1. Check for specific item stock query (only if explicitly asking stock check)
        is_stock_query = (
            any(k in prompt_lower for k in ["cek stok", "lihat stok", "status stok", "cek ketersediaan", "stok barang"])
            or ("berapa" in prompt_lower and any(w in prompt_lower for w in ["stok", "sisa", "unit", "persediaan", "tersedia", "ada barang", "part", "item", "produk"]))
        ) and not any(k in prompt_lower for k in ["pdf", "dokumen", "pr", "restock", "buatkan"])

        if is_stock_query:
            for row in workflows:
                if row[0] == "WF-005" or "spesifik" in row[1].lower() or "cek" in row[1].lower():
                    clean_target = prompt.lower().replace("berapa", "").replace("cek stok", "").replace("stok", "").strip()
                    return {"workflow_id": row[0], "target_item_name": clean_target, "send_email": False}
        
        # 2. Check for threshold update
        if any(k in prompt_lower for k in ["threshold", "ambang", "ubah batas"]):
            for row in workflows:
                if row[0] == "WF-002" or "threshold" in row[1].lower():
                    return {"workflow_id": row[0], "threshold_updates": [], "send_email": False}
        
        # 3. Check for warehouse audit
        if any(k in prompt_lower for k in ["seluruh gudang", "audit", "rekap seluruh"]):
            for row in workflows:
                if row[3] == tenant_id and "audit" in row[1].lower():
                    return {"workflow_id": row[0], "send_email": False}
            for row in workflows:
                if row[0] in ["WF-004", "WF-B01"] or "audit" in row[1].lower():
                    return {"workflow_id": row[0], "send_email": False}
                    
        # 4. Check for restock / pengadaan / menipis / kritis / PR
        is_restock_intent = any(k in prompt_lower for k in [
            "restock", "menipis", "kritis", "pengadaan", "pesan barang", "beli barang", "order barang", "purchase requisition", "kehabisan"
        ]) or bool(re.search(r'\bpr\b', prompt_lower))

        if is_restock_intent:
            # Check tenant-specific restock workflow first
            for row in workflows:
                if row[3] == tenant_id and any(w in row[1].lower() for w in ["restock", "pengadaan"]):
                    return {"workflow_id": row[0], "send_email": "email" in prompt_lower or "notifikasi" in prompt_lower}

            # Fallback to global restock if allowed
            for row in workflows:
                if "restock" in row[1].lower() or bool(re.search(r'\bpr\b', row[1].lower())):
                    return {"workflow_id": row[0], "send_email": True}

        # 5. ANTI-HALUSINASI GUARDRAIL:
        # If no recognized intent matched, return workflow_id: None! Do NOT pick a default workflow!
        return {
            "workflow_id": None,
            "send_email": False,
            "threshold_updates": [],
            "target_item_name": None
        }
