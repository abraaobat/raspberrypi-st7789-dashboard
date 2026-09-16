import io
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from dashboard.config import ConfigError, default_config, load_config, normalize_config, save_config
from dashboard.credentials import CredentialError, CredentialStore, validate_secret
from dashboard.http_client import MAX_JSON_BYTES, SourceError, request_json, resolve_source
from dashboard.integration_settings import base_url, integration_settings
from dashboard.integrations import fetch_integration
from dashboard.providers import AsyncDataCache, DataHub
from dashboard.rendering import render_page
from web_app import create_app

SUMMARY = {"queries": {"total": 1000, "blocked": 245, "percent_blocked": 24.5},
           "clients": {"active": 8}, "gravity": {"domains_being_blocked": 100000}}
TOKEN = "test-only-credential-not-a-real-token"


class SettingsTests(unittest.TestCase):
    def test_legacy_config_adds_disabled_connectors_without_reordering(self):
        old = default_config()
        old.pop("integrations")
        old["pages"] = [old["pages"][1], old["pages"][0], old["pages"][2]]
        migrated = normalize_config(old)
        self.assertEqual([page["id"] for page in migrated["pages"][:3]], ["network", "status", "hardware"])
        self.assertFalse(any(page["enabled"] for page in migrated["pages"] if page["id"] in {"pihole", "homeassistant"}))

    def test_base_address_is_canonical_and_rejects_secret_urls(self):
        self.assertEqual(base_url("HTTPS://EXAMPLE.COM:443/proxy/"), "https://example.com/proxy")
        self.assertEqual(base_url("http://[fd00::1]:8123/"), "http://[fd00::1]:8123")
        for value in ["file:///tmp/x", "http://user:secret@host", "https://host/?token=x",
                      "http://host/admin", "http://host/api", "http://host/a/../b", "http://host:0"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                base_url(value, required=True)

    def test_closed_settings_reject_credentials_and_bad_entities(self):
        for payload in [{"token": TOKEN}, {"allowInsecureHttp": "true"}, {"entities": ["sensor.x"] * 2},
                        {"entities": ["sensor.x/../../api"]}, {"entities": [f"sensor.x{i}" for i in range(5)]}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                integration_settings("homeassistant", payload)
        config = default_config()
        config["integrations"]["pihole"]["secret"] = TOKEN
        with self.assertRaises(ConfigError):
            normalize_config(config)

    def test_null_save_does_not_reset_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            config = default_config()
            config["carousel"]["enabled"] = True
            save_config(config, directory)
            with self.assertRaises(ConfigError):
                save_config(None, directory)
            self.assertTrue(load_config(directory)["carousel"]["enabled"])


class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = CredentialStore(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_owner_only_and_write_only_public_metadata(self):
        receipt = self.store.put("homeassistant", "http://home.local:8123/", TOKEN)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.directory.stat().st_mode & 0o777, 0o700)
        self.assertTrue(receipt["credentialMatches"])
        self.assertNotIn(TOKEN, json.dumps(receipt))
        self.assertNotIn("revision", receipt)
        self.assertEqual(self.store.read_secret("homeassistant", "http://home.local:8123"), TOKEN)

    def test_bound_to_address_and_rotated_revision(self):
        self.store.put("pihole", "http://pi.local", TOKEN)
        revision = self.store.revision("pihole", "http://pi.local")
        with self.assertRaises(CredentialError):
            self.store.read_secret("pihole", "http://other.local")
        self.assertIsNone(self.store.revision("pihole", "https://pi.local"))
        self.store.put("pihole", "http://pi.local", "replacement-password")
        self.assertNotEqual(self.store.revision("pihole", "http://pi.local"), revision)
        self.store.delete("pihole")
        self.assertFalse(self.store.status("pihole")["credentialConfigured"])

    def test_corrupt_or_public_vault_is_never_overwritten(self):
        self.store.put("pihole", "http://pi.local", TOKEN)
        # Test fixtures intentionally corrupt files; production writes remain atomic.
        self.store.path.write_text("broken", encoding="utf-8")
        with self.assertRaises(CredentialError):
            self.store.put("homeassistant", "http://ha.local", TOKEN)
        self.assertEqual(self.store.path.read_text(), "broken")
        self.store.path.chmod(0o644)
        with self.assertRaises(CredentialError):
            self.store.status("pihole")

    def test_symlink_is_not_followed(self):
        target = Path(self.temporary.name) / "target"
        target.write_text("preserve", encoding="utf-8")
        self.store.path.symlink_to(target)
        with self.assertRaises(CredentialError):
            self.store.put("pihole", "http://pi.local", TOKEN)
        self.assertEqual(target.read_text(), "preserve")

    def test_concurrent_process_compatible_writes_preserve_both_entries(self):
        def save(index):
            connector = "pihole" if index % 2 else "homeassistant"
            CredentialStore(self.temporary.name).put(connector, "http://local.test", TOKEN + str(index))
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(save, range(20)))
        payload = json.loads(self.store.path.read_text())
        self.assertEqual(set(payload["entries"]), {"pihole", "homeassistant"})
        self.assertFalse(list(self.store.directory.glob(".credentials-*.tmp")))

    def test_secret_and_connector_validation(self):
        for connector, value in [("other", TOKEN), ("pihole", ""), ("pihole", "x\n"),
                                 ("homeassistant", "has space"), ("homeassistant", "á"), ("pihole", "x" * 4097)]:
            with self.subTest(connector=connector, value=value[:20]), self.assertRaises(CredentialError):
                validate_secret(connector, value)


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seen = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                cls.seen.append(self.path)
                code, body = 200, b'{"value":42}'
                if self.path == "/redirect":
                    code, body = 302, b""
                elif self.path == "/large":
                    body = b'{"value":"' + b"x" * MAX_JSON_BYTES + b'"}'
                elif self.path == "/refused":
                    code, body = 401, TOKEN.encode()
                elif self.path == "/invalid":
                    body = b"not JSON"
                elif self.path == "/scalar":
                    body = b"42"
                elif self.path == "/slow":
                    time.sleep(.15)
                self.send_response(code)
                if code == 302:
                    self.send_header("Location", "/never-follow")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_json_http10_and_environment_proxy_is_ignored(self):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "http_proxy": "http://127.0.0.1:1"}):
            self.assertEqual(request_json(self.url + "/json"), {"value": 42})

    def test_explicit_local_http_consent(self):
        with self.assertRaisesRegex(SourceError, "explicitamente"):
            request_json(self.url + "/json", authenticated=True)
        self.assertEqual(request_json(self.url + "/json", authenticated=True, allow_insecure_http=True)["value"], 42)

    def test_redirect_large_bad_json_and_reflected_error_do_not_leak(self):
        for path in ["/redirect", "/large", "/invalid", "/scalar", "/refused"]:
            with self.subTest(path=path), self.assertRaises(SourceError) as context:
                request_json(self.url + path)
            self.assertNotIn(TOKEN, str(context.exception))
        self.assertNotIn("/never-follow", self.seen)

    def test_deadline_limits_response_wait(self):
        started = time.monotonic()
        with self.assertRaises(SourceError):
            request_json(self.url + "/slow", timeout=.03)
        self.assertLess(time.monotonic() - started, .3)

    def test_dns_pinning_keeps_host_and_uses_checked_ip(self):
        rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", self.server.server_port))]
        with patch("dashboard.http_client.socket.getaddrinfo", return_value=rows) as resolver:
            self.assertEqual(request_json(f"http://checked.test:{self.server.server_port}/json")["value"], 42)
        # socket.create_connection resolves a literal pinned IP, never the hostname a second time.
        self.assertEqual(resolver.call_args_list[0].args[0], "checked.test")
        self.assertTrue(all(call.args[0] == "127.0.0.1" for call in resolver.call_args_list[1:]))

    def test_unsafe_and_public_authenticated_http_destinations(self):
        for address in ["169.254.169.254", "::ffff:169.254.169.254", "0.0.0.0", "224.0.0.1", "8.8.8.8"]:
            rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))]
            with self.subTest(address=address), patch("dashboard.http_client.socket.getaddrinfo", return_value=rows), self.assertRaises(SourceError):
                resolve_source("http://service.test", authenticated=True, allow_insecure_http=True)
        for address in ["100.100.1.1", "192.168.1.1", "fd00::1"]:
            rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 80))]
            with self.subTest(address=address), patch("dashboard.http_client.socket.getaddrinfo", return_value=rows):
                self.assertEqual(resolve_source("http://service.test", authenticated=True, allow_insecure_http=True)[2], [address])

    def test_mixed_dns_answer_fails_closed_and_bad_methods_rejected(self):
        rows = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80)) for ip in ["192.168.1.1", "169.254.1.1"]]
        with patch("dashboard.http_client.socket.getaddrinfo", return_value=rows), self.assertRaises(SourceError):
            resolve_source("https://mixed.test")
        with self.assertRaises(SourceError):
            request_json(self.url, method="PUT")


