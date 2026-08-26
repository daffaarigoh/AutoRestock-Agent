import asyncio
import io
import unittest

from PIL import Image
from starlette.testclient import TestClient

from api.main import app
from core.schemas import StockStatus
from multimodal.ocr_engine import OCREngine
from multimodal.vision_auditor import VisionAuditor


def _create_dummy_image_bytes() -> bytes:
    img = Image.new("RGB", (400, 300), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestMultimodalPipeline(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_ocr_engine_processing(self):
        """
        Verifies that OCREngine parses receipt / invoice bytes into valid OCRDocumentResult
        """
        async def _run():
            image_bytes = _create_dummy_image_bytes()
            result = await OCREngine.process_document(image_bytes, filename="test_surat_jalan.jpg")
            self.assertEqual(result.doc_number, "SJ-2026-0819-094")
            self.assertGreaterEqual(len(result.items), 2)
            self.assertGreater(result.items[0].qty_received, 0)

        asyncio.run(_run())

    def test_vision_auditor_shelf(self):
        """
        Verifies that VisionAuditor analyzes rack photo and renders bounding boxes
        """
        async def _run():
            image_bytes = _create_dummy_image_bytes()
            result = await VisionAuditor.audit_shelf_image(image_bytes, original_filename="test_rack.jpg")
            self.assertEqual(result.total_slots_scanned, 4)
            self.assertEqual(result.empty_slots_count, 2)
            self.assertEqual(len(result.detected_items), 4)
            self.assertEqual(result.detected_items[0].status, StockStatus.CRITICAL_EMPTY)
            self.assertIsNotNone(result.annotated_image_url)
            self.assertIn("/api/annotated/", result.annotated_image_url)

        asyncio.run(_run())

    def test_api_health_endpoints(self):
        """
        Verifies root and health check endpoints
        """
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "online")
        self.assertIn("qwen-35b-vision", data["supported_models"])

        health_res = self.client.get("/health")
        self.assertEqual(health_res.status_code, 200)
        self.assertEqual(health_res.json(), {"status": "healthy"})

    def test_api_ingest_delivery_note(self):
        """
        Tests POST /api/ingest/delivery-note upload
        """
        image_bytes = _create_dummy_image_bytes()
        files = {"file": ("delivery_note.jpg", image_bytes, "image/jpeg")}

        res = self.client.post("/api/ingest/delivery-note", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["doc_number"], "SJ-2026-0819-094")
        self.assertGreaterEqual(len(data["items"]), 2)

    def test_api_ingest_shelf_photo(self):
        """
        Tests POST /api/ingest/shelf-photo upload
        """
        image_bytes = _create_dummy_image_bytes()
        files = {"file": ("warehouse_shelf.jpg", image_bytes, "image/jpeg")}

        res = self.client.post("/api/ingest/shelf-photo", files=files)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["empty_slots_count"], 2)
        self.assertIn("annotated_image_url", data)


if __name__ == "__main__":
    unittest.main()

