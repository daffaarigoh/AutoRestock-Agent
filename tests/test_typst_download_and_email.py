import io
import sys
import unittest
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from fastapi.testclient import TestClient
from api.main import app
from core.security import get_current_user, get_document_user, TokenData
from api.routers.approval_routes import PR_STORE, _create_default_pr
from docgen.compiler import generate_pr_pdf, get_pr_typ_path, STORAGE_DIR
from core.dispatcher import dispatcher, _format_markdown_to_html


class TestTypstDownloadAndEmail(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: TokenData(username="admin", role="ADMIN", tenant_id="ALL")
        app.dependency_overrides[get_document_user] = lambda: TokenData(username="admin", role="ADMIN", tenant_id="ALL")

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()

    def setUp(self):
        # Reset DB and seed default PR
        res = self.client.post("/api/approval/reset?seed=true")
        self.assertEqual(res.status_code, 200)

    def test_docgen_generates_pdf_and_preserves_typ(self):
        """Verify generate_pr_pdf outputs PDF and preserves .typ source file."""
        pr = _create_default_pr("PR-2026-TEST-001", status="PENDING")
        pdf_path_str = generate_pr_pdf(pr.model_dump())
        pdf_path = Path(pdf_path_str)
        self.assertTrue(pdf_path.exists())
        self.assertTrue(pdf_path_str.endswith(".pdf"))

        typ_path = pdf_path.with_suffix(".typ")
        self.assertTrue(typ_path.exists(), f"Typst source file {typ_path} must exist on disk.")

        with open(typ_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("PR-2026-TEST-001", content)
        self.assertIn("Microcontroller STM32F401", content)

    def test_download_typst_endpoint(self):
        """Verify GET /api/documents/pr/{pr_number}/download-typst endpoint returns text/plain attachment."""
        pr_number = "PR-2026-0819-001"
        res = self.client.get(f"/api/documents/pr/{pr_number}/download-typst")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/plain", res.headers.get("content-type", ""))
        self.assertIn(f"{pr_number.replace('/', '_')}.typ", res.headers.get("content-disposition", ""))
        
        typ_content = res.text
        self.assertIn(pr_number, typ_content)
        self.assertIn("Microcontroller STM32F401", typ_content)

    def test_download_format_typst_query_param(self):
        """Verify GET /api/documents/pr/{pr_number}/download?format=typst returns .typ source."""
        pr_number = "PR-2026-0819-001"
        res = self.client.get(f"/api/documents/pr/{pr_number}/download?format=typst")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/plain", res.headers.get("content-type", ""))
        self.assertIn(".typ", res.headers.get("content-disposition", ""))
        self.assertIn(pr_number, res.text)

    def test_email_html_buttons_and_material_table(self):
        """Verify email dispatcher renders material table and 4 action buttons (Approve, Reject, PDF, Typst)."""
        pr_number = "PR-2026-0819-001"
        res = self.client.post("/api/approval/dispatch-email", json={"pr_number": pr_number})
        self.assertEqual(res.status_code, 200)
        
        # Dispatch manually through MultiChannelDispatcher to inspect simulated payload and HTML
        pr_doc = PR_STORE.get(pr_number)
        self.assertIsNotNone(pr_doc)
        
        items_table_md = (
            "| SKU | Nama | Vendor | Kuantitas | Satuan | Estimasi Biaya |\n"
            "| :--- | :--- | :--- | :---: | :---: | ---: |\n"
            "| `ITM-001` | **Microcontroller STM32F401** | PT. Elektronika Jaya Prima | **76** | pcs | **Rp 4.940.000** |\n"
            "| `ITM-002` | **ESP32-WROOM-32D Module** | CV. Komponen Nusantara | **52** | pcs | **Rp 2.054.000** |\n"
        )
        
        html_table = _format_markdown_to_html(items_table_md)
        self.assertIn("<table", html_table)
        self.assertIn("SKU", html_table)
        self.assertIn("Nama", html_table)
        self.assertIn("Vendor", html_table)
        self.assertIn("Kuantitas", html_table)
        self.assertIn("Satuan", html_table)
        self.assertIn("Estimasi Biaya", html_table)
        self.assertIn("text-align: right", html_table) # Estimasi Biaya aligned right
        self.assertIn("text-align: center", html_table) # Kuantitas/Satuan aligned center

        import asyncio
        dispatch_res = asyncio.run(dispatcher.dispatch_email(
            recipient_email="test.manager@balitower.co.id",
            subject="Test PR Notification",
            content_text=items_table_md,
            pr_number=pr_number
        ))
        
        self.assertEqual(dispatch_res["status"], "simulated")
        self.assertIn("typst_url", dispatch_res["interactive_actions"])
        self.assertTrue(dispatch_res["interactive_actions"]["typst_url"].endswith(f"/api/documents/pr/{pr_number}/download-typst"))
        self.assertTrue(dispatch_res["interactive_actions"]["pdf_url"].endswith(f"/api/documents/pr/{pr_number}/download"))
        self.assertIn("approve_url", dispatch_res["interactive_actions"])
        self.assertIn("reject_url", dispatch_res["interactive_actions"])
        
        # Check attachments
        attachments = dispatch_res.get("attachments", [])
        self.assertTrue(any(a.endswith(".pdf") for a in attachments), f"PDF should be attached: {attachments}")
        self.assertTrue(any(a.endswith(".typ") for a in attachments), f".typ source should be attached: {attachments}")


if __name__ == "__main__":
    unittest.main()
