import unittest

from dashboard.config import default_config
from dashboard.display_profiles import PROFILE_BY_ID, adapt_image
from dashboard.rendering import render_page


SNAPSHOT = {
    "cpuPercent": 38,
    "ramPercent": 57,
    "temperatureC": 63.4,
    "uptime": "1d 2h",
    "hostname": "raspberrypi-laboratorio-com-nome-longo",
    "network": {
        "defaultInterface": "eth0",
        "ethernetInterface": "eth0",
        "ethernetIp": "192.168.100.11",
        "wifiInterface": "wlx001122334455",
        "wifiIp": "192.168.100.94",
        "wifiSsid": "Rede de laboratório",
        "wifiSignal": "-48 dBm",
        "tailscaleIp": "100.64.0.10",
    },
    "model": "Raspberry Pi 5 Model B Rev 1.0 com descrição propositalmente longa",
    "kernel": "6.12.34+rpt-rpi-v8-muito-longo-para-a-tela",
    "usbCount": 4,
    "spi": True,
    "diskPercent": 71,
    "throttled": "0x0",
    "weather": {
        "configured": True,
        "locationName": "Boa Vista",
        "temperatureC": 31.2,
        "apparentC": 34.1,
        "weatherCode": 2,
        "isDay": True,
        "maximumC": 34,
        "minimumC": 25,
        "precipitationProbability": 42,
        "loading": False,
        "stale": False,
        "error": None,
    },
    "sysops": {
        "diskPercent": 71,
        "gateway": "192.168.100.1",
        "pingMs": 2.4,
        "throttling": "OK",
        "services": [{"name": "ssh", "status": "active"}],
        "loading": False,
    },
    "custom": {"value": 318, "secondary": "atualizado agora", "loading": False},
}


def enabled_config(*page_ids):
    config = default_config()
    for page in config["pages"]:
        page["enabled"] = page["id"] in page_ids
    return config


class RenderingTests(unittest.TestCase):
    def test_all_pages_render_to_native_display_size(self):
        config = default_config()
        for page_id in ("status", "network", "hardware"):
            with self.subTest(page_id=page_id):
                image = render_page(page_id, SNAPSHOT, config)
                self.assertEqual(image.size, (240, 240))
                self.assertEqual(image.mode, "RGB")

    def test_missing_metrics_render_without_error(self):
        config = default_config()
        empty = {key: None for key in SNAPSHOT}
        empty["ethernet"] = None
        empty["wifi"] = None
        for page_id in ("status", "network", "hardware"):
            render_page(page_id, empty, config)

    def test_fahrenheit_configuration_renders(self):
        config = default_config()
        config["temperatureUnit"] = "fahrenheit"
        image = render_page("status", SNAPSHOT, config)
        self.assertEqual(image.size, (240, 240))

    def test_weather_and_sysops_pages_render(self):
        for page_id in ("weather", "sysops"):
            with self.subTest(page_id=page_id):
                image = render_page(page_id, SNAPSHOT, enabled_config(page_id))
                self.assertEqual(image.size, (240, 240))

    def test_custom_metric_page_renders(self):
        config = default_config()
        config["customPages"] = [
            {
                "id": "custom:energia",
                "title": "Energia",
                "description": "Consumo",
                "layout": "metric",
                "valueLabel": "CONSUMO",
                "unit": "W",
                "accent": "green",
                "source": {"type": "http-json", "url": "http://localhost/status", "valuePath": "power", "secondaryPath": ""},
            }
        ]
        config["pages"] = [{"id": "custom:energia", "enabled": True, "refreshSeconds": 60}]
        image = render_page("custom:energia", SNAPSHOT, config)
        self.assertEqual(image.size, (240, 240))

    def test_canonical_image_can_adapt_to_monochrome_profile(self):
        image = render_page("status", SNAPSHOT, default_config())
        adapted = adapt_image(image, PROFILE_BY_ID["ssd1306-128x64"])
        self.assertEqual(adapted.size, (128, 64))
        self.assertEqual(adapted.mode, "1")


if __name__ == "__main__":
    unittest.main()
