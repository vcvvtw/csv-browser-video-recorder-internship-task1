import os
import sys
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import web_service


class TestWebServiceUnit(unittest.TestCase):
    def setUp(self):
        web_service.app.config["TESTING"] = True
        self.client = web_service.app.test_client()

    def test_safe_company_filename(self):
        self.assertEqual(
            web_service.safe_company_filename("Acme Berlin Tech", "sample.webm"),
            "Acme_Berlin_Tech.webm"
        )
        self.assertEqual(
            web_service.safe_company_filename("Bavaria Soft Solutions! #1", "rec.webm"),
            "Bavaria_Soft_Solutions___1.webm"
        )
        self.assertEqual(
            web_service.safe_company_filename("   ", "sample.webm"),
            "video.webm"
        )

    def test_index_endpoint(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "running")
        self.assertIn("endpoints", data)

    def test_health_endpoint(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        with patch("web_service.get_db", return_value=mock_conn):
            res = self.client.get("/health")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()["status"], "ok")
            self.assertEqual(res.get_json()["database"], "connected")

    def test_get_video_url_missing_param(self):
        res = self.client.get("/get_video_url")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_get_video_url_not_found(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        with patch("web_service.get_db", return_value=mock_conn):
            res = self.client.get("/get_video_url?company_name=UnknownCorp")
            self.assertEqual(res.status_code, 404)
            self.assertIn("error", res.get_json())

    def test_get_video_url_success(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = {
            "company_name": "Acme Berlin Tech",
            "video_url": "http://127.0.0.1:8000/media/Acme_Berlin_Tech.webm"
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        with patch("web_service.get_db", return_value=mock_conn):
            res = self.client.get("/get_video_url?company_name=Acme%20Berlin%20Tech")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.get_json()["company_name"], "Acme Berlin Tech")
            self.assertTrue(res.get_json()["video_url"].endswith("/media/Acme_Berlin_Tech.webm"))

    def test_upload_missing_file_field(self):
        res = self.client.post("/upload", data={"company_name": "Acme Berlin Tech"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_upload_missing_company_name(self):
        from io import BytesIO
        data = {
            "file": (BytesIO(b"FAKEWEBMDATA"), "test.webm")
        }
        res = self.client.post("/upload", data=data, content_type="multipart/form-data")
        self.assertEqual(res.status_code, 400)
        self.assertIn("error", res.get_json())

    def test_list_videos(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [
            {
                "id": 1,
                "company_name": "Acme Berlin Tech",
                "file_path": "/app/uploads/Acme_Berlin_Tech.webm",
                "video_url": "http://127.0.0.1:8000/media/Acme_Berlin_Tech.webm",
                "created_at": "2026-11-22 12:00:00",
                "updated_at": "2026-11-22 12:00:00"
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        with patch("web_service.get_db", return_value=mock_conn):
            res = self.client.get("/videos")
            self.assertEqual(res.status_code, 200)
            items = res.get_json()
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["company_name"], "Acme Berlin Tech")


if __name__ == "__main__":
    unittest.main()
