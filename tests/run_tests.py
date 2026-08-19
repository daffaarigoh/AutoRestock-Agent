import asyncio
import io
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from starlette.testclient import TestClient

from api.main import app
from core.schemas import DocumentType
from multimodal.ocr_engine import OCREngine


def _create_dummy_image_bytes() -> bytes:
    img = Image.new("RGB", (400, 300), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestOCRPipeline(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_ocr_engine_surat_jalan(self):
        """
        Verifies OCR parsing on Surat Jalan / Delivery Note
        """
        async def _run():
            image_bytes = _create_dummy_image_bytes()
            result = await OCREngine.process_document(image_bytes, doc_type_hint="SURAT_JALAN")
            self.assertEqual(result.doc_type, DocumentType.SURAT_JALAN)
            self.assertEqual(result.doc_number, "SJ-2026-0819-094")
            self.assertEqual(result.vendor_or_issuer, "PT. MITRA LOGISTIK UTAMA")
            self.assertEqual(len(result.items), 2)
            self.assertEqual(result.items[0].item_name, "Baut Baja M8 x 50mm")
            self.assertEqual(result.items[0].qty_recorded, 500)
            self.assertEqual(result.total_amount, 4750000.0)

        asyncio.run(_run())

    def test_ocr_engine_stock_opname(self):
        """
        Verifies OCR parsing on physical Stock Opname Card
        """
        async def _run():
            image_bytes = _create_dummy_image_bytes()
            result = await OCREngine.process_document(image_bytes, doc_type_hint="KARTU_STOK_OPNAME")
            self.assertEqual(result.doc_type, DocumentType.KARTU_STOK_OPNAME)
            self.assertEqual(result.doc_number, "OPNAME-2026-0819")
            self.assertEqual(result.items[0].qty_recorded, 12)
            self.assertIn("menipis", result.items[0].condition_notes)

        asyncio.run(_run())

    def test_api_health_endpoints(self):
        """
        Verifies API dashboard and health endpoints
        """
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("AutoRestock-Agent", res.text)

        health_res = self.client.get("/health")
        self.assertEqual(health_res.status_code, 200)
        self.assertEqual(health_res.json(), {"status": "healthy"})

    def test_api_ingest_delivery_note(self):
        """
        Tests POST /api/ingest/delivery-note upload
        """
        image_bytes = _create_dummy_image_bytes()
        files = {"file": ("delivery_note.png", image_bytes, "image/png")}

        res = self.client.post("/api/ingest/delivery-note", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["doc_number"], "SJ-2026-0819-094")
        self.assertEqual(len(data["items"]), 2)

    def test_api_ingest_stock_opname(self):
        """
        Tests POST /api/ingest/stock-opname upload
        """
        image_bytes = _create_dummy_image_bytes()
        files = {"file": ("stock_opname.png", image_bytes, "image/png")}

        res = self.client.post("/api/ingest/stock-opname", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["doc_type"], "KARTU_STOK_OPNAME")
        self.assertEqual(data["doc_number"], "OPNAME-2026-0819")


if __name__ == "__main__":
    unittest.main()
