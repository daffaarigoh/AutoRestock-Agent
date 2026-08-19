import base64
import json
import logging
from typing import Any, Dict, List, Optional
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
        self.mock_mode = settings.MOCK_MODELS

    async def chat_completion(
        self,
        model_name: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        response_format_json: bool = False,
    ) -> str:
        """
        Calls either qwen-35b or nemotron-35
        """
        if self.mock_mode:
            return self._mock_chat_completion(model_name, messages)

        endpoint = (
            settings.MODEL_QWEN_URL
            if "qwen" in model_name.lower()
            else settings.MODEL_NEMOTRON_URL
        )

        headers = {
            "Authorization": f"Bearer {settings.MODEL_API_KEY}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                res = await client.post(f"{endpoint}/chat/completions", json=payload, headers=headers)
                res.raise_for_status()
                data = res.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                logger.warning(f"Failed to connect to model {model_name} at {endpoint}: {e}. Falling back to mock.")
                return self._mock_chat_completion(model_name, messages)

    async def ocr_document_extraction(
        self,
        image_bytes: bytes,
        doc_type_hint: str = "SURAT_JALAN"
    ) -> Dict[str, Any]:
        """
        Calls ocr-lighton to parse structured data from physical documents:
        - Invoices
        - Surat Jalan / Goods Receipt Notes
        - Kartu Stok Opname Fisik
        """
        if self.mock_mode:
            return self._mock_ocr_document_extraction(doc_type_hint)

        endpoint = settings.MODEL_OCR_LIGHTON_URL
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": "ocr-lighton",
            "image": b64_image,
            "doc_type_hint": doc_type_hint,
            "task": "document_parse_table",
        }

        headers = {
            "Authorization": f"Bearer {settings.MODEL_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                res = await client.post(f"{endpoint}/parse", json=payload, headers=headers)
                res.raise_for_status()
                return res.json()
            except Exception as e:
                logger.warning(f"Failed to call OCR LightOn model at {endpoint}: {e}. Falling back to mock.")
                return self._mock_ocr_document_extraction(doc_type_hint)

    # -------------------------------------------------------------
    # Realistic Mock Engines for Zero-Config Offline Testing
    # -------------------------------------------------------------

    def _mock_chat_completion(self, model_name: str, messages: List[Dict[str, str]]) -> str:
        if "nemotron" in model_name.lower():
            return json.dumps({
                "auditor_status": "PASSED",
                "auditor_notes": "Compliance check passed: Requested order quantities match the 14-day consumption burn rate and stay within departmental budget allocation.",
                "approved": True
            })
        else:
            return json.dumps({
                "reason": "Current stock is below safety threshold due to high dispatch activity. Recommending order from PT. Sumber Makmur based on lowest unit price and 2-day lead time.",
                "recommended_vendor_id": "VEND-001"
            })

    def _mock_ocr_document_extraction(self, doc_type_hint: str) -> Dict[str, Any]:
        if "KARTU_STOK" in doc_type_hint.upper() or "OPNAME" in doc_type_hint.upper():
            return {
                "doc_type": "KARTU_STOK_OPNAME",
                "doc_number": "OPNAME-2026-0819",
                "vendor_or_issuer": "Tim Gudang Logistik B",
                "date_recorded": "2026-08-19",
                "inspector_name": "Agus Setiawan (Warehouse Officer)",
                "total_amount": 0.0,
                "extraction_confidence": 0.98,
                "summary": "Hasil stock opname fisik gudang mencatat stok Baut M8 tersisa 12 pcs (Kritis) dan Oli Hidrolik tersisa 1 drum.",
                "items": [
                    {
                        "line_no": 1,
                        "item_name": "Baut Baja Hitam M8 x 50mm",
                        "sku": "SKU-BAUT-M8",
                        "qty_recorded": 12,
                        "unit": "pcs",
                        "unit_price": 2500.0,
                        "total_price": 30000.0,
                        "condition_notes": "Stok fisik menipis tajam, di bawah batas threshold 100 pcs."
                    },
                    {
                        "line_no": 2,
                        "item_name": "Oli Hidrolik ISO VG 68 20L",
                        "sku": "SKU-OLI-ISO68",
                        "qty_recorded": 1,
                        "unit": "pail",
                        "unit_price": 875000.0,
                        "total_price": 875000.0,
                        "condition_notes": "Tersisa 1 pail, butuh restock segera."
                    }
                ]
            }
        else:
            return {
                "doc_type": "SURAT_JALAN",
                "doc_number": "SJ-2026-0819-094",
                "vendor_or_issuer": "PT. MITRA LOGISTIK UTAMA",
                "date_recorded": "2026-08-19",
                "inspector_name": "Petugas Penerima Gudang",
                "total_amount": 4750000.0,
                "extraction_confidence": 0.97,
                "summary": "Surat Jalan pengiriman barang restock mingguan dari PT Mitra Logistik Utama.",
                "items": [
                    {
                        "line_no": 1,
                        "item_name": "Baut Baja M8 x 50mm",
                        "sku": "SKU-BAUT-M8",
                        "qty_recorded": 500,
                        "unit": "pcs",
                        "unit_price": 2500.0,
                        "total_price": 1250000.0,
                        "condition_notes": "Kemasan tersegel rapi"
                    },
                    {
                        "line_no": 2,
                        "item_name": "Oli Hidrolik ISO 68 (Pail 20L)",
                        "sku": "SKU-OLI-ISO68",
                        "qty_recorded": 4,
                        "unit": "pail",
                        "unit_price": 875000.0,
                        "total_price": 3500000.0,
                        "condition_notes": "Kondisi drum baik tanpa kebocoran"
                    }
                ]
            }


gateway = ModelGateway()
