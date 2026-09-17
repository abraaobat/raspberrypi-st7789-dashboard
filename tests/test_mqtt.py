import copy
import io
import json
import os
import socket
import ssl
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from PIL import Image

from dashboard.config import default_config, normalize_config, save_config, load_config, ConfigError
from dashboard.credentials import CredentialStore, CredentialError
from dashboard.mqtt_settings import broker_url, mqtt_settings, MQTTError, encode_credentials
from dashboard.mqtt_monitor import fetch_mqtt, sensor_value, _receive, MAX_PACKET_BYTES
from dashboard.providers import DataHub
from dashboard.rendering import render_page
from tests.mqtt_fixture import FakeMQTT, packet
from web_app import create_app


def settings(address="mqtt://127.0.0.1:1883"):
    return {"brokerUrl": address, "allowInsecureMqtt": True, "sensors": [
        {"label": "Sala", "topic": "casa/sala/temperatura", "format": "text", "valuePath": "", "unit": "°C"},
        {"label": "Energia", "topic": "casa/energia", "format": "json", "valuePath": "sensor.power", "unit": "W"},
    ]}


class MQTTSettingsTests(unittest.TestCase):
    def test_broker_canonical_addresses_and_rejected_secret_urls(self):
        self.assertEqual(broker_url("mqtts://EXAMPLE.com/"), "mqtts://example.com:8883")
        self.assertEqual(broker_url("mqtt://[::1]"), "mqtt://[::1]:1883")
        for address in ["http://host", "mqtt://user:password@host", "mqtt://host/path", "mqtt://host?token=secret",
                        "mqtt://host:0", "mqtt://host:65536", "mqtt://host#x", "mqtt://a%20b", "mqtt://a\\b"]:
            with self.subTest(address=address), self.assertRaises(MQTTError):
                broker_url(address)

    def test_closed_settings_reject_secrets_wildcards_duplicates_bad_paths(self):
        base = settings()
        self.assertEqual(mqtt_settings(base), base)
        bad = []
        for field, value in [("password", "secret"), ("allowInsecureMqtt", "true"), ("sensors", [{}] * 5)]:
            candidate = copy.deepcopy(base)
            candidate[field] = value
            bad.append(candidate)
        for field, value in [("topic", "casa/#"), ("topic", "casa/+"), ("topic", "$share/group/casa"),
                             ("topic", "a\0b"), ("label", ""), ("format", "script"), ("valuePath", "x.y")]:
            candidate = copy.deepcopy(base)
            candidate["sensors"][0][field] = value
            bad.append(candidate)
        duplicate = copy.deepcopy(base)
        duplicate["sensors"].append(duplicate["sensors"][0])
        bad.append(duplicate)
        for candidate in bad:
            with self.subTest(candidate=candidate), self.assertRaises(MQTTError):
                mqtt_settings(candidate)

    def test_migration_and_backup_are_optional_and_preserve_order(self):
        config = default_config()
        config.pop("mqtt")
        config["pages"] = [page for page in reversed(config["pages"]) if page["id"] != "mqtt"]
        migrated = normalize_config(config)
        self.assertEqual(migrated["pages"][:-1], config["pages"])
        self.assertFalse(migrated["pages"][-1]["enabled"])
        migrated["mqtt"] = settings()
        with tempfile.TemporaryDirectory() as directory:
            saved = save_config(migrated, directory)
            self.assertEqual(load_config(directory), saved)
        migrated["pages"][-1]["refreshSeconds"] = 1
        with self.assertRaises(ConfigError):
            normalize_config(migrated)

    def test_scalar_payloads_missing_null_invalid_and_bounded_text(self):
        sensor = settings()["sensors"][1]
        for payload, expected in [(b'{"sensor":{"power":0}}', "0"), (b'{"sensor":{"power":false}}', "false"),
                                  (b'{"sensor":{"power":null}}', None), (b'{"sensor":{"power":12.5}}', "12.5")]:
            self.assertEqual(sensor_value(payload, sensor), expected)
        for payload in [b"invalid", b'{"sensor":{"power":{}}}', b'{"sensor":{}}', b'\xff', b'{"sensor":{"power":1e10000}}', b'{"sensor":{"power":"\\ud800"}}']:
            with self.assertRaises(MQTTError):
                sensor_value(payload, sensor)
        self.assertEqual(len(sensor_value(b"a" * 200, settings()["sensors"][0])), 80)


