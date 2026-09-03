import base64
import json
import logging
from typing import Any

try:
    import httpx
except ImportError:
    import httpx2 as httpx

from core.config import settings

logger = logging.getLogger(__name__)


class ModelGateway:
    """
    Unified client gateway for:
    - 'qwen-35b': Core Agent reasoning & tool calls
    - 'nemotron-35': Compliance Auditor & Evaluator
    - 'ocr-lighton': Physical document OCR extraction (Surat Jalan, Invoices, Kartu Stok)
    """

    def __init__(self):
        pass

    async def chat_completion(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        response_format_json: bool = False,
    ) -> str:
        """
        Calls configured LLM models (Qwen, Nemotron, OCR) using settings from .env.
        Supports MOCK_MODELS mode if enabled or as fallback.
        """
        lower_name = model_name.lower()
        
        # Resolve model name from settings
        if "qwen" in lower_name:
            actual_model = settings.MODEL_QWEN_NAME
            endpoint = settings.MODEL_QWEN_URL
        elif "nemotron" in lower_name:
            actual_model = settings.MODEL_NEMOTRON_NAME
            endpoint = settings.MODEL_NEMOTRON_URL
        elif "ocr" in lower_name:
            actual_model = settings.MODEL_OCR_NAME
            endpoint = settings.MODEL_OCR_LIGHTON_URL or settings.MODEL_QWEN_URL
        else:
            actual_model = model_name
            endpoint = settings.MODEL_QWEN_URL

        # Handle Mock Mode if enabled in .env
        if settings.MOCK_MODELS:
            logger.info(f"[MOCK_MODE] Simulating LLM response for {actual_model}")
            return self._generate_mock_response(actual_model, messages, response_format_json)

        headers = {
            "Authorization": f"Bearer {settings.MODEL_API_KEY}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": actual_model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=8.0)) as client:
            try:
                res = await client.post(f"{endpoint}/chat/completions", json=payload, headers=headers)
                res.raise_for_status()
                data = res.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"Failed to connect to model {actual_model} at {endpoint}: {e}")
                raise e

    def _generate_mock_response(self, model: str, messages: list[dict[str, str]], response_format_json: bool) -> str:
        """Generates realistic mock responses when MOCK_MODELS=True."""
        user_content = " ".join([m.get("content", "") for m in messages if m.get("role") == "user"])
        user_lower = user_content.lower()

        if "auditor" in model.lower() or "compliance" in user_lower or "budget" in user_lower:
            return json.dumps({
                "auditor_status": "PASSED",
                "auditor_notes": "Evaluasi pengadaan lolos kepatuhan anggaran (Mock Mode)."
            })
        elif "planner" in user_lower or "vendor" in user_lower:
            return json.dumps({
                "items": [
                    {
                        "item_id": "ITM-001",
                        "vendor_id": "VND-001",
                        "vendor_name": "PT. Elektronika Jaya Prima",
                        "unit_price": 65000.0,
                        "line_total": 4940000.0,
                        "reason": "Rekomendasi vendor optimal (Mock Mode)."
                    }
                ]
            })
        elif "workflow_id" in user_lower:
            return json.dumps({"workflow_id": "WF-001"})
        
        if response_format_json:
            return json.dumps({"status": "success", "message": "Simulasi respons AI berhasil (Mock Mode)."})
        return "Halo! Ini adalah respons simulasi AutoRestock-Agent (Mock Mode)."


gateway = ModelGateway()
