import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard.config import default_config, normalize_config
from dashboard.providers import fetch_custom_page
from dashboard.rendering import GRAY, GREEN, RED, custom_status, render_page
from dashboard.source_templates import inspect_source_sample, public_source_templates
from web_app import create_app


def definition(template):
    fields = dict(template["fields"])
    value_path = fields.pop("valuePath")
    secondary_path = fields.pop("secondaryPath")
    return {"id": "custom:" + template["id"], **fields,
            "source": {"type": "http-json", "url": "http://example.invalid/metrics",
                       "valuePath": value_path, "secondaryPath": secondary_path}}


def inspect_payload(sample, value_path="value", secondary_path=""):
    return {"sample": sample, "valuePath": value_path, "secondaryPath": secondary_path}


class SourceTemplateTests(unittest.TestCase):
    def test_catalog_has_unique_ids_and_no_destinations_or_commands(self):
        templates = public_source_templates()
        self.assertEqual(len(templates), 9)
        self.assertEqual(len({item["id"] for item in templates}), 9)
        for template in templates:
            self.assertEqual(set(template) - {"endpoint"}, {"id", "name", "description", "fields", "sample"})
            self.assertNotIn("url", template["fields"])
            self.assertNotIn("secret", template["fields"])
            self.assertNotIn("script", template["fields"])

    def test_catalog_returns_independent_deep_copies(self):
        first = public_source_templates()
        first[0]["sample"]["value"] = "changed"
        first[0]["fields"]["title"] = "changed"
        self.assertEqual(public_source_templates()[0]["sample"]["value"], 42)
        self.assertNotEqual(public_source_templates()[0]["fields"]["title"], "changed")

    def test_all_templates_create_valid_existing_custom_definitions(self):
        for template in public_source_templates():
            with self.subTest(template=template["id"]):
                item = definition(template)
                config = normalize_config({"customPages": [item]})
                self.assertEqual(config["customPages"][0]["id"], item["id"])
                self.assertFalse(next(page for page in config["pages"] if page["id"] == item["id"])["enabled"])

    def test_examples_use_same_extraction_as_real_http_responses(self):
        for template in public_source_templates():
            with self.subTest(template=template["id"]):
                item = definition(template)
                expected = inspect_source_sample(inspect_payload(template["sample"], item["source"]["valuePath"], item["source"]["secondaryPath"]))
                with patch("dashboard.providers.fetch_json", return_value=template["sample"]):
                    self.assertEqual(fetch_custom_page(item), expected)

    def test_all_examples_render_in_existing_native_layouts(self):
        for template in public_source_templates():
            item = definition(template)
            config = normalize_config({"customPages": [item], "pages": [{"id": item["id"], "enabled": True, "refreshSeconds": 60}]})
            values = inspect_source_sample(inspect_payload(template["sample"], item["source"]["valuePath"], item["source"]["secondaryPath"]))
            image = render_page(item["id"], {"custom": values}, config)
            self.assertEqual(image.size, (240, 240))
            self.assertEqual(image.mode, "RGB")

    def test_inspector_handles_root_arrays_optional_details_and_scalar_types(self):
        for value in (0, False, True, None, 28.1, "ONLINE"):
            with self.subTest(value=value):
                self.assertEqual(inspect_source_sample(inspect_payload([{"value": value}], "0.value")), {"value": value, "secondary": None})

    def test_inspector_rejects_unknown_fields_bad_shapes_and_paths(self):
        invalid = [None, [], {}, {**inspect_payload({"value": 1}), "url": "http://example.invalid"}]
        invalid += [inspect_payload(sample) for sample in (None, "text", 4, True)]
        invalid += [inspect_payload({"value": 1}, path) for path in (None, [], 3, "", "$.value", "value[0]", "a" * 121)]
        invalid += [inspect_payload({"value": 1}, "value", path) for path in (None, [], "$.detail")]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                inspect_source_sample(payload)

    def test_inspector_rejects_missing_and_nonscalar_selections(self):
        for sample, path in (({}, "value"), ({"value": {}}, "value"), ({"value": []}, "value"), ({"items": []}, "items.0.value")):
            with self.assertRaises(ValueError):
                inspect_source_sample(inspect_payload(sample, path))

    def test_inspector_bounds_utf8_sample_and_selected_strings(self):
        result = inspect_source_sample(inspect_payload({"value": "a" * 200}))
        self.assertEqual(len(result["value"]), 160)
        self.assertTrue(result["value"].endswith("..."))
        with self.assertRaisesRegex(ValueError, "32 KiB"):
            inspect_source_sample(inspect_payload({"value": "á" * 17000}))

    def test_inspector_rejects_nonfinite_numbers_even_when_not_selected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                inspect_source_sample(inspect_payload({"value": 1, "other": value}))

    def test_status_unknown_and_null_are_neutral_not_false_failures(self):
        for value in ("UNKNOWN", "updating", "", None, 7):
            self.assertEqual(custom_status(value)[1], GRAY)
        for value in (True, "OK", "ONLINE", "healthy", 1):
            self.assertEqual(custom_status(value), ("OPERACIONAL", GREEN))
        for value in (False, "OFFLINE", "unhealthy", "error", 0):
            self.assertEqual(custom_status(value), ("ATENÇÃO", RED))

    def test_status_render_uses_neutral_indicator_for_unknown_and_null(self):
        item = definition(public_source_templates()[1])
        config = normalize_config({"customPages": [item], "pages": [{"id": item["id"], "enabled": True, "refreshSeconds": 60}]})
        for value in ("unavailable", None):
            image = render_page(item["id"], {"custom": {"value": value, "secondary": "Detalhe longo " * 30}}, config)
            self.assertEqual(image.getpixel((28, 180)), GRAY)


class SourceTemplateApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app({"STATE_DIR": self.temporary.name, "TESTING": True, "SECRET_KEY": "fixture-only"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary.cleanup()

    def login(self):
        return self.client.post("/api/auth/setup", json={"pin": "2468"}).get_json()["csrfToken"]

    def test_catalog_and_inspector_require_authentication_and_inspection_csrf(self):
        payload = inspect_payload({"value": 42})
        self.assertEqual(self.client.get("/api/catalog").status_code, 401)
        self.assertEqual(self.client.post("/api/sources/inspect", json=payload).status_code, 401)
        csrf = self.login()
        self.assertEqual(self.client.post("/api/sources/inspect", json=payload).status_code, 403)
        self.assertEqual(self.client.post("/api/sources/inspect", json=payload, headers={"X-CSRF-Token": "bad"}).status_code, 403)
        self.assertEqual(self.client.post("/api/sources/inspect", json=payload, headers={"X-CSRF-Token": csrf}).status_code, 200)
        self.assertEqual(len(self.client.get("/api/catalog").get_json()["sourceTemplates"]), 9)

    def test_inspection_does_not_query_network_write_state_or_echo_unused_fields(self):
        csrf = self.login()
        root = Path(self.temporary.name)
        before = {path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}
        sample = {"value": 42, "unused": "private-example-not-to-echo"}
        with patch("dashboard.providers.fetch_json") as fetch, patch("web_app.save_config") as save:
            response = self.client.post("/api/sources/inspect", json=inspect_payload(sample), headers={"X-CSRF-Token": csrf})
        self.assertEqual(response.get_json(), {"ok": True, "value": 42, "secondary": None})
        fetch.assert_not_called()
        save.assert_not_called()
        self.assertNotIn(sample["unused"], response.get_data(as_text=True))
        self.assertEqual({path.name: path.read_bytes() for path in root.iterdir() if path.is_file()}, before)

    def test_inspector_rejects_bad_json_oversize_and_excessive_depth(self):
        csrf = self.login()
        headers = {"X-CSRF-Token": csrf}
        self.assertEqual(self.client.post("/api/sources/inspect", data="not json", content_type="application/json", headers=headers).status_code, 400)
        self.assertEqual(self.client.post("/api/sources/inspect", json=inspect_payload({"value": "a" * 33000}), headers=headers).status_code, 400)
        self.assertEqual(self.client.post("/api/sources/inspect", data="x" * 66000, content_type="application/json", headers=headers).status_code, 413)
        nested = '{"sample":' + '[' * 1500 + '0' + ']' * 1500 + ',"valuePath":"value","secondaryPath":""}'
        self.assertEqual(self.client.post("/api/sources/inspect", data=nested, content_type="application/json", headers=headers).status_code, 400)

    def test_created_template_is_plain_custom_page_in_backup_and_restore(self):
        csrf = self.login()
        for template in public_source_templates():
            with self.subTest(template=template["id"]):
                item = definition(template)
                config = default_config()
                config["customPages"] = [item]
                saved = self.client.put("/api/config", json=config, headers={"X-CSRF-Token": csrf})
                self.assertEqual(saved.status_code, 200)
                exported = json.loads(self.client.get("/api/config/export").data)
                self.assertEqual(exported["customPages"][0]["source"]["valuePath"], item["source"]["valuePath"])
                self.assertNotIn("sourceTemplates", exported)
                self.assertNotIn("sample", exported["customPages"][0])
                self.assertNotIn("endpoint", exported["customPages"][0])
                restored = self.client.post("/api/config/import", json=exported, headers={"X-CSRF-Token": csrf})
                self.assertEqual(restored.status_code, 200)
                self.assertEqual(restored.get_json(), exported)


if __name__ == "__main__":
    unittest.main()
