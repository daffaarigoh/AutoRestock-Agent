import unittest
import sys
from pathlib import Path

WORKSPACE_DIR = Path(__file__).resolve().parent.parent
if str(WORKSPACE_DIR) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_DIR))

from agents.router import extract_recipient_email, check_clarification_needs

class TestDynamicEmailRecipient(unittest.TestCase):
    def test_direct_email_extraction(self):
        prompt = "Cek seluruh status cuti yang masih pending dan kirim ke dimas@balitower.co.id untuk persetujuan"
        recip = extract_recipient_email(prompt)
        self.assertEqual(recip, "dimas@balitower.co.id")

    def test_named_colleague_extraction(self):
        # Test Zeiniah
        self.assertEqual(extract_recipient_email("Cek status cuti pending dan kirim ke zeiniah"), "zeiniahalfiah@gmail.com")
        # Test Daffa
        self.assertEqual(extract_recipient_email("Cek data cuti pending dan kirim ke Daffa untuk persetujuan"), "muhammaddaffaarigoh@gmail.com")
        # Test HR
        self.assertEqual(extract_recipient_email("Kirim rekap cuti pending ke HR"), "muhammaddaffaarigoh@gmail.com")
        # Test Manager
        self.assertEqual(extract_recipient_email("Tolong teruskan email ke manager"), "muhammaddaffaarigoh@gmail.com")
        # Test Employee
        self.assertEqual(extract_recipient_email("Kirimkan berkas ke rian hidayat"), "muhammaddaffaarigoh@gmail.com")

    def test_user_reported_prompt_clarification(self):
        # The exact prompt reported by user where email recipient is missing
        user_prompt = "Periksa seluruh stok material yang menipis dan buat draft PR pengadaan barang dan kirimkan ke email"
        recip = extract_recipient_email(user_prompt)
        self.assertIsNone(recip, "Bare 'pengadaan barang' in PR phrase must NOT be falsely extracted as email recipient")
        
        clarif = check_clarification_needs(user_prompt)
        self.assertIsNotNone(clarif, "Prompt requesting email dispatch without recipient MUST trigger clarification")
        self.assertEqual(clarif["field"], "recipient_email")
        self.assertIn("muhammaddaffaarigoh@gmail.com", clarif["hint"])

    def test_user_reported_prompt_with_email_ready(self):
        # When user supplies the email, it should proceed without clarification
        user_prompt = "Periksa seluruh stok material yang menipis dan buat draft PR pengadaan barang dan kirimkan ke email muhammaddaffaarigoh@gmail.com"
        recip = extract_recipient_email(user_prompt)
        self.assertEqual(recip, "muhammaddaffaarigoh@gmail.com")
        
        clarif = check_clarification_needs(user_prompt)
        self.assertIsNone(clarif, "Prompt with explicit email address should NOT require clarification")

    def test_missing_parameter_clarifications(self):
        # 1. Threshold missing item name
        c_thresh_item = check_clarification_needs("Ubah batas minimum menjadi 25")
        self.assertIsNotNone(c_thresh_item)
        self.assertEqual(c_thresh_item["field"], "threshold_item_name")

        # 2. Threshold missing number
        c_thresh_val = check_clarification_needs("Ubah batas minimum SFP Transceiver")
        self.assertIsNotNone(c_thresh_val)
        self.assertEqual(c_thresh_val["field"], "threshold_parameters")

        # 3. Goods receipt missing PO number
        c_po = check_clarification_needs("Catat penerimaan barang dari vendor")
        self.assertIsNotNone(c_po)
        self.assertEqual(c_po["field"], "po_number_required")

if __name__ == "__main__":
    unittest.main()
