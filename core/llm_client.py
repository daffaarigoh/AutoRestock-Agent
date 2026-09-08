import json
import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class ModelGateway:
    """
    Unified client gateway for:
    - 'nemotron-35': Single corporate model for Planning, Routing, and Compliance Auditing
    """

    def __init__(self):
        pass

    async def chat_completion(
        self,
        model_name: str = "nemotron-35",
        messages: list[dict[str, str]] | None = None,
        temperature: float = 0.2,
        response_format_json: bool = False,
    ) -> str:
        """
        Calls configured LLM model (nemotron-35) using settings from .env.
        """
        actual_model = settings.MODEL_NAME or "nemotron-35"
        endpoint = (settings.MODEL_URL or "http://localhost:8001/v1").rstrip("/")
        if endpoint.endswith("/models"):
            endpoint = endpoint[:-7]

        headers = {
            "Authorization": f"Bearer {settings.MODEL_API_KEY}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": actual_model,
            "messages": messages or [],
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


gateway = ModelGateway()
