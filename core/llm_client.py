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
        Calls either qwen-35b or nemotron-35
        """


        endpoint = (
            settings.MODEL_QWEN_URL
            if "qwen" in model_name.lower()
            else settings.MODEL_NEMOTRON_URL
        )

        headers = {
            "Authorization": f"Bearer {settings.MODEL_API_KEY}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=180.0) as client:
            try:
                res = await client.post(f"{endpoint}/chat/completions", json=payload, headers=headers)
                res.raise_for_status()
                data = res.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"Failed to connect to model {model_name} at {endpoint}: {e}")
                raise e





gateway = ModelGateway()
