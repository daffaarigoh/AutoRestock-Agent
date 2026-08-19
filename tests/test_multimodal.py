import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from api.main import app
from core.llm_client import gateway
from core.schemas import StockStatus
from multimodal.ocr_engine import OCREngine
from multimodal.vision_auditor import VisionAuditor

client = TestClient(app)


def _create_dummy_image_bytes() -> bytes:
    img = Image.new("RGB", (400, 300), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_ocr_engine_processing():
    """
    Verifies that OCREngine parses receipt / invoice bytes into valid OCRDocumentResult
    """
    image_bytes = _create_dummy_image_bytes()
    result = await OCREngine.process_document(image_bytes, filename="test_surat_jalan.jpg")

    assert result.doc_number == "SJ-2026-0819-094"
    assert result.vendor_name == "PT. MITRA LOGISTIK UTAMA"
    assert len(result.items) == 2
    assert result.items[0].item_name == "Baut Baja M8 x 50mm"
    assert result.items[0].qty_received == 500
    assert result.total_amount == 4750000.0


@pytest.mark.asyncio
async def test_vision_auditor_shelf():
    """
    Verifies that VisionAuditor analyzes rack photo and renders bounding boxes
    """
    image_bytes = _create_dummy_image_bytes()
    result = await VisionAuditor.audit_shelf_image(image_bytes, original_filename="test_rack.jpg")

    assert result.total_slots_scanned == 4
    assert result.empty_slots_count == 2
    assert len(result.detected_items) == 4
    assert result.detected_items[0].status == StockStatus.CRITICAL_EMPTY
    assert result.annotated_image_url is not None
    assert "/api/annotated/" in result.annotated_image_url


def test_api_health_endpoints():
    """
    Verifies root and health check endpoints
    """
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "qwen-35b-vision" in data["supported_models"]

    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json() == {"status": "healthy"}


def test_api_ingest_delivery_note():
    """
    Tests POST /api/ingest/delivery-note upload
    """
    image_bytes = _create_dummy_image_bytes()
    files = {"file": ("delivery_note.jpg", image_bytes, "image/jpeg")}

    res = client.post("/api/ingest/delivery-note", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["doc_number"] == "SJ-2026-0819-094"
    assert len(data["items"]) == 2


def test_api_ingest_shelf_photo():
    """
    Tests POST /api/ingest/shelf-photo upload
    """
    image_bytes = _create_dummy_image_bytes()
    files = {"file": ("warehouse_shelf.jpg", image_bytes, "image/jpeg")}

    res = client.post("/api/ingest/shelf-photo", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["empty_slots_count"] == 2
    assert "annotated_image_url" in data
