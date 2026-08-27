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
class TestAPIHealth(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_api_health_endpoints(self):
        """
        Verifies API dashboard and health endpoints
        """
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("AutoRestock", res.text)

        health_res = self.client.get("/health")
        self.assertEqual(health_res.status_code, 200)
        self.assertEqual(health_res.json(), {"status": "healthy", "llm_connected": True})




if __name__ == "__main__":
    unittest.main()

