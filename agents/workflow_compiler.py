import json
import re

from core.llm_client import ModelGateway

class WorkflowCompiler:
    @classmethod
    async def compile_business_instruction(cls, name: str, instruction: str) -> dict:
        """
        Translates a natural language business instruction into a structured JSON workflow.
        """
        system_prompt = """You are a Workflow Compiler for an Inventory AutoRestock system.
Convert the user's business instruction into a strict JSON workflow definition.

Available tools/tasks you MUST choose from (use exactly these names):
- {"type": "tool", "tool": "inventory.get_low_stock_products"}
- {"type": "tool", "tool": "inventory.get_all_products"}
- {"type": "tool", "tool": "inventory.check_specific_stock"}
- {"type": "agent", "task": "calculate_reorder_quantity"}
- {"type": "tool", "tool": "purchase_order.create_draft"}
- {"type": "tool", "tool": "notification.send_email"}
- {"type": "tool", "tool": "inventory.update_threshold"}

Output format MUST be valid JSON:
{
  "workflow": "<workflow_name_slug>",
  "version": 1,
  "steps": [
    ... // Array of step objects
  ]
}
Do not output anything outside of the JSON structure.
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
            return parsed
        except Exception as e:
            print(f"[WORKFLOW COMPILER] Failed to compile workflow: {e}")
            return {
                "workflow": name.lower().replace(" ", "_"),
                "version": 1,
                "steps": []
            }