class ConnectorTests(unittest.TestCase):
    @patch("dashboard.integrations.request_json")
    def test_pihole_auth_summary_logout_and_safe_output(self, request):
        request.side_effect = [{"session": {"valid": True, "sid": "private-session"}}, SUMMARY, {}]
        result = fetch_integration("pihole", {"baseUrl": "http://pi.local", "allowInsecureHttp": True}, TOKEN)
        self.assertEqual(result["blockedPercent"], 24.5)
        self.assertNotIn(TOKEN, json.dumps(result))
        calls = request.call_args_list
        self.assertEqual(calls[0].kwargs["payload"], {"password": TOKEN})
        self.assertEqual(calls[1].args[0], "http://pi.local/api/stats/summary")
        self.assertEqual(calls[1].kwargs["headers"], {"X-FTL-SID": "private-session"})
        self.assertEqual(calls[2].kwargs["method"], "DELETE")
        self.assertTrue(all("dns/blocking" not in call.args[0] for call in calls))

    @patch("dashboard.integrations.request_json")
    def test_pihole_logs_out_even_if_summary_fails(self, request):
        request.side_effect = [{"session": {"valid": True, "sid": "session"}}, SourceError("unavailable"), {}]
        with self.assertRaises(SourceError):
            fetch_integration("pihole", {"baseUrl": "http://pi.local"}, TOKEN)
        self.assertEqual(request.call_args_list[-1].kwargs["method"], "DELETE")

    @patch("dashboard.integrations.request_json")
    def test_pihole_missing_percent_fallback_and_oversized_numbers(self, request):
        request.side_effect = [{"session": {"valid": True, "sid": "session"}}, {"queries": {"total": 100, "blocked": 25}}, {}]
        self.assertEqual(fetch_integration("pihole", {"baseUrl": "http://pi.local"}, TOKEN)["blockedPercent"], 25)
        request.side_effect = [{"session": {"valid": True, "sid": "session"}}, {"queries": {"total": 10**400, "blocked": 25}}, {}]
        with self.assertRaises(SourceError):
            fetch_integration("pihole", {"baseUrl": "http://pi.local"}, TOKEN)

    @patch("dashboard.integrations.request_json")
    def test_homeassistant_selected_states_only_and_secret_redaction(self, request):
        request.side_effect = [
            {"entity_id": "sensor.power", "state": "314", "attributes": {"friendly_name": "Power " + TOKEN, "unit_of_measurement": "W", "secret": TOKEN}},
            {"entity_id": "binary_sensor.door", "state": "unavailable", "attributes": {}},
            SourceError("not found", 404),
        ]
        result = fetch_integration("homeassistant", {"baseUrl": "https://home.local", "entities": ["sensor.power", "binary_sensor.door", "sensor.missing"]}, TOKEN)
        self.assertEqual([row["available"] for row in result["entities"]], [True, False, False])
        self.assertNotIn(TOKEN, json.dumps(result))
        self.assertIn("[oculto]", result["entities"][0]["label"])
        self.assertTrue(all(call.kwargs.get("method", "GET") == "GET" for call in request.call_args_list))
        self.assertTrue(all(call.kwargs["headers"] == {"Authorization": "Bearer " + TOKEN} for call in request.call_args_list))

    @patch("dashboard.integrations.request_json")
    def test_homeassistant_wrong_entity_and_auth_failure_are_not_off_states(self, request):
        settings = {"baseUrl": "https://home.local", "entities": ["sensor.power"]}
        request.return_value = {"entity_id": "sensor.other", "state": "off"}
        with self.assertRaises(SourceError):
            fetch_integration("homeassistant", settings, TOKEN)
        request.side_effect = SourceError("credencial recusada", 401)
        with self.assertRaises(SourceError) as context:
            fetch_integration("homeassistant", settings, TOKEN)
        self.assertEqual(context.exception.status, 401)

    def test_empty_homeassistant_does_not_query_any_endpoint(self):
        with patch("dashboard.integrations.request_json") as request, self.assertRaises(SourceError):
            fetch_integration("homeassistant", {"baseUrl": "http://home.local", "entities": []}, TOKEN)
        request.assert_not_called()


