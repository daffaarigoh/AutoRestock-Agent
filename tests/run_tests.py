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
        from unittest.mock import AsyncMock, patch

        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("AutoRestock", res.text)

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            from unittest.mock import MagicMock
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            health_res = self.client.get("/health")
            self.assertEqual(health_res.status_code, 200)
            self.assertEqual(health_res.json(), {"status": "healthy", "llm_connected": True})




if __name__ == "__main__":
    unittest.main()

