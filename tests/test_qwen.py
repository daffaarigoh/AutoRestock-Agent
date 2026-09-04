import asyncio
import re

from core.llm_client import ModelGateway

system_prompt = """You are an Intent Parser AI for an Inventory AutoRestock system.
Parse the user's natural language prompt into a structured JSON object.

Rules:
1. category_filter: Must be one of ["Electronics", "Packaging", "Consumables", "Mechanical", "Hardware"] or null. Map Indonesian terms (e.g., "baut" -> Hardware, "kardus" -> Packaging, "pasta" -> Consumables).
2. threshold_updates: Extract any requests to update minimum stock thresholds. Output as a list of objects: [{"item_id": "ITM-XXX", "new_threshold": integer}]. Format item_id uppercase.
3. destinations: Where the report should be sent. Base destinations are ALWAYS "database" and "pdf". User might ask for "email".
   - CRITICAL: Pay strict attention to negations (e.g., "jangan kirim email"). If negated, DO NOT include that destination.
4. recipient_email: Extract any email address mentioned in the text (string or null).
5. scan_all: Boolean. Set to true if the user implies scanning all items (laporan/rekap). Set to false if they only update a threshold or check a specific item.
6. create_pr: Boolean. Set to true ONLY if the user explicitly asks to restock, buy, or create a PR (e.g., "restock", "belikan", "ajukan pembelian"). Set to false if they just want to check stock, view reports, or update thresholds.
7. specific_items: Extract ANY explicitly mentioned item IDs (e.g. "ITM-003") or item names (e.g. "microcontroller", "Silica Gel", "baut", "Silica Gel Desiccant Packets 5g") into a list of strings. DO NOT skip specific item names. If the user mentions a specific product, put it here. If they just mention a general category, leave it empty.

Output strictly valid JSON with the exact keys: "category_filter", "threshold_updates", "destinations", "recipient_email", "scan_all", "create_pr", "specific_items".
"""

async def test(p):
    gw = ModelGateway()
    messages = [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': p}]
    res = await gw.chat_completion('qwen-35b', messages, temperature=0.1, response_format_json=True)
    json_match = re.search(r'\{.*\}', res, re.DOTALL)
    if json_match:
        res = json_match.group(0)
    print(p, '->', res)

async def main():
    await test('Coba cek stok Silica Gel Desiccant Packets 5g')
    await test('Restock Silica Gel')

if __name__ == "__main__":
    asyncio.run(main())