class CacheAndRenderingTests(unittest.TestCase):
    def test_error_backoff_and_stale_value_are_preserved(self):
        cache = AsyncDataCache()
        cache.get("test", "revision", 30, lambda: {"configured": True, "value": 42})
        for _ in range(100):
            with cache._lock:
                if not cache._items["test"]["refreshing"]:
                    break
            time.sleep(.001)
        failing = Mock(side_effect=SourceError("unavailable"))
        cache._refresh("test", "revision", failing)
        failing.reset_mock()
        snapshot = cache.get("test", "revision", 0, failing)
        self.assertEqual(snapshot["value"], 42)
        self.assertTrue(snapshot["stale"])
        self.assertEqual(snapshot["error"], "unavailable")
        failing.assert_not_called()

    def test_deleted_credentials_and_address_change_clear_cached_data(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = DataHub(metrics=Mock(get=Mock(return_value={})), state_override=directory)
            config = default_config()
            config["integrations"]["pihole"]["baseUrl"] = "http://pi.local"
            hub.credentials.put("pihole", "http://pi.local", TOKEN)
            with patch.object(hub.external, "get", return_value={"configured": True}) as cache:
                hub.get(config, "pihole", 60)
                self.assertNotIn(TOKEN, cache.call_args.args[1])
                self.assertIn("credentialRevision", cache.call_args.args[1])
                config["integrations"]["pihole"]["baseUrl"] = "http://other.local"
                self.assertFalse(hub.get(config, "pihole", 60)["pihole"]["configured"])
                self.assertEqual(cache.call_count, 1)

    def test_new_pages_render_loaded_loading_unconfigured_and_cache(self):
        config = default_config()
        for page in config["pages"]:
            page["enabled"] = True
        loaded = {"pihole": {"configured": True, "blockedPercent": 24.5, "blockedQueries": 245,
                              "totalQueries": 1000, "activeClients": 8, "blockedDomains": 100000},
                  "homeassistant": {"configured": True, "entities": [
                      {"label": "Temperatura", "state": "28.1", "unit": "°C", "available": True},
                      {"label": "Porta", "state": "on", "unit": "", "available": True},
                      {"label": "Ausente", "state": "unavailable", "unit": "", "available": False}]}}
        for connector in ["pihole", "homeassistant"]:
            for value in [loaded[connector], {"loading": True}, {"configured": False},
                          {**loaded[connector], "error": "offline", "stale": True}]:
                image = render_page(connector, {connector: value}, config)
                self.assertEqual(image.size, (240, 240))
                self.assertGreater(sum(Image.Image.getextrema(image)[0]), 100)


class IntegrationApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "STATE_DIR": self.temporary.name, "SECRET_KEY": "test-key"})
        self.client = self.app.test_client()
        self.credentials = CredentialStore(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def login(self):
        csrf = self.client.post("/api/auth/setup", json={"pin": "2468"}).get_json()["csrfToken"]
        return {"X-CSRF-Token": csrf}

    def test_new_endpoints_require_authentication_and_csrf(self):
        for method, endpoint in [("GET", "/api/integrations/status"), ("GET", "/api/config/export"),
                                 ("PUT", "/api/integrations/pihole/credential"), ("DELETE", "/api/integrations/pihole/credential"),
                                 ("POST", "/api/integrations/pihole/test"), ("POST", "/api/config/import")]:
            with self.subTest(method=method, endpoint=endpoint):
                self.assertEqual(self.client.open(endpoint, method=method).status_code, 401)
        self.login()
        for method, endpoint in [("PUT", "/api/integrations/pihole/credential"), ("DELETE", "/api/integrations/pihole/credential"),
                                 ("POST", "/api/integrations/pihole/test"), ("POST", "/api/config/import")]:
            self.assertEqual(self.client.open(endpoint, method=method).status_code, 403)

    def test_credential_api_never_returns_secret_and_bound_reuse_fails(self):
        headers = self.login()
        response = self.client.put("/api/integrations/pihole/credential", json={"baseUrl": "http://pi.local", "secret": TOKEN}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(TOKEN.encode(), response.data)
        self.assertNotIn(TOKEN.encode(), self.client.get("/api/integrations/status").data)
        with patch("web_app.fetch_integration") as fetch:
            response = self.client.post("/api/integrations/pihole/test", json={"settings": {"baseUrl": "http://other.local"}}, headers=headers)
            self.assertEqual(response.status_code, 400)
            fetch.assert_not_called()
        self.assertEqual(self.client.delete("/api/integrations/pihole/credential", headers=headers).status_code, 200)
        self.assertFalse(self.credentials.status("pihole")["credentialConfigured"])

    @patch("web_app.fetch_integration")
    def test_test_endpoint_does_not_persist_credential_or_settings(self, fetch):
        headers = self.login()
        fetch.return_value = {"configured": True, "totalQueries": 1}
        before = load_config(self.temporary.name)
        response = self.client.post("/api/integrations/pihole/test", json={"settings": {"baseUrl": "http://pi.local"}, "secret": TOKEN}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(TOKEN.encode(), response.data)
        self.assertFalse(self.credentials.path.exists())
        self.assertEqual(load_config(self.temporary.name), before)

    def test_export_and_restore_preserve_auth_and_separate_vault(self):
        headers = self.login()
        self.credentials.put("pihole", "http://pi.local", TOKEN)
        vault_before = self.credentials.path.read_bytes()
        auth_path = Path(self.temporary.name) / "auth.json"
        auth_before = auth_path.read_bytes()
        response = self.client.get("/api/config/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertNotIn(TOKEN.encode(), response.data)
        self.assertNotIn(b"2468", response.data)
        config = json.loads(response.data)
        config["carousel"]["enabled"] = True
        restored = self.client.post("/api/config/import", json=config, headers=headers)
        self.assertEqual(restored.status_code, 200)
        self.assertTrue(load_config(self.temporary.name)["carousel"]["enabled"])
        self.assertEqual(self.credentials.path.read_bytes(), vault_before)
        self.assertEqual(auth_path.read_bytes(), auth_before)
        config["integrations"]["homeassistant"]["secret"] = TOKEN
        self.assertEqual(self.client.post("/api/config/import", json=config, headers=headers).status_code, 400)
        self.assertTrue(load_config(self.temporary.name)["carousel"]["enabled"])

    def test_malformed_requests_unknown_connector_and_private_credential_get(self):
        headers = self.login()
        for payload in [None, [], {"baseUrl": "http://pi.local", "secret": TOKEN, "headers": {}}]:
            self.assertEqual(self.client.put("/api/integrations/pihole/credential", json=payload, headers=headers).status_code, 400)
        self.assertEqual(self.client.put("/api/integrations/other/credential", json={"baseUrl": "http://pi.local", "secret": TOKEN}, headers=headers).status_code, 400)
        self.assertEqual(self.client.get("/api/integrations/pihole/credential").status_code, 405)
        self.assertEqual(self.client.post("/api/config/import", json=[], headers=headers).status_code, 400)
        self.assertEqual(self.client.get("/credentials.json").status_code, 404)


if __name__ == "__main__":
    unittest.main()
