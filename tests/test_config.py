import json
import tempfile
import unittest
from pathlib import Path

from dashboard.config import ConfigError, default_config, load_config, save_config


class ConfigTests(unittest.TestCase):
    def test_round_trip_preserves_order_and_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = default_config()
            payload["temperatureUnit"] = "fahrenheit"
            payload["carousel"]["enabled"] = True
            payload["pages"] = list(reversed(payload["pages"]))

            saved = save_config(payload, directory)

            self.assertEqual(load_config(directory), saved)
            self.assertEqual(saved["pages"][0]["id"], "hardware")
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


if __name__ == "__main__":
    unittest.main()
