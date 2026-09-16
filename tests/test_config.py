import json
import tempfile
import unittest
from pathlib import Path

from dashboard.config import ConfigError, default_config, load_config, normalize_config, save_config


CUSTOM_PAGE = {
    "id": "custom:energia",
    "title": "Energia",
    "description": "Consumo instantâneo",
    "layout": "metric",
    "valueLabel": "CONSUMO",
    "unit": "W",
    "accent": "green",
    "source": {
        "type": "http-json",
        "url": "http://192.168.1.10:8080/status",
        "valuePath": "data.power",
        "secondaryPath": "data.updated",
    },
}


class ConfigTests(unittest.TestCase):
    def test_round_trip_preserves_order_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = default_config()
            payload["temperatureUnit"] = "fahrenheit"
            payload["carousel"]["enabled"] = True
            payload["pages"] = list(reversed(payload["pages"]))

            saved = save_config(payload, directory)

            self.assertEqual(load_config(directory), saved)
            self.assertEqual(saved["pages"][0]["id"], "weather")
            self.assertEqual(saved["temperatureUnit"], "fahrenheit")
            self.assertTrue(saved["carousel"]["enabled"])
            self.assertEqual(
                oct((Path(directory) / "config.json").stat().st_mode & 0o777),
                "0o600",
            )

    def test_invalid_write_does_not_replace_last_valid_config(self):
        with tempfile.TemporaryDirectory() as directory:
            original = save_config(default_config(), directory)
            invalid = default_config()
            for page in invalid["pages"]:
                page["enabled"] = False

            with self.assertRaises(ConfigError):
                save_config(invalid, directory)

            self.assertEqual(load_config(directory), original)
            json.loads((Path(directory) / "config.json").read_text(encoding="utf-8"))

    def test_corrupt_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text("{not-json", encoding="utf-8")
            self.assertEqual(load_config(directory), default_config())

    def test_legacy_page_list_gains_new_pages_without_enabling_them(self):
        legacy = default_config()
        legacy.pop("weather")
        legacy.pop("sysops")
        legacy.pop("customPages")
        legacy.pop("displayProfile")
        legacy["pages"] = legacy["pages"][:3]

        normalized = normalize_config(legacy)
        pages = {page["id"]: page for page in normalized["pages"]}

        self.assertFalse(pages["sysops"]["enabled"])
        self.assertFalse(pages["weather"]["enabled"])
        self.assertEqual(normalized["displayProfile"], "st7789-240x240")

    def test_custom_page_is_validated_and_added_to_page_order(self):
        payload = default_config()
        payload["customPages"] = [CUSTOM_PAGE]
        payload["pages"].append({"id": "custom:energia", "enabled": True, "refreshSeconds": 30})

        normalized = normalize_config(payload)

        self.assertEqual(normalized["customPages"][0]["source"]["valuePath"], "data.power")
        self.assertEqual(normalized["pages"][-1]["id"], "custom:energia")

    def test_custom_page_rejects_credentials_and_invalid_json_path(self):
        payload = default_config()
        invalid = json.loads(json.dumps(CUSTOM_PAGE))
        invalid["source"]["url"] = "http://user:secret@192.168.1.10/status"
        invalid["source"]["valuePath"] = "data[0].power"
        payload["customPages"] = [invalid]

        with self.assertRaises(ConfigError):
            normalize_config(payload)


if __name__ == "__main__":
    unittest.main()
