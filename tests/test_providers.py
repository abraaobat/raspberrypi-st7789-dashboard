import unittest
from unittest.mock import patch

from dashboard.providers import fetch_custom_page, fetch_weather, json_path, validate_source_url


class ProviderTests(unittest.TestCase):
    def test_json_path_supports_objects_and_array_indexes(self):
        payload = {"items": [{"state": "online"}]}
        self.assertEqual(json_path(payload, "items.0.state"), "online")
        with self.assertRaises(ValueError):
            json_path(payload, "items.1.state")

    @patch("dashboard.providers.socket.getaddrinfo")
    def test_source_url_blocks_link_local_but_allows_lan(self, getaddrinfo):
        getaddrinfo.return_value = [(2, 1, 6, "", ("192.168.1.20", 80))]
        validate_source_url("http://dashboard.local/status")

        getaddrinfo.return_value = [(2, 1, 6, "", ("169.254.169.254", 80))]
        with self.assertRaises(ValueError):
            validate_source_url("http://metadata.local/status")

    @patch("dashboard.providers.fetch_json")
    def test_weather_response_is_normalized(self, fetch_json_mock):
        fetch_json_mock.return_value = {
            "current": {"temperature_2m": 30, "apparent_temperature": 33, "weather_code": 2, "is_day": 1},
            "daily": {"temperature_2m_max": [34], "temperature_2m_min": [24], "precipitation_probability_max": [55]},
        }
        result = fetch_weather({"latitude": 2.8, "longitude": -60.7, "locationName": "Boa Vista"})
        self.assertEqual(result["locationName"], "Boa Vista")
        self.assertEqual(result["precipitationProbability"], 55)

    @patch("dashboard.providers.fetch_json")
    def test_custom_source_extracts_declared_values(self, fetch_json_mock):
        fetch_json_mock.return_value = {"data": {"power": 318, "unit": "W"}}
        definition = {
            "source": {
                "url": "http://192.168.1.10/status",
                "valuePath": "data.power",
                "secondaryPath": "data.unit",
            }
        }
        self.assertEqual(fetch_custom_page(definition), {"value": 318, "secondary": "W"})


if __name__ == "__main__":
    unittest.main()
