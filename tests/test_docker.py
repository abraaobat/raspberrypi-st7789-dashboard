import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard.config import ConfigError, default_config, normalize_config, save_config
from dashboard.docker_monitor import (
    DockerError, MAX_CONTAINERS, MAX_DOCKER_BYTES, _get_json, docker_settings,
    fetch_docker, socket_path, summarize_containers,
)
from dashboard.providers import DataHub
from dashboard.rendering import CYAN, GRAY, GREEN, ORANGE, RED, docker_container_label, render_page
from tests.docker_fixture import FakeDocker, SAMPLE_CONTAINERS
from web_app import create_app


def wait_docker(hub, config):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        result = hub.get(config, "docker", 30)["docker"]
        if not result.get("loading"):
            return result
        time.sleep(0.01)
    raise AssertionError("Docker cache did not finish")


class DockerSettingsTests(unittest.TestCase):
    def test_migration_disabled_preserves_previous_choices_and_order(self):
        old = default_config()
        old.pop("docker")
        old["pages"] = [page for page in old["pages"] if page["id"] != "docker"]
        normalized = normalize_config(old)
        self.assertEqual(normalized["pages"][:-1], old["pages"])
        self.assertEqual(normalized["pages"][-1], {"id": "docker", "enabled": False, "refreshSeconds": 30})
        self.assertEqual(normalized["docker"], {"names": []})

    def test_closed_settings_deduplicate_exact_names(self):
        self.assertEqual(docker_settings({"names": ["pihole", " pihole ", "Pi-hole_2.0"]}), {"names": ["pihole", "Pi-hole_2.0"]})
        for invalid in [None, [], {"socket": "/tmp/other"}, {"url": "http://localhost"}, {"names": "pihole"},
                        {"names": ["/pihole"]}, {"names": ["foo;bar"]}, {"names": ["x\ny"]},
                        {"names": ["a" * 81]}, {"names": [True]}, {"names": ["a", "b", "c", "d", "e"]}]:
            with self.subTest(invalid=invalid), self.assertRaises(DockerError):
                docker_settings(invalid)
        with self.assertRaises(ConfigError):
            normalize_config({"docker": {"method": "POST"}})

    def test_refresh_floor_and_backup_round_trip(self):
        config = default_config()
        config["docker"] = {"names": ["pihole"]}
        page = next(page for page in config["pages"] if page["id"] == "docker")
        page["refreshSeconds"] = 1
        with self.assertRaises(ConfigError):
            normalize_config(config)
        page["refreshSeconds"] = 47
        with tempfile.TemporaryDirectory() as directory:
            saved = save_config(config, directory)
            self.assertEqual(normalize_config(json.loads(json.dumps(saved))), saved)
            self.assertNotIn("socket", saved["docker"])