class MQTTTransportTests(unittest.TestCase):
    def test_exact_qos_zero_clean_session_anonymous_no_publish_or_will(self):
        with FakeMQTT() as broker:
            result = fetch_mqtt(settings(broker.url))
            self.assertEqual(result["received"], 2)
            self.assertEqual([s["value"] for s in result["sensors"]], ["28.5", "123.4"])
            self.assertTrue(all(s["retained"] for s in result["sensors"]))
            self.assertEqual(broker.connect_payloads[0][:10], b"\x00\x04MQTT\x04\x02\x00\x0f")
            self.assertEqual(broker.calls[1]["qos"], [0, 0])
            self.assertTrue(all(c["type"] in {1, 8, 14} for c in broker.calls))

    def test_private_credential_is_sent_only_in_connect_not_result(self):
        with FakeMQTT() as broker:
            secret = encode_credentials("readonly-user", "fixture-only-password")
            result = fetch_mqtt(settings(broker.url), secret)
            self.assertEqual(broker.connect_payloads[0][7], 194)
            self.assertIn(b"fixture-only-password", broker.connect_payloads[0])
            self.assertNotIn("fixture-only-password", json.dumps(result))
            self.assertNotIn("readonly-user", json.dumps(result))

    def test_live_values_before_suback_and_per_sensor_invalid_json(self):
        with FakeMQTT() as broker:
            broker.before_suback, broker.retained = True, False
            broker.messages["casa/energia"] = b"not-json"
            result = fetch_mqtt(settings(broker.url))
            self.assertEqual(result["received"], 1)
            self.assertFalse(result["sensors"][0]["retained"])
            self.assertIsNone(result["sensors"][1]["value"])
            self.assertIn("payload inválido", result["sensors"][1]["error"])

    def test_missing_values_timeout_is_not_off_or_zero(self):
        with FakeMQTT() as broker:
            broker.messages = {}
            started = time.monotonic()
            result = fetch_mqtt(settings(broker.url), timeout=0.15)
            self.assertLess(time.monotonic() - started, 0.8)
            self.assertTrue(result["available"])
            self.assertEqual(result["received"], 0)
            self.assertTrue(all(s["value"] is None for s in result["sensors"]))

    def test_subscription_acl_refusal_and_connection_refusal_are_safe(self):
        with FakeMQTT() as broker:
            broker.suback_codes = [128, 128]
            broker.messages = {}
            result = fetch_mqtt(settings(broker.url), timeout=0.3)
            self.assertTrue(all("recusada" in s["error"] for s in result["sensors"]))
            broker.connack = b"\x00\x05"
            with self.assertRaisesRegex(MQTTError, "recusada"):
                fetch_mqtt(settings(broker.url))

    def test_oversized_declared_packet_rejected_before_body_allocation(self):
        with FakeMQTT() as broker:
            broker.raw_packets = [b"\x31\x81\x40"]  # 8193, body deliberately absent.
            with self.assertRaisesRegex(MQTTError, "8 KiB"):
                fetch_mqtt(settings(broker.url))

    def test_unrequested_topic_or_qos_one_or_invalid_ack_rejected(self):
        for message in [packet(0x31, b"\x00\x03bad1"), packet(0x32, b"\x00\x03abc\x00\x011")]:
            with FakeMQTT() as broker:
                broker.raw_packets = [message]
                with self.assertRaises(MQTTError):
                    fetch_mqtt(settings(broker.url))
        with FakeMQTT() as broker:
            broker.suback_codes = [1, 0]
            with self.assertRaisesRegex(MQTTError, "assinatura"):
                fetch_mqtt(settings(broker.url))

    def test_total_bytes_and_packet_flood_are_bounded(self):
        topic = b"casa/sala/temperatura"
        for payload, count, error in [(b"a" * 5000, 7, "32 KiB"), (b"1", 32, "32 pacotes")]:
            with FakeMQTT() as broker:
                broker.raw_packets = [packet(0x31, len(topic).to_bytes(2, "big") + topic + payload)] * count
                with self.assertRaisesRegex(MQTTError, error):
                    fetch_mqtt(settings(broker.url))

    def test_slow_packet_has_total_deadline_not_per_byte_timeout(self):
        with FakeMQTT() as broker:
            broker.slow_packet = packet(0x31, b"\x00\x15casa/sala/temperatura" + b"1" * 200)
            started = time.monotonic()
            with self.assertRaisesRegex(MQTTError, "incompleto"):
                fetch_mqtt(settings(broker.url), timeout=0.16)
            self.assertLess(time.monotonic() - started, 0.8)

    def test_plaintext_requires_consent_and_checked_local_addresses(self):
        with FakeMQTT() as broker:
            candidate = settings(broker.url)
            candidate["allowInsecureMqtt"] = False
            with self.assertRaisesRegex(MQTTError, "não permitido"):
                fetch_mqtt(candidate)
            self.assertEqual(broker.calls, [])
        for ip in ["8.8.8.8", "169.254.169.254", "224.0.0.1", "0.0.0.0"]:
            with patch("dashboard.http_client.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 1883))]), patch("dashboard.mqtt_monitor.socket.create_connection") as connect:
                with self.assertRaises(MQTTError):
                    fetch_mqtt(settings("mqtt://somehost:1883"), encode_credentials("user", "secret"))
                connect.assert_not_called()

    def test_tls_pins_checked_ip_verifies_context_and_original_hostname(self):
        with FakeMQTT() as broker:
            port = broker.server.server_address[1]
            context = Mock()
            context.wrap_socket.side_effect = lambda sock, **_: sock
            with patch("dashboard.http_client.socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]) as resolve, patch("dashboard.mqtt_monitor.ssl.create_default_context", return_value=context):
                fetch_mqtt(settings(f"mqtts://broker.example:{port}"))
                self.assertEqual([call.args[0] for call in resolve.call_args_list], ["broker.example", "127.0.0.1"])
                self.assertEqual(context.wrap_socket.call_args.kwargs["server_hostname"], "broker.example")
            self.assertEqual(ssl.create_default_context().verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(ssl.create_default_context().check_hostname)


class MQTTCredentialsAndAPITests(unittest.TestCase):
    def test_vault_address_binding_private_permissions_and_http_entries_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = CredentialStore(directory)
            vault.put("homeassistant", "https://home.example", "fixture-token")
            vault.put("mqtt", "mqtts://broker.example", encode_credentials("user", "fixture-only-password"))
            self.assertTrue(vault.status("mqtt", "mqtts://broker.example:8883")["credentialMatches"])
            with self.assertRaises(CredentialError):
                vault.read_secret("mqtt", "mqtts://elsewhere.example:8883")
            self.assertEqual(vault.read_secret("homeassistant", "https://home.example"), "fixture-token")
            self.assertEqual(vault.path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("fixture-only-password", json.dumps(vault.status("mqtt")))

    def test_auth_csrf_closed_get_and_secret_never_exported_or_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            client = create_app({"TESTING": True, "STATE_DIR": directory, "SECRET_KEY": "fixture"}).test_client()
            self.assertEqual(client.get("/api/mqtt/state").status_code, 401)
            self.assertEqual(client.get("/api/mqtt/credential/status").status_code, 401)
            token = client.post("/api/auth/setup", json={"pin": "2468"}).json["csrfToken"]
            payload = {"brokerUrl": "mqtts://broker.example", "username": "user", "password": "fixture-only-password"}
            self.assertEqual(client.put("/api/mqtt/credential", json=payload).status_code, 403)
            headers = {"X-CSRF-Token": token}
            result = client.put("/api/mqtt/credential", json=payload, headers=headers)
            self.assertEqual(result.status_code, 200)
            for path in ["/api/mqtt/credential/status", "/api/config", "/api/config/export", "/api/catalog", "/api/mqtt/state"]:
                self.assertNotIn(b"fixture-only-password", client.get(path).data)
            self.assertEqual(client.get("/api/mqtt/state?topic=command").status_code, 400)
            self.assertEqual(client.post("/api/mqtt/state", json={"publish": "on"}, headers=headers).status_code, 405)
            self.assertEqual(client.get("/api/mqtt/credential").status_code, 405)
            self.assertEqual(client.delete("/api/mqtt/credential").status_code, 403)
            self.assertEqual(client.delete("/api/mqtt/credential", headers=headers).status_code, 200)

    def test_cache_uses_only_needed_provider_and_rejects_mismatched_vault(self):
        with FakeMQTT() as broker, tempfile.TemporaryDirectory() as directory:
            config = default_config()
            config["mqtt"] = settings(broker.url)
            hub = DataHub(state_override=directory)
            hub.metrics.get = Mock(side_effect=AssertionError("no CPU scan"))
            first = hub.get(config, "mqtt")["mqtt"]
            self.assertTrue(first["loading"])
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                result = hub.get(config, "mqtt")["mqtt"]
                if result.get("available"):
                    break
                time.sleep(0.01)
            self.assertEqual(result["received"], 2)
            count = len(broker.calls)
            hub.get(config, "mqtt")
            self.assertEqual(len(broker.calls), count)
            hub.credentials.put("mqtt", "mqtts://different.example", encode_credentials("user", "secret"))
            result = hub.get(config, "mqtt")["mqtt"]
            self.assertFalse(result["configured"])
            self.assertNotIn("sensors", result)
            self.assertIn("outro broker", result["error"])

    def test_mqtt_rendering_loaded_missing_loading_error_and_cache(self):
        config = default_config()
        next(page for page in config["pages"] if page["id"] == "mqtt")["enabled"] = True
        values = {"available": True, "sensors": [{**sensor, "value": "a" * 80, "retained": True} for sensor in settings()["sensors"]]}
        for data in [{"loading": True}, {"error": "Broker indisponível"}, values, {**values, "stale": True, "error": "timeout"}]:
            image = render_page("mqtt", {"mqtt": data}, config)
            self.assertEqual(image.size, (240, 240))
            self.assertGreater(len(set(image.get_flattened_data())), 10)


if __name__ == "__main__":
    unittest.main()
