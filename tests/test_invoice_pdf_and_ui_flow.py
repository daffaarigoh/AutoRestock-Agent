import unittest
from fastapi.testclient import TestClient
from api.main import app
from database.db import get_db_connection
from docgen.compiler import generate_invoice_pdf
from agents.router import extract_recipient_email, check_clarification_needs
from core.action_links import build_action_url
from pathlib import Path

class TestInvoicePdfAndUiFlow(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        login = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(login.status_code, 200)

    def test_invoice_pdf_compilation(self):
        pdf_path = generate_invoice_pdf("INV-2026-001")
        self.assertTrue(Path(pdf_path).exists(), f"PDF should exist at {pdf_path}")
        self.assertTrue(Path(pdf_path).stat().st_size > 10000, "PDF should be valid size")

    def test_invoice_download_endpoint(self):
        # Test inline preview
        res_inline = self.client.get("/api/documents/invoice/INV-2026-001/download?inline=true")
        self.assertEqual(res_inline.status_code, 200)
        self.assertEqual(res_inline.headers.get("content-type"), "application/pdf")
        self.assertIn("inline", res_inline.headers.get("content-disposition", ""))

        # Test download attachment
        res_download = self.client.get("/api/documents/invoice/INV-2026-001/download")
        self.assertEqual(res_download.status_code, 200)
        self.assertEqual(res_download.headers.get("content-type"), "application/pdf")
        self.assertIn("attachment", res_download.headers.get("content-disposition", ""))

    def test_email_extraction_and_safety(self):
        # Strict user testing rules: any email address can be extracted, named zeiniah resolves to zeiniahalfiah@gmail.com
        self.assertEqual(extract_recipient_email("Kirim invoice ke zeiniah"), "zeiniahalfiah@gmail.com")
        self.assertEqual(extract_recipient_email("Kirim invoice ke finance@perusahaan.co.id"), "finance@perusahaan.co.id")
        
        # When user asks to send email but mentions no recipient
        clarif = check_clarification_needs("Tolong kirimkan invoice ini ke email")
        self.assertIsNotNone(clarif)
        self.assertEqual(clarif["field"], "recipient_email")

    def test_onboarding_approval_marks_invoice_paid(self):
        conn = get_db_connection()
        try:
            # Ensure pending table exists and create a test onboarding record
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_client_onboardings (
                    onboarding_id VARCHAR PRIMARY KEY,
                    client_id VARCHAR,
                    client_name VARCHAR,
                    client_type VARCHAR,
                    npwp VARCHAR,
                    billing_email VARCHAR,
                    payment_terms VARCHAR,
                    contract_id VARCHAR,
                    site_id VARCHAR,
                    monthly_rate BIGINT,
                    billing_frequency VARCHAR,
                    start_date VARCHAR,
                    end_date VARCHAR,
                    first_invoice_amount BIGINT,
                    approval_status VARCHAR DEFAULT 'PENDING_APPROVAL',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approved_at TIMESTAMP,
                    approved_by VARCHAR
                );
            """)
            test_onb_id = "ONB-TEST-099"
            test_cli_id = "CLI-TEST-099"
            test_mla_id = "MLA-TEST-099"
            conn.execute("DELETE FROM pending_client_onboardings WHERE onboarding_id = ?", [test_onb_id])
            conn.execute("DELETE FROM revenue_invoices WHERE client_id = ?", [test_cli_id])
            conn.execute("DELETE FROM mla_contracts WHERE contract_id = ?", [test_mla_id])
            conn.execute("DELETE FROM telecom_clients WHERE client_id = ?", [test_cli_id])

            conn.execute("""
                INSERT INTO pending_client_onboardings (
                    onboarding_id, client_id, client_name, client_type, npwp,
                    billing_email, payment_terms, contract_id, site_id, monthly_rate,
                    billing_frequency, start_date, end_date, first_invoice_amount, approval_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING_APPROVAL');
            """, [
                test_onb_id, test_cli_id, "PT Operator Testing", "OPERATOR_SELULER", "01.234.567.8-095.000",
                "billing@testing.co.id", "Net 30", test_mla_id, "JKS-MCP-001", 25000000,
                "QUARTERLY", "2026-04-01", "2031-03-31", 83250000
            ])
            conn.commit()

            # Trigger approval endpoint
            url = build_action_url("http://testserver", "onboarding", test_onb_id, "APPROVE")
            confirm = self.client.get(url)
            self.assertEqual(confirm.status_code, 200)
            res = self.client.post(url)
            self.assertEqual(res.status_code, 200)

            # Check revenue_invoices: status MUST be PAID
            inv_row = conn.execute("SELECT payment_status FROM revenue_invoices WHERE client_id = ?", [test_cli_id]).fetchone()
            self.assertIsNotNone(inv_row, "Revenue invoice should be created on approval")
            self.assertEqual(inv_row[0], "PAID", "Invoice status must be PAID when approved")

            # Cleanup
            conn.execute("DELETE FROM pending_client_onboardings WHERE onboarding_id = ?", [test_onb_id])
            conn.execute("DELETE FROM revenue_invoices WHERE client_id = ?", [test_cli_id])
            conn.execute("DELETE FROM mla_contracts WHERE contract_id = ?", [test_mla_id])
            conn.execute("DELETE FROM telecom_clients WHERE client_id = ?", [test_cli_id])
            conn.commit()
        finally:
            conn.close()

if __name__ == "__main__":
    unittest.main()
