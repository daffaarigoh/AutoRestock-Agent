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
            "Content-Type": "application/json",
        }
        if settings.MODEL_API_KEY and settings.MODEL_API_KEY.strip():
            headers["Authorization"] = f"Bearer {settings.MODEL_API_KEY.strip()}"

        payload: dict[str, Any] = {
            "model": actual_model,
            "messages": messages or [],
            "temperature": temperature,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            try:
                res = await client.post(f"{endpoint}/chat/completions", json=payload, headers=headers)
                res.raise_for_status()
                data = res.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error(f"Failed to connect to model {actual_model} at {endpoint}: {e!r}")
                raise e

    async def chat_completion_stream(
        self,
        model_name: str = "nemotron-35",
        messages: list[dict[str, str]] | None = None,
        temperature: float = 0.2,
    ):
        """
        Streams response tokens from configured LLM model (nemotron-35).
        Yields text chunks as they arrive from the upstream server.
        """
        actual_model = settings.MODEL_NAME or "nemotron-35"
        endpoint = (settings.MODEL_URL or "http://localhost:8001/v1").rstrip("/")
        if endpoint.endswith("/models"):
            endpoint = endpoint[:-7]

        headers = {
            "Content-Type": "application/json",
        }
        if settings.MODEL_API_KEY and settings.MODEL_API_KEY.strip():
            headers["Authorization"] = f"Bearer {settings.MODEL_API_KEY.strip()}"

        payload: dict[str, Any] = {
            "model": actual_model,
            "messages": messages or [],
            "temperature": temperature,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            try:
                async with client.stream("POST", f"{endpoint}/chat/completions", json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            raw_data = line[6:].strip()
                            if raw_data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(raw_data)
                                content = chunk["choices"][0]["delta"].get("content", "")
                                if content:
                                    yield content
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"Streaming failed for model {actual_model} at {endpoint}: {e!r}")
                raise e


gateway = ModelGateway()
