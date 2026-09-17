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

    def test_clarification_when_unspecified(self):
        # When user asks to send email but mentions no recipient email/name
        clarif = check_clarification_needs("Tolong kirimkan notifikasi dokumen ke email")
        self.assertIsNotNone(clarif)
        self.assertEqual(clarif["field"], "recipient_email")

    def test_no_clarification_when_named_recipient_present(self):
        # When named recipient is specified, no clarification needed
        clarif_named = check_clarification_needs("Tolong kirimkan notifikasi dokumen ke Daffa")
        self.assertIsNone(clarif_named)

        clarif_direct = check_clarification_needs("Kirimkan ke test@balitower.co.id")
        self.assertIsNone(clarif_direct)

if __name__ == "__main__":
    unittest.main()
