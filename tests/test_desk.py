import io
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from dashboard.config import ConfigError, default_config, normalize_config, save_config
from dashboard.desk import DeskError, PomodoroStore, clock_snapshot, system_boot_id
from dashboard.desk_settings import clock_settings, pomodoro_settings
from dashboard.providers import DataHub
from dashboard.rendering import render_page
from dashboard.runtime import RuntimeStore
from web_app import create_app


class DeskSettingsTests(unittest.TestCase):
    def test_old_configuration_keeps_order_and_adds_disabled_desk_pages(self):
        old = default_config()
        old.pop("clock")
        old.pop("pomodoro")
        old["pages"] = [old["pages"][1], old["pages"][0], old["pages"][2]]
        config = normalize_config(old)
        self.assertEqual([p["id"] for p in config["pages"][:3]], ["network", "status", "hardware"])
        self.assertFalse(any(p["enabled"] for p in config["pages"] if p["id"] in {"clock", "pomodoro"}))
        self.assertEqual(config["pomodoro"], {"minutes": 25})
        self.assertEqual(config["clock"], {"timezone": "", "showSeconds": True, "hour24": True})

    def test_clock_settings_are_closed_and_validate_timezone(self):
        self.assertEqual(clock_settings({"timezone": " America/Boa_Vista "})["timezone"], "America/Boa_Vista")
        for payload in [None, [], {"timezone": "../../etc/passwd"}, {"timezone": "not/a-zone"},
                        {"timezone": 123}, {"showSeconds": 1}, {"hour24": "false"}, {"command": "date"}]:
            with self.subTest(payload=payload), self.assertRaises(DeskError):
                clock_settings(payload)

    def test_pomodoro_duration_requires_integer_in_range(self):
        for value in [0, 121, True, 25.5, "25", None]:
            with self.subTest(value=value), self.assertRaises(DeskError):
                pomodoro_settings({"minutes": value})
        for payload in [{"minutes": 25, "action": "start"}, [], None]:
            with self.assertRaises(DeskError):
                pomodoro_settings(payload)
        for minutes in [1, 25, 120]:
            self.assertEqual(pomodoro_settings({"minutes": minutes})["minutes"], minutes)

    def test_invalid_desk_settings_reject_entire_config(self):
        for key, payload in [("clock", {"hour24": 0}), ("pomodoro", {"minutes": 0})]:
            config = default_config()
            config[key] = payload
            with self.assertRaises(ConfigError):
                normalize_config(config)

    def test_time_pages_keep_one_second_refresh(self):
        for page_id in ["clock", "pomodoro"]:
            config = default_config()
            page = next(p for p in config["pages"] if p["id"] == page_id)
            self.assertEqual(page["refreshSeconds"], 1)
            page["refreshSeconds"] = 10
            with self.assertRaises(ConfigError):
                normalize_config(config)

    def test_clock_formats_convert_timezone_date_and_weekday(self):
        now = datetime(2026, 9, 16, 2, 3, 4, tzinfo=timezone.utc)
        result = clock_snapshot(clock_settings({"timezone": "America/Boa_Vista"}), now=now)
        self.assertEqual(result["time"], "22:03:04")
        self.assertEqual(result["date"], "15/09/2026")
        self.assertEqual(result["weekday"], "TERÇA")
        result = clock_snapshot(clock_settings({"timezone": "UTC", "hour24": False, "showSeconds": False}), now=now)
        self.assertEqual(result["time"], "02:03")
        self.assertEqual(result["period"], "AM")
        self.assertEqual(result["date"], "16/09/2026")

    def test_default_clock_uses_system_timezone_without_network(self):
        now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
        result = clock_snapshot(clock_settings({}), now=now)
        self.assertEqual(result["timezone"], "UTC")
        self.assertEqual(result["time"], "12:00:00")


class PomodoroTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.clock = 100.0
        self.store = PomodoroStore(self.temporary.name, monotonic=lambda: self.clock, boot_id="test-boot-1")

    def tearDown(self):
        self.temporary.cleanup()

    def test_start_pause_resume_complete_and_reset(self):
        self.assertEqual(self.store.snapshot(1)["status"], "idle")
        self.assertEqual(self.store.command("start", 1)["remainingSeconds"], 60)
        self.clock += 10.2
        paused = self.store.command("pause", 1)
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(paused["remainingSeconds"], 50)
        self.clock += 500
        self.assertEqual(self.store.snapshot(1), paused)
        resumed = self.store.command("resume", 1)
        self.assertEqual(resumed["status"], "running")
        self.clock += 50
        completed = self.store.snapshot(1)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["remainingSeconds"], 0)
        self.assertEqual(completed["progress"], 1)
        self.assertEqual(self.store.command("start", 2)["totalSeconds"], 120)
        self.assertEqual(self.store.command("reset", 3)["remainingSeconds"], 180)

    def test_new_duration_only_applies_to_next_cycle(self):
        self.store.command("start", 25)
        self.clock += 5
        self.assertEqual(self.store.snapshot(1)["totalSeconds"], 1500)
        self.store.command("pause", 1)
        self.assertEqual(self.store.command("resume", 1)["totalSeconds"], 1500)
        self.assertEqual(self.store.command("reset", 1)["totalSeconds"], 60)

    def test_invalid_actions_and_transitions_preserve_state(self):
        for action in [None, [], "shell", "pause", "resume"]:
            with self.subTest(action=action), self.assertRaises(DeskError):
                self.store.command(action, 1)
        self.store.command("start", 1)
        original = self.store.path.read_bytes()
        with self.assertRaises(DeskError):
            self.store.command("start", 1)
        self.assertEqual(self.store.path.read_bytes(), original)

    def test_elapsed_cycle_cannot_be_paused(self):
        self.store.command("start", 1)
        self.clock += 61
        with self.assertRaises(DeskError):
            self.store.command("pause", 1)

    def test_other_process_reads_same_monotonic_deadline(self):
        self.store.command("start", 1)
        code = ("import json, sys; from dashboard.desk import PomodoroStore; "
                "print(json.dumps(PomodoroStore(sys.argv[1], monotonic=lambda: 110, boot_id='test-boot-1').snapshot(1)))")
        result = subprocess.run([sys.executable, "-c", code, self.temporary.name],
                                capture_output=True, text=True, check=True, timeout=5)
        self.assertEqual(json.loads(result.stdout)["remainingSeconds"], 50)

    def test_restarting_process_preserves_running_timer(self):
        self.store.command("start", 1)
        self.clock += 20
        other = PomodoroStore(self.temporary.name, monotonic=lambda: self.clock, boot_id="test-boot-1")
        self.assertEqual(other.snapshot(1)["remainingSeconds"], 40)

    def test_reboot_interrupts_running_cycle_and_requires_explicit_start(self):
        self.store.command("start", 1)
        other = PomodoroStore(self.temporary.name, monotonic=lambda: 5, boot_id="test-boot-2")
        view = other.snapshot(1)
        self.assertEqual(view["status"], "interrupted")
        self.assertIsNone(view["remainingSeconds"])
        with self.assertRaises(DeskError):
            other.command("resume", 1)
        self.assertEqual(other.command("start", 1)["remainingSeconds"], 60)

    def test_paused_cycle_survives_reboot_with_explicit_resume(self):
        self.store.command("start", 1)
        self.clock += 20
        self.store.command("pause", 1)
        other = PomodoroStore(self.temporary.name, monotonic=lambda: 5, boot_id="test-boot-2")
        self.assertEqual(other.snapshot(1)["remainingSeconds"], 40)
        self.assertEqual(other.command("resume", 1)["status"], "running")

    def test_missing_boot_identity_fails_closed(self):
        with patch("dashboard.desk.system_boot_id", return_value=None):
            other = PomodoroStore(self.temporary.name)
        with self.assertRaises(DeskError):
            other.command("start", 1)
        self.assertEqual(other.snapshot(1)["status"], "idle")

    def test_mac_boot_identity_uses_uuid_not_adjustable_wall_time(self):
        identifier = "72DEE20C-90E9-41A5-A7C8-D8A43D807498"
        system_boot_id.cache_clear()
        try:
            with patch("dashboard.desk.platform.system", return_value="Darwin"), \
                    patch("dashboard.desk.subprocess.run", return_value=Mock(returncode=0, stdout=identifier)) as run:
                self.assertEqual(system_boot_id(), "darwin-" + identifier.lower())
                self.assertEqual(run.call_args.args[0][-1], "kern.bootsessionuuid")
                system_boot_id.cache_clear()
                run.return_value.stdout = "invalid"
                self.assertIsNone(system_boot_id())
        finally:
            system_boot_id.cache_clear()

    def test_wall_clock_changes_do_not_affect_countdown(self):
        self.store.command("start", 1)
        self.clock += 10
        with patch("time.time", return_value=10**12):
            self.assertEqual(self.store.snapshot(1)["remainingSeconds"], 50)

    def test_private_permissions_public_view_and_no_temp_files(self):
        result = self.store.command("start", 1)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.lock_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.directory.stat().st_mode & 0o777, 0o700)
        self.assertNotIn("bootId", result)
        self.assertNotIn("deadline", result)
        self.assertFalse(list(self.store.directory.glob(".pomodoro-*.tmp")))

    def test_corrupt_or_public_file_is_not_overwritten(self):
        self.store.command("start", 1)
        for body in ["broken", "[]", '{"schemaVersion":1,"status":[]}']:
            self.store.path.write_text(body)
            with self.assertRaises(DeskError):
                self.store.command("reset", 1)
            self.assertEqual(self.store.path.read_text(), body)
        self.store.path.chmod(0o644)
        with self.assertRaises(DeskError):
            self.store.snapshot(1)

    def test_symlinked_state_or_lock_is_not_followed(self):
        target = Path(self.temporary.name) / "target"
        target.write_text("preserve")
        self.store.path.symlink_to(target)
        with self.assertRaises(DeskError):
            self.store.command("reset", 1)
        self.assertEqual(target.read_text(), "preserve")
        self.store.path.unlink()
        self.store.lock_path.unlink()
        self.store.lock_path.symlink_to(target)
        with self.assertRaises(DeskError):
            self.store.command("start", 1)
        self.assertEqual(target.read_text(), "preserve")

    def test_concurrent_starts_accept_exactly_one(self):
        def start(_):
            try:
                return PomodoroStore(self.temporary.name, monotonic=lambda: 100, boot_id="test-boot-1").command("start", 1)["status"]
            except DeskError:
                return "denied"
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(start, range(8)))
        self.assertEqual(results.count("running"), 1)
        self.assertEqual(results.count("denied"), 7)


class DeskWebTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        with patch("dashboard.desk.system_boot_id", return_value="web-test-boot"):
            self.app = create_app({"TESTING": True, "STATE_DIR": self.temporary.name, "SECRET_KEY": "desk-test-only"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temporary.cleanup()

    def auth(self):
        token = self.client.post("/api/auth/setup", json={"pin": "2468"}).get_json()["csrfToken"]
        return {"X-CSRF-Token": token}

    def test_state_and_commands_require_auth_and_csrf(self):
        self.assertEqual(self.client.get("/api/pomodoro/state").status_code, 401)
        self.assertEqual(self.client.post("/api/pomodoro/command", json={"action": "start"}).status_code, 401)
        self.auth()
        self.assertEqual(self.client.get("/api/pomodoro/state").status_code, 200)
        self.assertEqual(self.client.post("/api/pomodoro/command", json={"action": "start"}).status_code, 403)

    def test_commands_accept_only_action_and_applied_duration(self):
        headers = self.auth()
        for payload in [None, [], {}, {"action": "start", "minutes": 1}, {"action": ["start"]}, {"action": "shell"}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/pomodoro/command", json=payload, headers=headers).status_code, 400)
        config = default_config()
        config["pomodoro"]["minutes"] = 1
        save_config(config, self.temporary.name)
        result = self.client.post("/api/pomodoro/command", json={"action": "start"}, headers=headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()["totalSeconds"], 60)
        self.assertEqual(self.client.post("/api/pomodoro/command", json={"action": "start"}, headers=headers).status_code, 400)

    def test_timer_commands_do_not_change_page_activation_or_navigation(self):
        headers = self.auth()
        before = self.client.get("/api/config").get_json()
        runtime = RuntimeStore(self.temporary.name).read_control()
        self.client.post("/api/pomodoro/command", json={"action": "start"}, headers=headers)
        self.assertEqual(self.client.get("/api/config").get_json(), before)
        self.assertEqual(RuntimeStore(self.temporary.name).read_control(), runtime)

    def test_backup_contains_settings_not_timer_runtime_and_import_preserves_cycle(self):
        headers = self.auth()
        self.client.post("/api/pomodoro/command", json={"action": "start"}, headers=headers)
        backup = self.client.get("/api/config/export").get_json()
        self.assertIn("clock", backup)
        self.assertIn("pomodoro", backup)
        self.assertNotIn("deadline", json.dumps(backup))
        self.assertNotIn("bootId", json.dumps(backup))
        backup["pomodoro"]["minutes"] = 1
        result = self.client.post("/api/config/import", json=backup, headers=headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get("/api/pomodoro/state").get_json()["totalSeconds"], 1500)

    def test_desk_previews_are_png_and_corrupt_timer_error_is_safe(self):
        self.auth()
        for page_id in ["clock", "pomodoro"]:
            result = self.client.get("/api/preview?page=" + page_id)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(Image.open(io.BytesIO(result.data)).size, (240, 240))
        path = Path(self.temporary.name) / "pomodoro.json"
        path.write_text("broken")
        path.chmod(0o600)
        self.assertEqual(self.client.get("/api/pomodoro/state").status_code, 400)
        self.assertEqual(self.client.get("/api/preview?page=pomodoro").status_code, 200)
        self.assertEqual(path.read_text(), "broken")

    def test_desk_providers_skip_system_scan_and_network(self):
        metrics = Mock()
        hub = DataHub(metrics=metrics, state_override=self.temporary.name)
        hub.external = Mock()
        config = default_config()
        self.assertIn("clock", hub.get(config, "clock"))
        self.assertIn("pomodoro", hub.get(config, "pomodoro"))
        metrics.get.assert_not_called()
        hub.external.get.assert_not_called()

    def test_all_timer_states_and_long_clock_strings_render(self):
        config = default_config()
        for page in config["pages"]:
            page["enabled"] = page["id"] in {"clock", "pomodoro"}
        for status in ["idle", "running", "paused", "completed", "interrupted"]:
            snapshot = {"pomodoro": {"status": status, "remainingSeconds": None if status == "interrupted" else 7200, "progress": .5}}
            self.assertEqual(render_page("pomodoro", snapshot, config).size, (240, 240))
        for page_id in ["clock", "pomodoro"]:
            self.assertEqual(render_page(page_id, {}, config).size, (240, 240))
        result = render_page("clock", {"clock": {"time": "12:34:56", "date": "16/09/2026", "weekday": "QUARTA",
                                                  "period": "PM", "timezone": "America/Argentina/Buenos_Aires"}}, config)
        self.assertEqual(result.size, (240, 240))


if __name__ == "__main__":
    unittest.main()
