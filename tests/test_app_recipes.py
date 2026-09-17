import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

from dashboard.app_recipes import APP_SOURCE_TEMPLATES, build_source_url
from dashboard.config import normalize_config
from dashboard.providers import fetch_custom_page
from dashboard.rendering import render_page
from dashboard.source_templates import public_source_templates, inspect_source_sample
from tests.test_source_templates import definition
from web_app import create_app


def request(recipe="shelly-power", base="http://192.168.1.10", **parameters):
    defaults = {field["name"]: field["default"] for item in APP_SOURCE_TEMPLATES if item["id"] == recipe for field in item["endpoint"]["parameters"]}
    return {"templateId": recipe, "baseUrl": base, "parameters": {**defaults, **parameters}}


class AppRecipeTests(unittest.TestCase):
    def test_esphome_names_spaces_utf8_and_optional_subdevice_are_encoded_segments(self):
        payload = request("esphome-sensor", entityName="Temperatura externa", deviceName="Área sul")
        self.assertEqual(build_source_url(payload)["url"], "http://192.168.1.10/sensor/%C3%81rea%20sul/Temperatura%20externa")
        payload["parameters"]["deviceName"] = ""
        self.assertEqual(build_source_url(payload)["url"], "http://192.168.1.10/sensor/Temperatura%20externa")
        self.assertTrue(build_source_url(request("esphome-sensor", entityName=" Sensor "))["url"].endswith("/sensor/%20Sensor%20"))

    def test_esphome_does_not_interpret_names_as_paths_actions_or_queries(self):
        for key in ("deviceName", "entityName"):
            for value in ("..", ".", "../turn_on", "sensor/foo", "a\\b", "a\n", "a" * 81, "   ", None):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    build_source_url(request("esphome-sensor", **{key: value}))
        url = build_source_url(request("esphome-sensor", entityName="Sala?mode=on#x"))["url"]
        self.assertEqual(unquote(urlsplit(url).path), "/sensor/Sala?mode=on#x")
        self.assertEqual(urlsplit(url).query, "")

    def test_shelly_only_get_status_with_bounded_decimal_channel(self):
        for channel in ("0", "1", "63"):
            self.assertEqual(build_source_url(request(channel=channel))["url"], "http://192.168.1.10/rpc/Switch.GetStatus?id=" + channel)
        for channel in ("64", "-1", "01", "1&on=true", "0.0", 0, True, None):
            with self.subTest(channel=channel), self.assertRaises(ValueError):
                build_source_url(request(channel=channel))
        with self.assertRaises(ValueError):
            build_source_url(request(method="Switch.Set"))

    def test_prometheus_encodes_query_without_query_parameter_injection(self):
        expression = 'scalar(up{job="a&b",instance="pi:9090"})'
        parts = urlsplit(build_source_url(request("prometheus-scalar", expression=expression))["url"])
        self.assertEqual(parts.path, "/api/v1/query")
        self.assertEqual(parse_qs(parts.query), {"query": [expression], "timeout": ["2s"]})
        self.assertEqual(parts.fragment, "")

    def test_helper_never_claims_to_parse_or_execute_promql(self):
        self.assertIn("query=up", build_source_url(request("prometheus-scalar", expression="up"))["url"])
        for expression in ("", "x" * 513, "up\n", None, "\ud800"):
            with self.assertRaises(ValueError):
                build_source_url(request("prometheus-scalar", expression=expression))
        with self.assertRaisesRegex(ValueError, "2048"):
            build_source_url(request("prometheus-scalar", expression="漢" * 512))

    def test_base_origin_preserves_port_and_https_and_normalizes_idna(self):
        for base, prefix in (("https://PI.local:8443/", "https://pi.local:8443"), ("http://127.0.0.1:9090", "http://127.0.0.1:9090"), ("https://café.example", "https://xn--caf-dma.example"), ("https://[2001:4860:4860::8888]:443", "https://[2001:4860:4860::8888]:443")):
            with self.subTest(base=base):
                self.assertEqual(build_source_url(request(base=base))["url"], prefix + "/rpc/Switch.GetStatus?id=0")

    def test_base_rejects_credentials_paths_controls_queries_and_invalid_ports(self):
        invalid = ("ftp://pi.local", "http://user:pass@pi.local", "http://@pi.local", "http://pi.local/rpc/Switch.Set", "http://pi.local?", "http://pi.local#", "http://pi.local:0", "http://pi.local:65536", "http://pi.local:", "http://pi.local/a/../", "http://pi.local\\@other", "http://pi.local\n", "http://pi local", "http://pi%2elocal", "http://[2001:4860::1]evil", "http://-pi.local", None)
        for base in invalid:
            with self.subTest(base=base), self.assertRaises(ValueError):
                build_source_url(request(base=base))

    def test_literal_unsafe_addresses_rejected_without_dns(self):
        for base in ("http://169.254.169.254", "http://0.0.0.0", "http://224.0.0.1", "http://[fe80::1]", "http://[::ffff:169.254.1.1]", "http://[fe80::1%25eth0]"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                build_source_url(request(base=base))

    def test_closed_payload_rejects_free_recipe_fields_and_wrong_types(self):
        invalid = (None, [], {}, {**request(), "url": "http://pi.local"}, {**request(), "templateId": []}, {**request(), "templateId": "energy"}, {**request(), "parameters": []}, {**request(), "parameters": {}}, {**request(), "parameters": {"channel": "0", "on": "true"}})
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                build_source_url(payload)

    def test_all_builders_are_offline_including_dns(self):
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS forbidden")), patch("dashboard.providers.fetch_json", side_effect=AssertionError("HTTP forbidden")):
            for item in APP_SOURCE_TEMPLATES:
                self.assertTrue(build_source_url(request(item["id"], base="http://not-resolved.invalid"))["ok"])

    def test_metadata_deep_copies_and_no_destination_or_secret(self):
        templates = public_source_templates()
        apps = [item for item in templates if "endpoint" in item]
        self.assertEqual(len(apps), 3)
        for item in apps:
            self.assertEqual(set(item["endpoint"]), {"help", "docsUrl", "parameters"})
            self.assertTrue(item["endpoint"]["docsUrl"].startswith("https://"))
        apps[0]["endpoint"]["parameters"][0]["default"] = "changed"
        self.assertEqual(public_source_templates()[6]["endpoint"]["parameters"][0]["default"], "Temperatura externa")

    def test_new_examples_render_on_all_three_software_profiles(self):
        for template in APP_SOURCE_TEMPLATES:
            item = definition(template)
            config = normalize_config({"customPages": [item], "pages": [{"id": item["id"], "enabled": True, "refreshSeconds": 60}]})
            values = inspect_source_sample({"sample": template["sample"], "valuePath": item["source"]["valuePath"], "secondaryPath": item["source"]["secondaryPath"]})
            for profile, size, mode in (("st7789-240x240", (240, 240), "RGB"), ("ssd1306-128x64", (128, 64), "1"), ("ili9341-320x240", (320, 240), "RGB")):
                with self.subTest(template=template["id"], profile=profile):
                    image = render_page(item["id"], {"custom": values}, config, target_profile=profile)
                    self.assertEqual((image.size, image.mode), (size, mode))

    def test_missing_shelly_power_and_prometheus_vectors_do_not_invent_a_value(self):
        for sample, path in (({"id": 0, "output": True}, "apower"), ({"data": {"result": [{"value": [0, "1"]}]}}, "data.result.1"), ({"data": {"result": [{}, {}]}}, "data.result.1")):
            with self.assertRaises(ValueError):
                inspect_source_sample({"sample": sample, "valuePath": path, "secondaryPath": ""})
        for value in ("NaN", "0", "1"):
            result = inspect_source_sample({"sample": {"data": {"result": [0, value]}}, "valuePath": "data.result.1", "secondaryPath": ""})
            self.assertEqual(result["value"], value)

    def test_real_get_requests_to_fictitious_app_routes_use_same_selected_values(self):
        seen = []
        samples = {"/sensor/Temperatura%20externa": APP_SOURCE_TEMPLATES[0]["sample"], "/rpc/Switch.GetStatus?id=0": APP_SOURCE_TEMPLATES[1]["sample"], "/api/v1/query?query=scalar%28up%7Bjob%3D%22prometheus%22%7D%29&timeout=2s": APP_SOURCE_TEMPLATES[2]["sample"]}

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append((self.command, self.path))
                body = json.dumps(samples[self.path]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            for template in APP_SOURCE_TEMPLATES:
                item = definition(template)
                item["source"]["url"] = build_source_url(request(template["id"], base=f"http://127.0.0.1:{server.server_port}"))["url"]
                values = fetch_custom_page(item)
                self.assertEqual(values["value"], {"esphome-sensor": 28.1, "shelly-power": 318, "prometheus-scalar": "1"}[template["id"]])
            self.assertEqual(seen, [("GET", path) for path in samples])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


class AppRecipeApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app({"STATE_DIR": self.temporary.name, "TESTING": True, "SECRET_KEY": "fixture-only"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary.cleanup()

    def test_builder_requires_authentication_csrf_and_post(self):
        self.assertEqual(self.client.post("/api/sources/build-url", json=request()).status_code, 401)
        csrf = self.client.post("/api/auth/setup", json={"pin": "2468"}).get_json()["csrfToken"]
        self.assertEqual(self.client.get("/api/sources/build-url").status_code, 405)
        for headers in ({}, {"X-CSRF-Token": "wrong"}):
            self.assertEqual(self.client.post("/api/sources/build-url", json=request(), headers=headers).status_code, 403)
        self.assertEqual(self.client.post("/api/sources/build-url", json=request(), headers={"X-CSRF-Token": csrf}).get_json(), build_source_url(request()))

    def test_api_builder_does_not_resolve_hosts_save_state_or_return_credentials(self):
        csrf = self.client.post("/api/auth/setup", json={"pin": "2468"}).get_json()["csrfToken"]
        root = Path(self.temporary.name)
        before = {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}
        with patch("socket.getaddrinfo", side_effect=AssertionError("DNS forbidden")), patch("dashboard.providers.fetch_json") as fetch, patch("web_app.save_config") as save:
            response = self.client.post("/api/sources/build-url", json=request(base="https://not-resolved.invalid"), headers={"X-CSRF-Token": csrf})
            rejected = self.client.post("/api/sources/build-url", json=request(base="http://private-secret@pi.local"), headers={"X-CSRF-Token": csrf})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(rejected.status_code, 400)
        self.assertNotIn("private-secret", rejected.get_data(as_text=True))
        fetch.assert_not_called()
        save.assert_not_called()
        self.assertEqual({path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}, before)

    def test_api_rejects_malformed_json_and_request_size(self):
        csrf = self.client.post("/api/auth/setup", json={"pin": "2468"}).get_json()["csrfToken"]
        headers = {"X-CSRF-Token": csrf}
        self.assertEqual(self.client.post("/api/sources/build-url", data="not json", content_type="application/json", headers=headers).status_code, 400)
        self.assertEqual(self.client.post("/api/sources/build-url", data="x" * 66000, content_type="application/json", headers=headers).status_code, 413)
