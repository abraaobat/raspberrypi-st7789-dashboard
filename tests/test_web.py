import tempfile
import unittest
from unittest.mock import patch

from dashboard.config import default_config
from dashboard.runtime import RuntimeStore
from web_app import create_app


class WebControlPanelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "STATE_DIR": self.temporary.name,
                "SECRET_KEY": "test-only-secret",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary.cleanup()

    def configure_auth(self):
        response = self.client.post("/api/auth/setup", json={"pin": "2468"})
        self.assertEqual(response.status_code, 200)
        return response.get_json()["csrfToken"]

    def test_first_use_authentication_flow(self):
        status = self.client.get("/api/auth/status").get_json()
        self.assertFalse(status["configured"])
        self.assertFalse(status["authenticated"])

        csrf = self.configure_auth()
        self.assertTrue(csrf)

        self.client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        denied = self.client.get("/api/config")
        self.assertEqual(denied.status_code, 401)
        invalid = self.client.post("/api/auth/login", json={"pin": "0000"})
        self.assertEqual(invalid.status_code, 401)
        login = self.client.post("/api/auth/login", json={"pin": "2468"})
        self.assertEqual(login.status_code, 200)

    def test_config_preview_and_live_page_selection(self):
        csrf = self.configure_auth()
        config = default_config()
        config["carousel"]["enabled"] = True
        config["pages"] = [config["pages"][1], config["pages"][0], config["pages"][2]]

        saved = self.client.put(
            "/api/config",
            json=config,
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["pages"][0]["id"], "network")

        preview = self.client.get("/api/preview?page=network")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.content_type, "image/png")
        self.assertGreater(len(preview.data), 500)

        selected = self.client.post(
            "/api/display/page",
            json={"pageId": "network"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(
            RuntimeStore(self.temporary.name).read_control()["requestedPage"],
            "network",
        )

    def test_mutations_require_csrf_and_invalid_config_is_rejected(self):
        self.configure_auth()
        missing_csrf = self.client.put("/api/config", json=default_config())
        self.assertEqual(missing_csrf.status_code, 403)

        status = self.client.get("/api/auth/status").get_json()
        invalid = default_config()
        invalid["thresholds"]["temperatureCritical"] = 50
        response = self.client.put(
            "/api/config",
            json=invalid,
            headers={"X-CSRF-Token": status["csrfToken"]},
        )
        self.assertEqual(response.status_code, 400)

    def test_security_headers_are_present(self):
        response = self.client.get("/")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])

    def test_catalog_exposes_integrations_and_display_profiles(self):
        self.configure_auth()
        response = self.client.get("/api/catalog")
        payload = response.get_json()
        ids = {page["id"] for page in payload["pages"]}
        self.assertIn("weather", ids)
        self.assertIn("sysops", ids)
        self.assertEqual(payload["displays"][0]["id"], "st7789-240x240")

    @patch("web_app.fetch_custom_page")
    def test_custom_source_can_be_tested_without_saving(self, fetch_custom_page_mock):
        fetch_custom_page_mock.return_value = {"value": 318, "secondary": "W"}
        csrf = self.configure_auth()
        response = self.client.post(
            "/api/sources/test",
            json={
                "id": "custom:energia",
                "title": "Energia",
                "layout": "metric",
                "valueLabel": "CONSUMO",
                "unit": "W",
                "accent": "green",
                "source": {
                    "type": "http-json",
                    "url": "http://192.168.1.10/status",
                    "valuePath": "data.power",
                    "secondaryPath": "data.unit",
                },
            },
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["value"], 318)

    def test_login_is_rate_limited(self):
        self.configure_auth()
        status = self.client.get("/api/auth/status").get_json()
        self.client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": status["csrfToken"]},
        )
        for _ in range(5):
            response = self.client.post("/api/auth/login", json={"pin": "0000"})
            self.assertEqual(response.status_code, 401)
        limited = self.client.post("/api/auth/login", json={"pin": "0000"})
        self.assertEqual(limited.status_code, 429)


if __name__ == "__main__":
    unittest.main()
