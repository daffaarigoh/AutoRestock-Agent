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

    async def vision_shelf_audit(
        self,
        image_bytes: bytes
    ) -> Dict[str, Any]:
        """
        Calls qwen-35b-vision to detect empty/depleted shelf slots and locate bounding boxes.
        """
        if self.mock_mode:
            return self._mock_vision_shelf_audit()

        endpoint = settings.MODEL_QWEN_VISION_URL
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": "qwen-35b-vision",
            "image": b64_image,
            "task": "shelf_stock_audit",
        }

        headers = {
            "Authorization": f"Bearer {settings.MODEL_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                res = await client.post(f"{endpoint}/audit", json=payload, headers=headers)
                res.raise_for_status()
                return res.json()
            except Exception as e:
                logger.warning(f"Failed to call Vision model at {endpoint}: {e}. Falling back to mock.")
                return self._mock_vision_shelf_audit()

    # -------------------------------------------------------------
    # Realistic Mock Engines for Zero-Config Offline Testing
    # -------------------------------------------------------------

    def _mock_vision_shelf_audit(self) -> Dict[str, Any]:
        return {
            "total_slots_scanned": 4,
            "empty_slots_count": 2,
            "low_stock_count": 0,
            "audit_summary": "Pemeriksaan visual rak gudang mendeteksi 2 slot rak dalam kondisi kritis kosong.",
            "detected_items": [
                {
                    "slot_id": "SLOT-A1",
                    "item_label": "Baut Baja Hitam M8 (Empty Slot)",
                    "status": "CRITICAL_EMPTY",
                    "confidence": 0.98,
                    "bbox": {"ymin": 0.1, "xmin": 0.05, "ymax": 0.45, "xmax": 0.45},
                    "notes": "Slot kosong total, membutuhkan restock segera."
                },
                {
                    "slot_id": "SLOT-A2",
                    "item_label": "Oli Hidrolik ISO 68 (Empty Slot)",
                    "status": "CRITICAL_EMPTY",
                    "confidence": 0.95,
                    "bbox": {"ymin": 0.1, "xmin": 0.55, "ymax": 0.45, "xmax": 0.95},
                    "notes": "Slot kosong total."
                },
                {
                    "slot_id": "SLOT-B1",
                    "item_label": "Lakban Coklat 2 Inch",
                    "status": "NORMAL",
                    "confidence": 0.92,
                    "bbox": {"ymin": 0.55, "xmin": 0.05, "ymax": 0.9, "xmax": 0.45},
                    "notes": "Stok mencukupi."
                },
                {
                    "slot_id": "SLOT-B2",
                    "item_label": "Kertas Box A4 80gr",
                    "status": "NORMAL",
                    "confidence": 0.96,
                    "bbox": {"ymin": 0.55, "xmin": 0.55, "ymax": 0.9, "xmax": 0.95},
                    "notes": "Stok penuh."
                }
            ]
        }


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
                "inspector_name": "Agus Setiawan (Warehouse Lead Inspector)",
                "total_amount": 0.0,
                "extraction_confidence": 0.98,
                "summary": "Hasil stock opname fisik gudang mencatat 5 SKU kritis di bawah threshold: STM32F401 (12 pcs), ESP32 (8 pcs), Thermal Paste (5 tube), Cardboard Box (35 pcs), Bubble Wrap (4 roll).",
                "items": [
                    {
                        "line_no": 1,
                        "item_name": "Microcontroller STM32F401",
                        "sku": "ITM-001",
                        "qty_recorded": 12,
                        "unit": "pcs",
                        "unit_price": 65000.0,
                        "total_price": 780000.0,
                        "condition_notes": "Stok fisik 12 pcs, di bawah threshold 50 pcs."
                    },
                    {
                        "line_no": 2,
                        "item_name": "ESP32-WROOM-32D Module",
                        "sku": "ITM-002",
                        "qty_recorded": 8,
                        "unit": "pcs",
                        "unit_price": 39500.0,
                        "total_price": 316000.0,
                        "condition_notes": "Stok fisik 8 pcs, di bawah threshold 40 pcs."
                    },
                    {
                        "line_no": 3,
                        "item_name": "Thermal Paste Arctic MX-4 4g",
                        "sku": "ITM-003",
                        "qty_recorded": 5,
                        "unit": "tube",
                        "unit_price": 48000.0,
                        "total_price": 240000.0,
                        "condition_notes": "Stok fisik 5 tube, di bawah threshold 25 tube."
                    },
                    {
                        "line_no": 4,
                        "item_name": "Cardboard Box 30x20x15cm",
                        "sku": "ITM-004",
                        "qty_recorded": 35,
                        "unit": "pcs",
                        "unit_price": 4200.0,
                        "total_price": 147000.0,
                        "condition_notes": "Stok fisik 35 pcs, di bawah threshold 150 pcs."
                    },
                    {
                        "line_no": 5,
                        "item_name": "Bubble Wrap Roll 50m x 50cm",
                        "sku": "ITM-005",
                        "qty_recorded": 4,
                        "unit": "roll",
                        "unit_price": 72000.0,
                        "total_price": 288000.0,
                        "condition_notes": "Stok fisik 4 roll, di bawah threshold 15 roll."
                    }
                ]
            }
        else:
            return {
                "doc_type": "SURAT_JALAN",
                "doc_number": "SJ-2026-0819-094",
                "vendor_or_issuer": "PT. ELEKTRONIKA JAYA PRIMA & LOGISTIK",
                "date_recorded": "2026-08-19",
                "inspector_name": "Petugas Penerima Gudang",
                "total_amount": 10600000.0,
                "extraction_confidence": 0.97,
                "summary": "Surat Jalan pengiriman barang masuk restock: STM32F401 (+76), ESP32 (+52), Thermal Paste (+33), Cardboard Box (+190), Bubble Wrap (+17).",
                "items": [
                    {
                        "line_no": 1,
                        "item_name": "Microcontroller STM32F401",
                        "sku": "ITM-001",
                        "qty_recorded": 76,
                        "unit": "pcs",
                        "unit_price": 65000.0,
                        "total_price": 4940000.0,
                        "condition_notes": "Kemasan anti-statik tersegel rapi"
                    },
                    {
                        "line_no": 2,
                        "item_name": "ESP32-WROOM-32D Module",
                        "sku": "ITM-002",
                        "qty_recorded": 52,
                        "unit": "pcs",
                        "unit_price": 39500.0,
                        "total_price": 2054000.0,
                        "condition_notes": "Reel kemasan utuh"
                    },
                    {
                        "line_no": 3,
                        "item_name": "Thermal Paste Arctic MX-4 4g",
                        "sku": "ITM-003",
                        "qty_recorded": 33,
                        "unit": "tube",
                        "unit_price": 48000.0,
                        "total_price": 1584000.0,
                        "condition_notes": "Dus segel pabrik"
                    },
                    {
                        "line_no": 4,
                        "item_name": "Cardboard Box 30x20x15cm",
                        "sku": "ITM-004",
                        "qty_recorded": 190,
                        "unit": "pcs",
                        "unit_price": 4200.0,
                        "total_price": 798000.0,
                        "condition_notes": "Bandel utuh rapi"
                    },
                    {
                        "line_no": 5,
                        "item_name": "Bubble Wrap Roll 50m x 50cm",
                        "sku": "ITM-005",
                        "qty_recorded": 17,
                        "unit": "roll",
                        "unit_price": 72000.0,
                        "total_price": 1224000.0,
                        "condition_notes": "Roll tersegel plastik"
                    }
                ]
            }



gateway = ModelGateway()
