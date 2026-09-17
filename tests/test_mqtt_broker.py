"""Interoperability against a real, isolated Mosquitto, when its CLI is installed.

The CI runner installs these tools. The dashboard installer never does.
All files/accounts/topics/ports below are temporary and fictitious.
"""

import getpass
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path

from dashboard.mqtt_monitor import fetch_mqtt
from dashboard.mqtt_settings import MQTTError, encode_credentials

TOOLS_AVAILABLE = all(shutil.which(name) for name in ["mosquitto", "mosquitto_pub", "mosquitto_passwd", "openssl"])


@contextmanager
def broker(extra="", prepare=None):
    with tempfile.TemporaryDirectory(prefix="st7789-mosquitto-test-") as directory:
        folder = Path(directory)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        if prepare:
            extra = prepare(folder)
        # Explicit current user avoids privilege dropping/changing private fixture permissions on root CI runs.
        config = folder / "mosquitto.conf"
        config.write_text(f"user {getpass.getuser()}\nlistener {port} 127.0.0.1\npersistence false\n" + extra)
        process = subprocess.Popen(["mosquitto", "-c", str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError("isolated test broker did not start")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise AssertionError("isolated test broker not ready")
            yield port
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()  # This helper owns only this temporary child, never a system/user broker.
                process.wait(timeout=3)


def source(port, tls=False):
    return {"brokerUrl": f"{'mqtts' if tls else 'mqtt'}://127.0.0.1:{port}", "allowInsecureMqtt": not tls,
            "sensors": [{"label": "Temperature", "topic": "fixture/temperature", "format": "text", "valuePath": "", "unit": "°C"},
                        {"label": "Energy", "topic": "fixture/energy", "format": "json", "valuePath": "power", "unit": "W"}]}


def publish(port, topic, payload, credentials=None):
    command = ["mosquitto_pub", "-h", "127.0.0.1", "-p", str(port), "-V", "mqttv311", "-q", "1", "-r", "-t", topic, "-m", payload]
    if credentials:
        command.extend(["-u", credentials[0], "-P", credentials[1]])
    subprocess.run(command, check=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@unittest.skipUnless(TOOLS_AVAILABLE, "isolated Mosquitto CLI not installed; exercised in CI, not required on the Pi")
class RealMQTTBrokerTests(unittest.TestCase):
    def test_mosquitto_retained_text_json_and_qos_downgrade(self):
        with broker("allow_anonymous true\n") as port:
            publish(port, "fixture/temperature", "28.5")
            publish(port, "fixture/energy", '{"power":123.4}')
            result = fetch_mqtt(source(port))
            self.assertEqual([s["value"] for s in result["sensors"]], ["28.5", "123.4"])
            self.assertTrue(all(s["retained"] for s in result["sensors"]))
            self.assertEqual(result["missingTopics"], [])

    def test_mosquitto_private_login_read_only_acl_and_wrong_password(self):
        def prepare(folder):
            password = folder / "passwords"
            subprocess.run(["mosquitto_passwd", "-b", "-c", str(password), "reader", "fixture-read-secret"], check=True, timeout=5)
            subprocess.run(["mosquitto_passwd", "-b", str(password), "writer", "fixture-write-secret"], check=True, timeout=5)
            acl = folder / "acl"
            acl.write_text("user reader\ntopic read fixture/temperature\ntopic read fixture/energy\nuser writer\ntopic write fixture/#\n")
            return f"allow_anonymous false\npassword_file {password}\nacl_file {acl}\n"
        with broker(prepare=prepare) as port:
            publish(port, "fixture/temperature", "0", ("writer", "fixture-write-secret"))
            publish(port, "fixture/energy", '{"power":0}', ("writer", "fixture-write-secret"))
            result = fetch_mqtt(source(port), encode_credentials("reader", "fixture-read-secret"))
            self.assertEqual([s["value"] for s in result["sensors"]], ["0", "0"])
            with self.assertRaisesRegex(MQTTError, "recusada"):
                fetch_mqtt(source(port), encode_credentials("reader", "fixture-wrong-secret"))

    def test_mosquitto_untrusted_tls_certificate_is_not_bypassed(self):
        def prepare(folder):
            key, cert = folder / "key.pem", folder / "cert.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-subj", "/CN=localhost", "-keyout", str(key), "-out", str(cert)], check=True, timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"allow_anonymous true\ncertfile {cert}\nkeyfile {key}\n"
        with broker(prepare=prepare) as port:
            with self.assertRaisesRegex(MQTTError, "certificado"):
                fetch_mqtt(source(port, tls=True), encode_credentials("reader", "fixture-secret"))
