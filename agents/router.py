import json
import re

from core.llm_client import ModelGateway
from database.db import get_db_connection

class SemanticRouter:
    @classmethod
    async def route_prompt(cls, prompt: str, tenant_id: str = "ALL") -> dict:
        """
        Matches user prompt to a predefined workflow ID and extracts context parameters.
        """
        conn = get_db_connection(read_only=True)
        workflows = conn.execute("SELECT id, name, description FROM workflows").fetchall()
        conn.close()
        
        workflows_str = "\n".join([f"- ID: {row[0]}, Name: {row[1]}, Desc: {row[2]}" for row in workflows])
        
        system_prompt = f"""You are a Semantic Router for an Inventory AutoRestock system.
Match the user's prompt to one of the following predefined workflows:

{workflows_str}

If the user wants to update a threshold, you must extract "threshold_updates": [{{"item_name": "name of item", "new_threshold": 100}}]
If the user specifies an item name to check, extract it as "target_item_name".
If the user explicitly asks to send an email, report, or notify via email, extract "send_email": true. Otherwise, "send_email": false.
Do not assume any default workflow. Carefully match the prompt's intent to the descriptions provided above.

Output strictly valid JSON with exact keys: "workflow_id", "threshold_updates" (optional array), "target_item_name" (optional string), "send_email" (boolean).
If no workflow matches, return workflow_id: null.
"""
        gateway = ModelGateway()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response_str = await gateway.chat_completion("qwen-35b", messages, temperature=0.1, response_format_json=True)
            json_match = re.search(r'\{.*\}', response_str, re.DOTALL)
            if json_match:
                response_str = json_match.group(0)
            parsed = json.loads(response_str)
            return parsed
        except Exception as e:
            print(f"[SEMANTIC ROUTER] LLM failed: {e}")
            return {"workflow_id": None, "threshold_updates": []}
