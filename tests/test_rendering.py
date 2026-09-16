import unittest

from dashboard.config import default_config
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
}


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


if __name__ == "__main__":
    unittest.main()
