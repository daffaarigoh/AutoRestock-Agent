"""
Test Suite for Tahap 3:
Purchase Order (PO) Typst PDF Generation, Preview, and Download Flow.
"""

import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from docgen.compiler import generate_po_pdf, angka_ke_terbilang

client = TestClient(app)

def login(username: str = "usera", password: str = "user123"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, f"Login failed: {res.text}"
    return {"Authorization": f"Bearer {res.json()['access_token']}"}

def test_terbilang_helper():
    print("\n=== [1/5] Testing Indonesian Terbilang (Words) Generator ===")
    assert "Enam Puluh Enam Juta" in angka_ke_terbilang(66000000)
    assert "Tujuh Puluh Tiga Juta Dua Ratus Enam Puluh Ribu Rupiah" == angka_ke_terbilang(73260000)
    assert "Seratus Delapan Puluh Lima Juta Rupiah" == angka_ke_terbilang(185000000)
    print("  [OK] angka_ke_terbilang generates perfect Indonesian grammatical numbers.")

def test_direct_po_pdf_compiler():
    print("\n=== [2/5] Testing Direct Typst Compilation for Multiple POs ===")
    for po_id in ["PO-2026-001", "PO-2026-006", "PO-2026-007"]:
        pdf_path = generate_po_pdf(po_id)
        path_obj = Path(pdf_path)
        assert path_obj.exists(), f"PDF for {po_id} should exist at {pdf_path}"
        assert path_obj.stat().st_size > 10000, f"PDF file size too small: {path_obj.stat().st_size} bytes"
        with open(path_obj, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-", f"Expected %PDF- magic bytes, got {header}"
        print(f"  [OK] Successfully compiled Typst PDF for {po_id} ({path_obj.stat().st_size} bytes)")

def test_po_pdf_download_endpoints():
    print("\n=== [3/5] Testing PO PDF Download & Preview API Endpoints ===")
    # 1. Inline Preview (for In-App Modal Iframe)
    res_inline = client.get("/api/documents/po/PO-2026-006/download?inline=true")
    assert res_inline.status_code == 200
    assert "application/pdf" in res_inline.headers["content-type"]
    assert "inline" in res_inline.headers.get("content-disposition", "")
    assert res_inline.content.startswith(b"%PDF-")
    print("  [OK] GET /api/documents/po/PO-2026-006/download?inline=true (200 OK, inline header)")

    # 2. Attachment Download
    res_dl = client.get("/api/documents/po/PO-2026-006/download?download=true")
    assert res_dl.status_code == 200
    assert "attachment" in res_dl.headers.get("content-disposition", "")
    assert "PO-2026-006.pdf" in res_dl.headers.get("content-disposition", "")
    print("  [OK] GET /api/documents/po/PO-2026-006/download?download=true (200 OK, attachment filename)")

def test_chat_prompt_po_pdf_generation():
    print("\n=== [4/5] Testing AI Copilot Prompt for PO PDF Request ===")
    headers = login("usera", "user123")
    res = client.post(
        "/api/agent/custom-prompt",
        headers=headers,
        json={"prompt": "Tolong tampilkan dokumen PDF untuk PO-2026-006", "destinations": []}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["action_type"] == "view_po_document"
    assert data["po_id"] == "PO-2026-006"
    assert data["pdf_download_url"] == "/api/documents/po/PO-2026-006/download"
    assert "Typst Engine" in data["message"]
    print("  [OK] AI Copilot returned view_po_document card with interactive PDF modal trigger.")

def test_purchase_orders_api_fields():
    print("\n=== [5/5] Testing Purchase Orders API for UI Action Button ===")
    headers = login("usera", "user123")
    res = client.get("/api/balitower/inventory/purchase-orders", headers=headers)
    assert res.status_code == 200
    pos = res.json()
    assert len(pos) >= 16
    first_po = pos[0]
    assert "po_id" in first_po
    assert "po_number" in first_po
    assert "supplier_name" in first_po
    assert "total_amount" in first_po
    print(f"  [OK] /api/balitower/inventory/purchase-orders returned {len(pos)} PO records with required metadata.")

    print("\n=== ALL TAHAP 3 PO PDF TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    test_terbilang_helper()
    test_direct_po_pdf_compiler()
    test_po_pdf_download_endpoints()
    test_chat_prompt_po_pdf_generation()
    test_purchase_orders_api_fields()
