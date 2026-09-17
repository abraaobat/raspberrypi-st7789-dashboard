"""No sudo/systemctl/hardware changes. All service transitions use an in-memory double."""
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from dashboard import update_manager as updates
from dashboard.config import default_config

ROOT = Path(__file__).resolve().parents[1]


class FakeServices:
    def __init__(self, units):
        self.units = dict(units)
        self.calls = []
        self.health = [True] * 20
        self.fail_install = False

    def read_units(self):
        return dict(self.units)

    def authorize(self):
        self.calls.append("authorize")

    def stop(self):
        self.calls.append("stop")

    def install(self, files):
        self.calls.append(files.name)
        if self.fail_install and files.name == "after":
            self.units[updates.UNITS[0]] = (files / updates.UNITS[0]).read_text()
            raise updates.UpdateError("simulated partial install")
        self.units = {name: (files / name).read_text() for name in updates.UNITS}

    def start(self):
        self.calls.append("start")

    def healthy(self, expected, state, since):
        self.calls.append("health:" + expected)
        return self.health.pop(0)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="st7789-update-tests-")
        self.home = Path(self.temporary.name)
        self.home.chmod(0o700)
        self.repository = self.home / "repo"
        (self.repository / "systemd").mkdir(parents=True)
        (self.repository / "dashboard").mkdir()
        (self.repository / "dashboard/__init__.py").write_text('__version__ = "0.6.0"\n')
        self.templates = {name: (ROOT / "systemd" / name).read_text() for name in updates.UNITS}
        for name, text in self.templates.items():
            (self.repository / "systemd" / name).write_text(text)
        self.environment = self.home / "old-env"
        (self.environment / "bin").mkdir(parents=True)
        for name in ("python", "waitress-serve"):
            (self.environment / "bin" / name).write_text("old-environment-untouched")
        self.state = self.home / ".config/raspberrypi-st7789-dashboard"
        self.state.mkdir(parents=True, mode=0o700)
        self.private = {"config.json": json.dumps(default_config()).encode(),
                        "auth.json": b"private-fixture-pin", "session-secret.bin": b"fake-session-only"}
        for name, data in self.private.items():
            updates.private_write(self.state / name, data)
        units = updates.render_units(self.repository, self.environment, "pi", self.state, self.templates)
        self.services = FakeServices(units)
        self.manager = updates.UpdateManager(self.repository, self.home, "pi", self.services)
        self.compatibility = patch.object(updates, "compatible")
        self.compatibility.start()
        self.addCleanup(self.compatibility.stop)
        self.addCleanup(self.temporary.cleanup)

    def release(self):
        with self.manager.locked():
            name = "release-" + "a" * 12 + "-" + "b" * 8
            release = self.manager.root / name
            release.mkdir(mode=0o700)
            candidate = release / "code"
            (candidate / "dashboard").mkdir(parents=True)
            (candidate / "dashboard/__init__.py").write_text('__version__ = "0.10.0"\n')
            environment = release / "venv"
            (environment / "bin").mkdir(parents=True)
            for file in ("python", "waitress-serve"):
                (environment / "bin" / file).write_text("new-environment")
            previous, before = self.manager.active()
            target = {"code": str(candidate), "environment": str(environment), "version": "0.10.0",
                      "fingerprint": updates.fingerprint(candidate)}
            after = updates.render_units(candidate, environment, "pi", self.state, self.templates)
            for folder, contents in (("before", before), ("after", after)):
                (release / folder).mkdir(mode=0o700)
                for unit, text in contents.items():
                    updates.private_write(release / folder / unit, text.encode())
            updates.private_write(release / "packages.txt", b"packages-fixture")
            manifest = {"schemaVersion": 1, "id": name, "home": str(self.home), "phase": "prepared",
                        "previous": previous, "candidate": target}
            self.manager.save(release, manifest)
            return name, release, manifest

    def assert_private_unchanged(self):
        for name, data in self.private.items():
            self.assertEqual((self.state / name).read_bytes(), data)
        self.assertEqual((self.environment / "bin/python").read_text(), "old-environment-untouched")

    def activate(self, name):
        with patch.object(updates, "run", return_value=b"packages-fixture"):
            return self.manager.activate(name)

    def test_preflight_is_read_only_and_does_not_request_sudo(self):
        previous, _ = self.manager.preflight()
        self.assertEqual(previous["version"], "0.6.0")
        self.assertEqual(self.services.calls, ["health:0.6.0"])
        self.assertFalse(self.manager.root.exists())
        self.assert_private_unchanged()

    def test_custom_units_are_rejected_before_operations(self):
        self.services.units[updates.UNITS[0]] += "Environment=EXTRA=1\n"
        with self.assertRaises(updates.UpdateError):
            self.manager.preflight()
        self.assertEqual(self.services.calls, [])

    def test_preflight_unhealthy_refuses_update(self):
        self.services.health = [False]
        with self.assertRaises(updates.UpdateError):
            self.manager.preflight()
        self.assertNotIn("authorize", self.services.calls)

    def test_activate_preserves_private_state_and_old_environment(self):
        name, release, _ = self.release()
        self.assertEqual(self.activate(name), "active")
        self.assertEqual(self.manager.read(name)["phase"], "active")
        self.assertEqual(self.services.calls, ["health:0.6.0", "authorize", "stop", "after", "start", "health:0.10.0"])
        self.assertTrue((release / "backup-activation/auth.json").exists())
        self.assert_private_unchanged()

    def test_health_failure_returns_previous_units_without_restoring_state(self):
        name, _, manifest = self.release()
        self.services.health = [True, False, True]
        with self.assertRaisesRegex(updates.UpdateError, "versão anterior restaurada"):
            self.activate(name)
        self.assertEqual(self.manager.read(name)["phase"], "rolled-back")
        self.assertEqual(self.manager.active()[0], manifest["previous"])
        self.assert_private_unchanged()

    def test_partial_install_failure_restores_both_units(self):
        name, release, manifest = self.release()
        self.services.fail_install = True
        with self.assertRaisesRegex(updates.UpdateError, "versão anterior restaurada"):
            self.activate(name)
        self.assertEqual(self.manager.active()[0], manifest["previous"])
        self.assert_private_unchanged()
        with patch.object(updates, "run", return_value=b"") as external:
            updates.SystemServices().install(release / "after")
            arguments = [call.args[0] for call in external.call_args_list]
            self.assertEqual(len(arguments), 5)
            for index, unit in ((0, updates.UNITS[0]), (2, updates.UNITS[1])):
                temporary = "/etc/systemd/system/." + unit + ".st7789-next"
                self.assertEqual(arguments[index][-1], temporary)
                self.assertEqual(arguments[index + 1], ["sudo", "-n", "mv", "-T", "--", temporary, "/etc/systemd/system/" + unit])
            self.assertEqual(arguments[-1], ["sudo", "-n", "systemctl", "daemon-reload"])

    def test_recovery_failure_keeps_durable_pending_journal(self):
        name, _, _ = self.release()
        self.services.health = [True, False, False]
        with self.assertRaisesRegex(updates.UpdateError, "Recuperação pendente"):
            self.activate(name)
        self.assertEqual(self.manager.read(name)["phase"], "recovery-required")
        with self.manager.locked(), self.assertRaises(updates.UpdateError):
            self.manager.pending()
        self.assert_private_unchanged()

    def test_sudo_denial_happens_before_journal_or_stop(self):
        name, _, _ = self.release()
        with patch.object(self.services, "authorize", side_effect=updates.UpdateError("denied")):
            with self.assertRaises(updates.UpdateError):
                self.activate(name)
        self.assertEqual(self.manager.read(name)["phase"], "prepared")
        self.assertNotIn("stop", self.services.calls)

    def test_changed_candidate_code_refuses_before_sudo(self):
        name, release, _ = self.release()
        (release / "code/new-file").write_text("tampered")
        with self.assertRaises(updates.UpdateError):
            self.activate(name)
        self.assertNotIn("authorize", self.services.calls)

    def test_changed_package_inventory_refuses_before_sudo(self):
        name, _, _ = self.release()
        with patch.object(updates, "run", return_value=b"changed-packages"), self.assertRaises(updates.UpdateError):
            self.manager.activate(name)
        self.assertNotIn("authorize", self.services.calls)

    def test_changed_service_file_refuses_before_sudo(self):
        name, release, _ = self.release()
        updates.private_write(release / "after" / updates.UNITS[0], b"ExecStart=arbitrary\n")
        with self.assertRaises(updates.UpdateError):
            self.activate(name)
        self.assertNotIn("authorize", self.services.calls)

    def test_changed_active_code_refuses_stale_preparation(self):
        name, _, _ = self.release()
        (self.repository / "new-file").write_text("different")
        with self.assertRaises(updates.UpdateError):
            self.activate(name)
        self.assertNotIn("authorize", self.services.calls)

    def test_manual_rollback_preserves_new_private_values(self):
        name, _, manifest = self.release()
        self.activate(name)
        updates.private_write(self.state / "credentials.json", b"new-private-state")
        self.assertEqual(self.manager.rollback(name), "rolled-back")
        self.assertEqual((self.state / "credentials.json").read_bytes(), b"new-private-state")
        self.assertEqual(self.manager.active()[0], manifest["previous"])
        self.assert_private_unchanged()

    def test_incompatible_rollback_refuses_before_any_stop(self):
        name, _, _ = self.release()
        self.activate(name)
        before = list(self.services.calls)
        with patch.object(updates, "compatible", side_effect=updates.UpdateError("incompatible")):
            with self.assertRaises(updates.UpdateError):
                self.manager.rollback(name)
        self.assertEqual(self.services.calls, before)
        self.assert_private_unchanged()

    def test_rollback_refuses_units_from_another_release(self):
        name, _, _ = self.release()
        self.activate(name)
        self.services.units[updates.UNITS[1]] += "changed\n"
        before = list(self.services.calls)
        with self.assertRaises(updates.UpdateError):
            self.manager.rollback(name)
        self.assertEqual(self.services.calls, before)

    def test_interrupted_partial_unit_install_can_be_recovered(self):
        name, release, manifest = self.release()
        manifest["phase"] = "activating"
        self.manager.save(release, manifest)
        self.services.units[updates.UNITS[0]] = (release / "after" / updates.UNITS[0]).read_text()
        self.assertEqual(self.manager.rollback(name), "rolled-back")
        self.assert_private_unchanged()

    def test_unsafe_release_identifiers_are_rejected(self):
        for name in ("../state", "/tmp/release", "release-" + "a" * 12 + "-" + "b" * 8 + "/x"):
            with self.subTest(name=name), self.assertRaises(updates.UpdateError):
                self.manager.read(name)

    def test_unsafe_paths_and_shared_writable_parent_refused(self):
        for path in (self.home, self.home / "../outside", self.home / "name space"):
            with self.subTest(path=path), self.assertRaises(updates.UpdateError):
                updates.checked_path(path, self.home)
        self.home.chmod(0o755)
        folder = self.home / "shared"
        folder.mkdir(mode=0o777)
        folder.chmod(0o777)
        with self.assertRaises(updates.UpdateError):
            updates.checked_path(folder / "release", self.home)
        self.home.chmod(0o700)
        self.assertEqual(updates.checked_path(folder / "release", self.home), folder / "release")
        self.home.chmod(0o755)
        folder.chmod(0o700)
        (folder / "inner").mkdir(mode=0o775)
        (folder / "inner").chmod(0o775)
        self.assertEqual(updates.checked_path(folder / "inner/release", self.home), folder / "inner/release")

    def test_symlink_parent_refused(self):
        (self.home / "linked").symlink_to(self.state, target_is_directory=True)
        with self.assertRaises(updates.UpdateError):
            updates.checked_path(self.home / "linked/release", self.home)

    def test_backup_rejects_links_and_public_private_files(self):
        (self.state / "linked").symlink_to(self.state / "auth.json")
        with self.assertRaises(updates.UpdateError):
            updates.snapshot_state(self.state, self.home / "backup")
        (self.state / "linked").unlink()
        (self.state / "auth.json").chmod(0o644)
        with self.assertRaises(updates.UpdateError):
            updates.snapshot_state(self.state, self.home / "backup")

    def test_backup_preserves_bytes_and_private_modes_in_nested_directories(self):
        (self.state / "nested").mkdir(mode=0o700)
        (self.state / "nested/deeper").mkdir(mode=0o700)
        updates.private_write(self.state / "nested/deeper/private", b"fixture")
        backup = self.home / "backup"
        updates.snapshot_state(self.state, backup)
        for path in (backup, backup / "nested", backup / "nested/deeper", backup / "nested/deeper/private"):
            self.assertEqual(path.stat().st_mode & 0o077, 0)
        self.assertEqual((backup / "auth.json").read_bytes(), self.private["auth.json"])

    def test_health_requires_expected_version_fresh_frame_and_no_error(self):
        now = time.time()
        health = {"status": "ok", "version": "0.10.0"}
        display = {"currentPage": "status", "error": None,
                   "lastRenderAt": datetime.fromtimestamp(now, timezone.utc).isoformat()}
        self.assertTrue(updates.health_valid(health, display, "0.10.0", now - 1, now))
        self.assertFalse(updates.health_valid(health, display, "0.6.0", now - 1, now))
        self.assertFalse(updates.health_valid(health, display, "0.10.0", now + 1, now + 1))
        self.assertFalse(updates.health_valid(health, display, "0.10.0", now - 100, now + 31))
        for changes in ({"error": "fixture"}, {"lastRenderAt": "invalid"}, {"lastRenderAt": "2026-01-01T00:00:00"}, {"currentPage": None}):
            self.assertFalse(updates.health_valid(health, display | changes, "0.10.0", now - 1, now))

    def test_archive_rejects_traversal_and_links_before_extraction(self):
        for name, kind in (("../escape", tarfile.REGTYPE), ("link", tarfile.SYMTYPE), ("hard", tarfile.LNKTYPE), ("pipe", tarfile.FIFOTYPE)):
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as tar:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.linkname = "/etc/passwd"
                tar.addfile(member)
            with self.subTest(name=name), self.assertRaises(updates.UpdateError):
                updates.extract_archive(archive.getvalue(), self.home / "extracted")
            self.assertFalse((self.home / "extracted").exists())

    def test_archive_safe_regular_file_and_executable(self):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            member = tarfile.TarInfo("scripts/check.sh")
            member.size = 2
            member.mode = 0o755
            tar.addfile(member, io.BytesIO(b"ok"))
        updates.extract_archive(archive.getvalue(), self.home / "extracted")
        path = self.home / "extracted/scripts/check.sh"
        self.assertEqual(path.read_bytes(), b"ok")
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)

    def test_dirty_git_checkout_refused_without_reset(self):
        with patch.object(updates, "run", return_value=b" M fixture\n") as external:
            (self.repository / ".git").mkdir()
            with self.assertRaises(updates.UpdateError):
                updates.fingerprint(self.repository)
            self.assertEqual(external.call_args.args[0], ["git", "status", "--porcelain"])

    def test_prepare_rejects_unknown_sha_before_any_service_operation(self):
        with self.assertRaises(updates.UpdateError):
            self.manager.prepare("origin/main")
        self.assertEqual(self.services.calls, [])
        self.assertFalse(self.manager.root.exists())

    def prepare_double(self, fail_tests=False, fail_venv=False):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            for name, data in (("dashboard/__init__.py", b'__version__ = "0.10.0"\n'), ("requirements.txt", b"fixture-only\n")):
                member = tarfile.TarInfo(name)
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
        calls = []
        def external(arguments, **kwargs):
            calls.append((arguments, kwargs))
            if arguments[:3] == ["git", "rev-parse", "--verify"]:
                return b"a" * 40 + b"\n"
            if arguments[:2] == ["git", "archive"]:
                return archive.getvalue()
            if "venv" in arguments:
                if fail_venv:
                    raise updates.UpdateError("fixture venv failure")
                environment = Path(arguments[-1])
                (environment / "bin").mkdir(parents=True)
                for name in ("python", "waitress-serve"):
                    (environment / "bin" / name).write_text("new-fixture-environment")
            if "unittest" in arguments and fail_tests:
                raise updates.UpdateError("fixture test failure")
            return b"packages-fixture"
        return patch.object(updates, "run", side_effect=external), calls

    def test_prepare_builds_new_environment_and_keeps_existing_code_state_services_unchanged(self):
        external, calls = self.prepare_double()
        before_units = self.services.read_units()
        with external:
            name = self.manager.prepare("a" * 40)
        manifest = self.manager.read(name)
        self.assertEqual(manifest["phase"], "prepared")
        self.assertEqual(manifest["revision"], "a" * 40)
        self.assertEqual(self.services.read_units(), before_units)
        self.assertNotIn("authorize", self.services.calls)
        release = self.manager.root / name
        self.assertEqual(Path(manifest["candidate"]["environment"]), release / "venv")
        self.assertEqual((release / "backup-preparation/auth.json").read_bytes(), self.private["auth.json"])
        self.assertEqual(manifest["candidate"]["fingerprint"], updates.fingerprint(release / "code"))
        tests = next((args, kwargs) for args, kwargs in calls if "unittest" in args)
        self.assertEqual(tests[1]["cwd"], release / "code")
        self.assertEqual(tests[1]["test_state"], release / "test-state")
        self.assert_private_unchanged()

    def test_failed_preparation_cannot_be_activated_and_keeps_original_environment(self):
        external, _ = self.prepare_double(fail_tests=True)
        with external, self.assertRaises(updates.UpdateError):
            self.manager.prepare("a" * 40)
        name = next(self.manager.root.glob("release-*" )).name
        self.assertEqual(self.manager.read(name)["phase"], "failed")
        with self.assertRaises(updates.UpdateError):
            self.manager.activate(name)
        self.assertNotIn("authorize", self.services.calls)
        self.assert_private_unchanged()

    def test_dependency_environment_failure_does_not_touch_active_environment(self):
        external, _ = self.prepare_double(fail_venv=True)
        with external, self.assertRaises(updates.UpdateError):
            self.manager.prepare("a" * 40)
        self.assertEqual(self.manager.read(next(self.manager.root.glob("release-*")).name)["phase"], "failed")
        self.assertNotIn("stop", self.services.calls)
        self.assert_private_unchanged()

    def test_global_lock_blocks_second_operation(self):
        with self.manager.locked(), self.assertRaisesRegex(updates.UpdateError, "em andamento"):
            with self.manager.locked():
                self.fail("second lock acquired")

    def test_real_read_only_compatibility_does_not_create_lock_or_rewrite_private_files(self):
        self.compatibility.stop()
        before = {p.name: p.read_bytes() for p in self.state.iterdir()}
        updates.compatible(ROOT, Path(sys.prefix), self.state)
        self.assertEqual({p.name: p.read_bytes() for p in self.state.iterdir()}, before)
        self.compatibility.start()

    def test_real_read_only_compatibility_rejects_unknown_config_or_corrupt_vault(self):
        self.compatibility.stop()
        config = default_config() | {"futureUnknown": "private-fixture"}
        updates.private_write(self.state / "config.json", json.dumps(config).encode())
        with self.assertRaisesRegex(updates.UpdateError, "incompatível"):
            updates.compatible(ROOT, Path(sys.prefix), self.state)
        updates.private_write(self.state / "config.json", self.private["config.json"])
        updates.private_write(self.state / "credentials.json", b"not-valid-json")
        with self.assertRaisesRegex(updates.UpdateError, "incompatível"):
            updates.compatible(ROOT, Path(sys.prefix), self.state)
        self.assertFalse((self.state / ".credentials.lock").exists())
        self.compatibility.start()

    def test_environment_controls_do_not_leak_into_commands_and_output_is_not_reported(self):
        with patch.dict(os.environ, {"ST7789_DASHBOARD_STATE_DIR": "private", "PYTHONPATH": "inject", "PIP_INDEX_URL": "private-url"}), patch.object(subprocess, "run") as external:
            external.return_value.stdout = b"ok"
            self.assertEqual(updates.run(["tool", "arg"]), b"ok")
            env = external.call_args.kwargs["env"]
            self.assertNotIn("ST7789_DASHBOARD_STATE_DIR", env)
            self.assertNotIn("PYTHONPATH", env)
            self.assertNotIn("PIP_INDEX_URL", env)
            self.assertEqual(env["PIP_CONFIG_FILE"], os.devnull)
            updates.run(["tool"], test_state=self.home / "isolated-state")
            self.assertEqual(external.call_args.kwargs["env"]["ST7789_DASHBOARD_STATE_DIR"], str(self.home / "isolated-state"))
            external.side_effect = subprocess.CalledProcessError(1, ["tool"], output=b"private-output")
            with self.assertRaises(updates.UpdateError) as error:
                updates.run(["tool"])
            self.assertNotIn("private-output", str(error.exception))


if __name__ == "__main__":
    unittest.main()
