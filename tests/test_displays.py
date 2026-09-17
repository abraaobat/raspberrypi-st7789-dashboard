import copy
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from dashboard.config import default_config, ConfigError, normalize_config
from dashboard.display_profiles import public_profiles, runtime_profile
from dashboard.display_backends import create_display
from dashboard.compact_rendering import compact_lines
from dashboard.rendering import render_page
from tests.test_rendering import SNAPSHOT
from tests.test_config import CUSTOM_PAGE
from web_app import create_app


class DisplayCompatibilityTests(unittest.TestCase):
    def test_all_profiles_preview_available_but_experimental_hardware_not_validated(self):
        profiles = public_profiles()
        self.assertTrue(all(p["previewAvailable"] and p["driverImplemented"] for p in profiles))
        self.assertEqual([p["id"] for p in profiles if p["hardwareValidated"]], ["st7789-240x240"])
        config = default_config()
        config["displayProfile"] = "ssd1306-128x64"
        with self.assertRaises(ConfigError):
            normalize_config(config)

    def test_default_runtime_preserved_and_only_operator_overrides_hardware(self):
        config = default_config()
        with patch.dict(os.environ, {"ST7789_DISPLAY_PROFILE": ""}):
            self.assertEqual(runtime_profile(config).id, "st7789-240x240")
        with patch.dict(os.environ, {"ST7789_DISPLAY_PROFILE": "ssd1306-128x64"}):
            self.assertEqual(render_page("status", SNAPSHOT, config).size, (128, 64))
        self.assertEqual(config["displayProfile"], "st7789-240x240")
        with patch.dict(os.environ, {"ST7789_DISPLAY_PROFILE": "arbitrary"}), self.assertRaises(ValueError):
            runtime_profile(config)

    def test_all_pages_have_native_compact_and_landscape_canvases(self):
        config = default_config()
        config["customPages"] = [copy.deepcopy(CUSTOM_PAGE)]
        config = normalize_config(config)
        for p in config["pages"]:
            p["enabled"] = True
        snapshot = copy.deepcopy(SNAPSHOT)
        snapshot.update({"clock": {"time": "23:59:58", "date": "17/09/2026"},
                         "pomodoro": {"status": "paused", "remainingSeconds": 3599, "progress": 0.3},
                         "mqtt": {"available": True, "sensors": [{"label": "Energia", "value": "123", "unit": "W", "retained": True}]},
                         "docker": {"available": True, "containers": [{"name": "pihole", "state": "running", "health": None}], "total": 1, "running": 1, "stopped": 0, "unhealthy": 0},
                         "custom": {"value": 123.4, "secondary": "online"}})
        for page in config["pages"]:
            for profile, size, mode in [("ssd1306-128x64", (128, 64), "1"), ("ili9341-320x240", (320, 240), "RGB")]:
                with self.subTest(page=page["id"], profile=profile):
                    image = render_page(page["id"], snapshot, config, target_profile=profile)
                    self.assertEqual((image.size, image.mode), (size, mode))
                    self.assertIsNotNone(image.getbbox())

    def test_compact_data_uses_real_keys_and_unavailable_states_not_false_off(self):
        config = default_config()
        lines = compact_lines("weather", SNAPSHOT, config)
        self.assertEqual(lines[-1], "CHUVA 42%")
        self.assertIn("SPI ON", compact_lines("hardware", SNAPSHOT, config)[-1])
        values = {"homeassistant": {"entities": [{"label": "Porta", "state": "unavailable", "available": False}]}}
        self.assertIn("SEM DADOS", compact_lines("homeassistant", values, config)[0])
        self.assertNotIn("OFF", compact_lines("homeassistant", values, config)[0])

    def test_st7789_driver_call_and_pins_are_unchanged(self):
        module = Mock()
        with patch.dict(sys.modules, {"st7789": module}), patch.dict(os.environ, {"ST7789_DISPLAY_PROFILE": ""}):
            device = create_display(default_config())
        module.ST7789.assert_called_once_with(height=240, width=240, rotation=90, port=0, cs=0, dc=25, rst=27, spi_speed_hz=40_000_000)
        device.begin.assert_called_once()

    def test_optional_luma_drivers_use_explicit_bus_and_correct_orientation(self):
        serial, oled, lcd = Mock(), Mock(), Mock()
        modules = {"luma.core.interface.serial": serial, "luma.oled.device": oled, "luma.lcd.device": lcd}
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"ST7789_DISPLAY_PROFILE": "ssd1306-128x64"}):
            self.assertIs(create_display(default_config()), oled.ssd1306.return_value)
        serial.i2c.assert_called_once_with(port=1, address=0x3C)
        oled.ssd1306.assert_called_once_with(serial.i2c.return_value, width=128, height=64, rotate=0)
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {"ST7789_DISPLAY_PROFILE": "ili9341-320x240"}):
            self.assertIs(create_display(default_config()), lcd.ili9341.return_value)
        serial.spi.assert_called_once_with(port=0, device=0, gpio_DC=25, gpio_RST=27, bus_speed_hz=16_000_000)
        lcd.ili9341.assert_called_once_with(serial.spi.return_value, width=320, height=240, rotate=0)

    def test_failed_optional_driver_initialization_releases_serial(self):
        serial, oled = Mock(), Mock()
        oled.ssd1306.side_effect = RuntimeError("device absent")
        with patch.dict(sys.modules, {"luma.core.interface.serial": serial, "luma.oled.device": oled}), patch.dict(os.environ, {"ST7789_DISPLAY_PROFILE": "ssd1306-128x64"}), self.assertRaises(RuntimeError):
            create_display(default_config())
        serial.i2c.return_value.cleanup.assert_called_once()

    def test_preview_simulation_requires_auth_and_never_imports_physical_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            client = create_app({"TESTING": True, "STATE_DIR": directory, "SECRET_KEY": "fixture"}).test_client()
            self.assertEqual(client.get("/api/preview?profile=ssd1306-128x64").status_code, 401)
            client.post("/api/auth/setup", json={"pin": "2468"})
            before = client.get("/api/config").json
            with patch("dashboard.display_backends.create_display", side_effect=AssertionError("must not open hardware")):
                for profile, size in [("ssd1306-128x64", (128, 64)), ("ili9341-320x240", (320, 240))]:
                    response = client.get(f"/api/preview?page=status&profile={profile}")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(Image.open(io.BytesIO(response.data)).size, size)
            self.assertEqual(client.get("/api/preview?profile=arbitrary").status_code, 400)
            self.assertEqual(client.get("/api/config").json, before)
            self.assertEqual(client.get("/api/catalog").json["activeDisplayProfile"], "st7789-240x240")


if __name__ == "__main__":
    unittest.main()