class DockerSummaryTests(unittest.TestCase):
    def test_counts_prioritize_problems_and_discard_sensitive_fields(self):
        result = summarize_containers(SAMPLE_CONTAINERS, {})
        self.assertEqual((result["total"], result["running"], result["stopped"], result["unhealthy"], result["other"]), (5, 3, 1, 1, 1))
        self.assertEqual(result["containers"][0], {"name": "jellyfin", "state": "running", "health": "unhealthy"})
        self.assertEqual(result["hiddenCount"], 1)
        self.assertNotIn("not-exported", json.dumps(result))
        self.assertNotIn("9999", json.dumps(result))
        self.assertTrue(result["available"])

    def test_name_filters_are_exact_with_aliases_missing_and_case(self):
        payload = copy.deepcopy(SAMPLE_CONTAINERS)
        payload[0]["Names"].append("/ha-alias")
        result = summarize_containers(payload, {"names": ["ha-alias", "pihole", "HOMEASSISTANT", "hole"]})
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["missingNames"], ["HOMEASSISTANT", "hole"])
        self.assertEqual({item["name"] for item in result["containers"]}, {"ha-alias", "pihole"})
        self.assertEqual(result["scope"], "selected")

    def test_zero_is_real_only_for_valid_empty_list(self):
        result = summarize_containers([], {})
        self.assertEqual(result["running"], 0)
        self.assertTrue(result["available"])
        self.assertEqual(result["missingNames"], [])
        for invalid in [{}, [None], [{"Names": []}], [{"Names": ["/bad\nname"]}], SAMPLE_CONTAINERS * (MAX_CONTAINERS + 1)]:
            with self.subTest(invalid=str(invalid)[:70]), self.assertRaises(DockerError):
                summarize_containers(invalid, {})

    def test_unknown_or_absent_health_never_claims_healthy(self):
        for state, status, expected in [("running", "Up 1h", "none"), ("running", "Up 1h (unhealthy)", "unhealthy"),
                                        ("running", "Up (health: starting)", "starting"), ("exited", "was (healthy)", "none")]:
            result = summarize_containers([{"Names": ["/demo"], "State": state, "Status": status}], {})
            self.assertEqual(result["containers"][0]["health"], expected)
        for state in [{}, None, "mystery"]:
            result = summarize_containers([{"Names": ["/demo"], "State": state}], {})
            self.assertEqual(result["containers"][0]["state"], "unknown")
            self.assertEqual(result["other"], 1)

    def test_all_states_and_long_names_render_in_shared_canvas(self):
        config = default_config()
        next(page for page in config["pages"] if page["id"] == "docker")["enabled"] = True
        states = [("running", "healthy", GREEN), ("running", "unhealthy", RED), ("running", "none", CYAN),
                  ("running", "starting", ORANGE), ("paused", "none", ORANGE), ("unknown", "none", GRAY),
                  ("dead", "none", RED), ("exited", "none", GRAY), ("restarting", "none", ORANGE)]
        for state, health, color in states:
            item = {"name": "long-container-name-" * 5, "state": state, "health": health}
            self.assertEqual(docker_container_label(item)[1], color)
            values = {**summarize_containers([], {}), "containers": [item] * 4}
            image = render_page("docker", {"docker": values}, config)
            self.assertEqual(image.size, (240, 240))
            self.assertEqual(image.getpixel((15, 124)), color)
        for values in [{"loading": True}, {"error": "Sem permissão para consultar o socket Docker"},
                       {**summarize_containers([], {}), "stale": True}, summarize_containers([], {"names": ["missing"]})]:
            self.assertEqual(render_page("docker", {"docker": values}, config).mode, "RGB")


