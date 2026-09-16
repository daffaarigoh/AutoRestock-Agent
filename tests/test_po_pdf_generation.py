import sys
import unittest
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


class TestPOPDFGeneration(unittest.TestCase):

    def test_terbilang_helper(self):
        self.assertIn("Enam Puluh Enam Juta", angka_ke_terbilang(66000000))
        self.assertEqual("Tujuh Puluh Tiga Juta Dua Ratus Enam Puluh Ribu Rupiah", angka_ke_terbilang(73260000))
        self.assertEqual("Seratus Delapan Puluh Lima Juta Rupiah", angka_ke_terbilang(185000000))

    def test_direct_po_pdf_compiler(self):
        for po_id in ["PO-2026-001", "PO-2026-006", "PO-2026-007"]:
            pdf_path = generate_po_pdf(po_id)
            path_obj = Path(pdf_path)
            self.assertTrue(path_obj.exists(), f"PDF for {po_id} should exist at {pdf_path}")
            self.assertGreater(path_obj.stat().st_size, 10000, f"PDF file size too small: {path_obj.stat().st_size} bytes")
            with open(path_obj, "rb") as f:
                header = f.read(5)
                self.assertEqual(header, b"%PDF-", f"Expected %PDF- magic bytes, got {header}")

    def test_po_pdf_download_endpoints(self):
        # 1. Inline Preview (for In-App Modal Iframe)
        res_inline = client.get("/api/documents/po/PO-2026-006/download?inline=true")
        self.assertEqual(res_inline.status_code, 200)
        self.assertIn("application/pdf", res_inline.headers["content-type"])
        self.assertIn("inline", res_inline.headers.get("content-disposition", ""))
        self.assertTrue(res_inline.content.startswith(b"%PDF-"))

        # 2. Attachment Download
        res_dl = client.get("/api/documents/po/PO-2026-006/download?download=true")
        self.assertEqual(res_dl.status_code, 200)
        self.assertIn("attachment", res_dl.headers.get("content-disposition", ""))
        self.assertIn("PO-2026-006.pdf", res_dl.headers.get("content-disposition", ""))

    def test_chat_prompt_po_pdf_generation(self):
        headers = login("usera", "user123")
        res = client.post(
            "/api/agent/custom-prompt",
            headers=headers,
            json={"prompt": "Tolong tampilkan dokumen PDF untuk PO-2026-006", "destinations": []}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["action_type"], "view_po_document")
        self.assertEqual(data["po_id"], "PO-2026-006")
        self.assertEqual(data["pdf_download_url"], "/api/documents/po/PO-2026-006/download")

    def test_purchase_orders_api_fields(self):
        headers = login("usera", "user123")
        res = client.get("/api/balitower/inventory/purchase-orders", headers=headers)
        self.assertEqual(res.status_code, 200)
        pos = res.json()
        self.assertGreaterEqual(len(pos), 8)
        first_po = pos[0]
        self.assertIn("po_id", first_po)
        self.assertIn("po_number", first_po)
        self.assertIn("supplier_name", first_po)
        self.assertIn("total_amount", first_po)


if __name__ == "__main__":
    unittest.main()
