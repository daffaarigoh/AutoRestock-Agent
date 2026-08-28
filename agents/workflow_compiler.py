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
        system_prompt = """You are a Workflow Compiler for an Enterprise Agentic Inventory & Restock System.
Convert the user's natural language business instruction into a strict, structured JSON workflow execution definition.

You must build the execution pipeline using the 4 Core Agentic Building Blocks:

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

3. NOTIFICATION & DISPATCH (Tools):
   - {"type": "tool", "tool": "notification.dispatch"} or {"type": "tool", "tool": "notification.send_email"} -> Sends email notifications, alert dispatches, or operational reports.

4. DOCUMENT GENERATION (Tools):
   - {"type": "tool", "tool": "docgen.compile"} or {"type": "tool", "tool": "purchase_order.create_draft"} -> Generates Purchase Requisition (PR) draf documents and Typst PDFs.

Output format MUST be strictly valid JSON:
{
  "workflow": "<workflow_name_slug>",
  "version": 1,
  "steps": [
    ... // Array of step objects
  ]
}
Do not output any markdown formatting or extra commentary outside the JSON.
"""
        gateway = ModelGateway()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Workflow Name: {name}\n\nInstruction:\n{instruction}"}
        ]
        
        try:
            response_str = await gateway.chat_completion("qwen-35b", messages, temperature=0.1, response_format_json=True)
            json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if json_match:
                response_str = json_match.group(0)
            parsed = json.loads(response_str)
            if parsed.get("steps") and len(parsed["steps"]) > 0:
                return parsed
        except Exception as e:
            print(f"[WORKFLOW COMPILER] LLM compilation exception: {e}. Utilizing deterministic heuristic compiler.")

        # Heuristic compiler fallback ensuring high-quality standard compilation
        text_lower = f"{name} {instruction}".lower()
        slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        
        steps = []
        # Case 1: Product Registration & Validation
        if any(k in text_lower for k in ["daftar", "pendaftaran", "tambah barang", "register", "validasi"]):
            steps.append({"type": "agent", "task": "agent.reason_and_validate"})
            steps.append({"type": "tool", "tool": "inventory.register_product"})
            if "email" in text_lower or "notifikasi" in text_lower or "lapor" in text_lower:
                steps.append({"type": "tool", "tool": "notification.dispatch"})
        
        # Case 2: Update Threshold
        elif any(k in text_lower for k in ["threshold", "ambang", "batas"]):
            steps.append({"type": "tool", "tool": "inventory.update_threshold"})
            if "email" in text_lower or "notifikasi" in text_lower:
                steps.append({"type": "tool", "tool": "notification.dispatch"})
                
        # Case 3: Warehouse Audit
        elif any(k in text_lower for k in ["audit", "seluruh gudang", "semua barang"]):
            steps.append({"type": "tool", "tool": "inventory.get_all_products"})
            steps.append({"type": "tool", "tool": "notification.dispatch"})
            
        # Case 4: Specific stock check
        elif any(k in text_lower for k in ["spesifik", "cek stok"]):
            steps.append({"type": "tool", "tool": "inventory.check_specific_stock"})
            
        # Case 5: Standard Restock / Procurement (End-to-End)
        else:
            steps.append({"type": "tool", "tool": "inventory.get_low_stock_products"})
            steps.append({"type": "agent", "task": "calculate_reorder_quantity"})
            steps.append({"type": "tool", "tool": "docgen.compile"})
            steps.append({"type": "tool", "tool": "notification.dispatch"})
            
        return {
            "workflow": slug or "custom_workflow",
            "version": 1,
            "steps": steps
        }