class DockerTransportTests(unittest.TestCase):
    def test_unix_only_two_fixed_gets_and_no_environment_proxy_or_tcp(self):
        with FakeDocker() as engine, patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": engine.path,
                                                           "DOCKER_HOST": "tcp://evil.example:2375", "HTTP_PROXY": "http://evil.example"}), \
                patch("socket.getaddrinfo", side_effect=AssertionError("DNS not allowed")), \
                patch("subprocess.run", side_effect=AssertionError("commands not allowed")):
            self.assertEqual(fetch_docker({})["total"], 5)
            self.assertEqual(engine.calls, [{"method": "GET", "path": "/version"}, {"method": "GET", "path": "/v1.47/containers/json?all=1"}])

    def test_missing_regular_file_relative_and_permission_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-a-socket"
            with patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": str(path)}), self.assertRaisesRegex(DockerError, "não encontrado"):
                socket_path()
            path.touch()
            with patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": str(path)}), self.assertRaisesRegex(DockerError, "socket Unix"):
                socket_path()
            with patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": "relative.sock"}), self.assertRaisesRegex(DockerError, "inválido"):
                socket_path()
        with patch("dashboard.docker_monitor.os.stat", side_effect=PermissionError), self.assertRaisesRegex(DockerError, "Sem permissão"):
            socket_path()

    def test_invalid_api_version_cannot_inject_endpoint(self):
        with FakeDocker() as engine, patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": engine.path}):
            for api in ["1.47/containers/create", "1.47\r\nHeader: bad", None, 1.47, "1.1234"]:
                engine.responses["/version"] = (200, {"ApiVersion": api})
                with self.assertRaisesRegex(DockerError, "versão de API inválida"):
                    fetch_docker({})
            self.assertTrue(all(call["path"] == "/version" for call in engine.calls))
            with self.assertRaisesRegex(DockerError, "não permitida"):
                _get_json(engine.path, "/containers/create", time.monotonic() + 1)

    def test_daemon_errors_redirects_and_invalid_json_are_not_echoed(self):
        with FakeDocker() as engine, patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": engine.path}):
            for status, body in [(302, {"secret": "do-not-echo"}), (500, {"message": "do-not-echo"}),
                                 (403, {}), (200, b"do-not-echo"), (200, b"[" * 1500)]:
                engine.responses["/version"] = (status, body)
                with self.assertRaises(DockerError) as error:
                    fetch_docker({})
                self.assertNotIn("do-not-echo", str(error.exception))

    def test_oversized_declared_response_is_rejected(self):
        with FakeDocker() as engine, patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": engine.path}):
            engine.responses["/version"] = (200, b"x" * (MAX_DOCKER_BYTES + 1))
            with self.assertRaisesRegex(DockerError, "256 KiB"):
                fetch_docker({})

    def test_watchdog_bounds_slow_headers_not_just_each_read(self):
        with FakeDocker() as engine:
            engine.slow_headers = True
            started = time.monotonic()
            with self.assertRaises(DockerError):
                _get_json(engine.path, "/version", started + 0.15)
            self.assertLess(time.monotonic() - started, 0.8)

    def test_oversized_stream_without_length_is_also_bounded(self):
        with FakeDocker() as engine, patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": engine.path}):
            engine.content_length = None
            engine.responses["/version"] = (200, b"x" * (MAX_DOCKER_BYTES + 1))
            with self.assertRaisesRegex(DockerError, "256 KiB"):
                fetch_docker({})

    def test_incomplete_or_bad_declared_length_is_rejected(self):
        with FakeDocker() as engine, patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": engine.path}):
            engine.content_length = "1024"
            with self.assertRaisesRegex(DockerError, "incompleta"):
                fetch_docker({})
            engine.content_length = "9" * 5000
            with self.assertRaisesRegex(DockerError, "256 KiB"):
                fetch_docker({})

    def test_async_cache_no_metrics_scan_filtered_signature_and_stale_failure(self):
        with tempfile.TemporaryDirectory() as directory, FakeDocker() as engine, \
                patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": engine.path}):
            hub = DataHub(state_override=directory)
            config = default_config()
            with patch.object(hub.metrics, "get", side_effect=AssertionError("Docker must not scan CPU/network")):
                result = wait_docker(hub, config)
                self.assertEqual(result["running"], 3)
                self.assertFalse(result["stale"])
                wait_docker(hub, config)
                self.assertEqual(len(engine.calls), 2)
                config["docker"]["names"] = ["pihole"]
                self.assertEqual(wait_docker(hub, config)["total"], 1)
                self.assertEqual(len(engine.calls), 4)
                engine.responses["/version"] = (500, {})
                with hub.external._lock:
                    hub.external._items["docker"]["loadedAt"] = time.monotonic() - 100
                result = wait_docker(hub, config)
                deadline = time.monotonic() + 2
                while not result.get("error") and time.monotonic() < deadline:
                    time.sleep(0.01)
                    result = wait_docker(hub, config)
                self.assertTrue(result["available"])
                self.assertTrue(result["stale"])
                self.assertEqual(result["total"], 1)
                self.assertTrue(result["error"])
                calls = len(engine.calls)
                wait_docker(hub, config)
                self.assertEqual(len(engine.calls), calls, "failure backoff must prevent repeated queries")


class DockerAPITests(unittest.TestCase):
    def test_authenticated_get_only_no_paths_no_config_or_auth_mutation(self):
        with tempfile.TemporaryDirectory() as directory, FakeDocker() as engine, \
                patch.dict(os.environ, {"ST7789_DOCKER_SOCKET": engine.path}):
            client = create_app({"STATE_DIR": directory, "TESTING": True}).test_client()
            self.assertEqual(client.get("/api/docker/state").status_code, 401)
            self.assertEqual(engine.calls, [])
            client.post("/api/auth/setup", json={"pin": "2468"})
            client.get("/api/config")
            before = {path.name: path.read_bytes() for path in Path(directory).iterdir() if path.is_file()}
            self.assertEqual(client.get("/api/docker/state?socket=/tmp/private").status_code, 400)
            for method in ["post", "put", "delete", "patch"]:
                self.assertEqual(getattr(client, method)("/api/docker/state", json={"command": "restart"}).status_code, 405)
            self.assertEqual(engine.calls, [])
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                result = client.get("/api/docker/state").get_json()
                if result.get("available"):
                    break
                time.sleep(0.01)
            self.assertTrue(result["available"])
            self.assertNotIn("not-exported", json.dumps(result))
            self.assertEqual(client.get("/api/preview?page=docker").status_code, 200)
            after = {path.name: path.read_bytes() for path in Path(directory).iterdir() if path.is_file()}
            self.assertEqual(before, after)
            self.assertFalse(next(page for page in client.get("/api/config").get_json()["pages"] if page["id"] == "docker")["enabled"])
