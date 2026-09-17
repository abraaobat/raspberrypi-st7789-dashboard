"""Operator-only staged updates. No web imports, shell strings or state restoration."""

from __future__ import annotations

import fcntl
import hashlib
import http.client
import io
import json
import os
import pwd
import re
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

UNITS = ("bench-display.service", "bench-display-web.service")
SAFE_PATH = re.compile(r"/[A-Za-z0-9_./-]+\Z")
RELEASE_ID = re.compile(r"release-[a-f0-9]{12}-[a-f0-9]{8}\Z")
REVISION = re.compile(r"[a-f0-9]{40}\Z")
LIMIT = 64 * 1024 * 1024


class UpdateError(ValueError):
    """Fixed messages only: do not disclose private state or subprocess output."""


def run(arguments, *, cwd=None, timeout=30, test_state=None):
    environment = dict(os.environ)
    for name in list(environment):
        if name.startswith(("ST7789_", "PYTHON", "PIP_")):
            environment.pop(name)
    environment.update(PYTHONDONTWRITEBYTECODE="1", PIP_CONFIG_FILE=os.devnull)
    if test_state is not None:
        environment["ST7789_DASHBOARD_STATE_DIR"] = str(test_state)
    try:
        # A timeout must stop the build tree, not just pip while compilers keep
        # holding its output pipes. This new session belongs only to this step.
        process = subprocess.Popen(arguments, cwd=cwd, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        try:
            output, _ = process.communicate(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # Do not drain inherited pipes: an escaped child may still hold one.
            process.wait(timeout=5)
            raise
        finally:
            process.stdout.close()
            process.stderr.close()
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, arguments)
        return output
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("Etapa externa falhou; serviços ativos não são alterados durante a preparação.") from exc


def checked_path(value, home):
    path = Path(value)
    if not SAFE_PATH.fullmatch(str(path)) or not path.is_absolute() or ".." in path.parts:
        raise UpdateError("Caminho incompatível; espaços, links e caracteres especiais não são suportados.")
    if path == home or home not in path.parents:
        raise UpdateError("Destino precisa estar em um subdiretório da home do operador.")
    if home.is_symlink() or home.stat().st_uid != os.geteuid() or home.stat().st_mode & 0o022:
        raise UpdateError("Home do operador precisa ser própria, protegida e sem links.")
    private_boundary = not bool(home.stat().st_mode & 0o077)
    current = home
    for part in path.relative_to(home).parts:
        current = current / part
        if current.is_symlink():
            raise UpdateError("Links simbólicos não são suportados.")
        if current.exists():
            details = current.stat()
            if details.st_uid != os.geteuid() or (details.st_mode & 0o022 and not private_boundary):
                raise UpdateError("Caminho precisa pertencer ao operador e não permitir escrita por terceiros.")
            # Owner-only traversal on an ancestor protects existing inner umask-0002 paths.
            # Do not change legacy directory permissions or trust shared primary groups.
            private_boundary = private_boundary or not bool(details.st_mode & 0o077)
    return path


def private_read(path, maximum=LIMIT):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as file:
            details = os.fstat(file.fileno())
            if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid() or details.st_mode & 0o077:
                raise UpdateError("Arquivo privado precisa ser regular, do operador e protegido por 0600.")
            if details.st_size > maximum:
                raise UpdateError("Arquivo excede o limite de preparação.")
            data = file.read(maximum + 1)
            if len(data) > maximum:
                raise UpdateError("Arquivo excede o limite de preparação.")
            return data
    except OSError as exc:
        raise UpdateError("Não foi possível ler um arquivo privado; preserve-o para recuperação.") from exc


def private_write(path, data):
    descriptor, temporary = tempfile.mkstemp(prefix=".update-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def version(code):
    match = re.fullmatch(r'.*__version__ = "(\d+\.\d+\.\d+)"\s*',
                         (code / "dashboard/__init__.py").read_text(), re.S)
    if not match:
        raise UpdateError("Versão de software não reconhecida.")
    return match[1]


def render_units(code, environment, user, state, templates):
    replacements = {"User=pi\n": f"User={user}\n",
                    "/home/pi/raspberrypi-st7789-dashboard": str(code),
                    "/home/pi/st7789-env": str(environment),
                    "/home/pi/.config/raspberrypi-st7789-dashboard": str(state)}
    result = {}
    for name in UNITS:
        text = templates[name]
        for old, new in replacements.items():
            text = text.replace(old, new)
        result[name] = text
    return result


def snapshot_state(state, destination):
    """Bounded copy; files are individually atomic, not a global live-state transaction."""
    if state.is_symlink() or state.stat().st_uid != os.geteuid() or state.stat().st_mode & 0o077:
        raise UpdateError("Diretório de estado precisa ser privado, do operador e sem links.")
    entries = []
    total = 0
    for path in sorted(state.rglob("*")):
        if path.parent == state and (path.name in {"display-state.json.tmp", "control.json.tmp", "auth.tmp", "session-secret.tmp"}
                or re.fullmatch(r"\.(config|credentials|pomodoro)-[^/]+\.tmp", path.name)):
            # Atomic writers rename these transient files; they are never recovery records.
            continue
        if len(entries) >= 2048:
            raise UpdateError("Estado excede o limite de arquivos de backup.")
        if path.is_symlink():
            raise UpdateError("Backup recusado: link simbólico no estado.")
        if path.is_dir():
            if path.stat().st_uid != os.geteuid() or path.stat().st_mode & 0o077:
                raise UpdateError("Backup recusado: subdiretório de estado não privado.")
            continue
        data = private_read(path)
        total += len(data)
        if total > LIMIT:
            raise UpdateError("Estado excede 64 MiB; backup automático recusado.")
        entries.append((path.relative_to(state), data))
    destination.mkdir(mode=0o700)
    for relative, data in entries:
        parent = destination / relative.parent
        current = destination
        for part in relative.parent.parts:
            current = current / part
            current.mkdir(mode=0o700, exist_ok=True)
        private_write(destination / relative, data)


def extract_archive(data, destination):
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        members = archive.getmembers()
        if sum(item.size for item in members) > 256 * 1024 * 1024:
            raise UpdateError("Release excede o limite de extração.")
        names = set()
        for item in members:
            path = Path(item.name)
            if path.is_absolute() or ".." in path.parts or not (item.isfile() or item.isdir()) or item.name in names:
                raise UpdateError("Release contém caminho, link ou tipo de arquivo não permitido.")
            names.add(item.name)
        destination.mkdir(mode=0o700)
        for item in members:
            path = destination / item.name
            if item.isdir():
                path.mkdir(parents=True, mode=0o700, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                with archive.extractfile(item) as file:
                    private_write(path, file.read())
                if item.mode & 0o111:
                    path.chmod(0o700)


def fingerprint(code):
    if (code / ".git").exists():
        if run(["git", "status", "--porcelain"], cwd=code).strip():
            raise UpdateError("Checkout com alterações: não será modificado nem usado para retorno automático.")
        paths = [code / item.decode() for item in run(["git", "ls-files", "-z"], cwd=code).split(b"\0") if item]
    else:
        paths = [item for item in code.rglob("*") if not item.is_dir() and "__pycache__" not in item.parts]
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file():
            raise UpdateError("Código contém link ou arquivo irregular.")
        digest.update(str(path.relative_to(code)).encode() + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


COMPATIBILITY = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
try:
    from dashboard.config import normalize_config
    from dashboard.credentials import CredentialStore
    state = Path(sys.argv[2])
    path = state / "config.json"
    if path.exists():
        original = json.loads(path.read_text())
        normalized = normalize_config(original)
        def contains(old, new):
            if isinstance(old, dict):
                return isinstance(new, dict) and all(k in new and contains(v, new[k]) for k, v in old.items())
            if isinstance(old, list):
                return isinstance(new, list) and len(new) >= len(old) and all(contains(a, b) for a, b in zip(old, new))
            return type(old) is type(new) and old == new
        if not contains(original, normalized):
            raise ValueError()
    CredentialStore(state)._read()  # Deliberately no lock/mkdir/chmod/write methods.
except Exception:
    sys.exit(1)
'''


def compatible(code, environment, state):
    try:
        run([str(environment / "bin/python"), "-I", "-B", "-c", COMPATIBILITY,
             str(code), str(state)], cwd=code)
    except UpdateError as exc:
        raise UpdateError("Versão incompatível com configuração/cofre atuais; nenhum dado privado será sobrescrito.") from exc


def health_valid(health, display, expected_version, since, now):
    try:
        rendered = datetime.fromisoformat(display["lastRenderAt"])
        timestamp = rendered.timestamp() if rendered.tzinfo else -1
        return (health == {"status": "ok", "version": expected_version}
                and isinstance(display.get("currentPage"), str) and bool(display["currentPage"])
                and not display.get("error") and since < timestamp <= now + 2 and now - timestamp < 30)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


class SystemServices:
    def read_units(self):
        result = {}
        for name in UNITS:
            path = Path("/etc/systemd/system") / name
            details = path.lstat()
            if not stat.S_ISREG(details.st_mode) or details.st_uid != 0 or details.st_mode & 0o022:
                raise UpdateError("Arquivo de serviço fora do contrato padrão.")
            fragment = run(["systemctl", "show", name, "--property=FragmentPath", "--value"]).decode().strip()
            dropins = run(["systemctl", "show", name, "--property=DropInPaths", "--value"]).strip()
            if fragment != str(path) or dropins:
                raise UpdateError("Serviços personalizados/drop-ins: atualização automática não suportada.")
            result[name] = path.read_text()
        return result

    def authorize(self):
        # Password is read only by sudo in the operator's own terminal.
        try:
            subprocess.run(["sudo", "-v"], check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise UpdateError("Autorização de administrador não obtida; nenhuma troca iniciada.") from exc

    def stop(self):
        run(["sudo", "-n", "systemctl", "stop", *UNITS])

    def install(self, files):
        for name in UNITS:
            temporary = Path("/etc/systemd/system") / ("." + name + ".st7789-next")
            run(["sudo", "-n", "install", "-m", "0644", "-o", "root", "-g", "root",
                 str(files / name), str(temporary)])
            run(["sudo", "-n", "mv", "-T", "--", str(temporary), str(Path("/etc/systemd/system") / name)])
        run(["sudo", "-n", "systemctl", "daemon-reload"])

    def start(self):
        run(["sudo", "-n", "systemctl", "start", *UNITS])

    def healthy(self, expected, state, since):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            connection = None
            try:
                for name in UNITS:
                    run(["systemctl", "is-active", "--quiet", name], timeout=3)
                if not Path("/dev/spidev0.0").exists():
                    return False
                connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=2)
                connection.request("GET", "/api/health")
                response = connection.getresponse()
                body = response.read(4097)
                if response.status == 200 and len(body) <= 4096:
                    health = json.loads(body)
                    display = json.loads(private_read(state / "display-state.json", 16384))
                    if health_valid(health, display, expected, since, time.time()):
                        return True
            except (OSError, ValueError, UpdateError, http.client.HTTPException):
                pass
            finally:
                if connection:
                    connection.close()
            time.sleep(1)
        return False


class UpdateManager:
    def __init__(self, repository, home=None, user=None, services=None):
        operator = pwd.getpwuid(os.geteuid())
        self.home = Path(home or operator.pw_dir)
        self.user = user or operator.pw_name
        if not re.fullmatch(r"[a-z_][a-z0-9_-]*", self.user):
            raise UpdateError("Operador incompatível com serviços padrão.")
        self.repository = checked_path(repository, self.home)
        self.state = checked_path(self.home / ".config/raspberrypi-st7789-dashboard", self.home)
        self.root = checked_path(self.home / ".config/raspberrypi-st7789-updates", self.home)
        self.services = services or SystemServices()
        self.templates = {name: (self.repository / "systemd" / name).read_text() for name in UNITS}

    @contextmanager
    def locked(self):
        self.root.mkdir(mode=0o700, exist_ok=True)
        if self.root.stat().st_mode & 0o077:
            raise UpdateError("Diretório de atualizações precisa ter permissão 0700.")
        descriptor = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "a") as file:
            details = os.fstat(file.fileno())
            if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid() or details.st_mode & 0o077:
                raise UpdateError("Arquivo de bloqueio inválido.")
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise UpdateError("Outra atualização está em andamento.") from exc
            yield

    def active(self):
        units = self.services.read_units()
        match = re.search(r"^WorkingDirectory=(.+)$", units[UNITS[0]], re.M)
        executable = re.search(r"^ExecStart=(.+)/bin/python ", units[UNITS[0]], re.M)
        if not match or not executable:
            raise UpdateError("Instalação ativa fora do contrato padrão.")
        code = checked_path(match[1], self.home)
        environment = checked_path(executable[1], self.home)
        if render_units(code, environment, self.user, self.state, self.templates) != units:
            raise UpdateError("Serviços personalizados: não serão sobrescritos.")
        if not (environment / "bin/python").is_file() or not (environment / "bin/waitress-serve").is_file():
            raise UpdateError("Ambiente ativo incompleto; preserve a instalação para recuperação.")
        return {"code": str(code), "environment": str(environment), "version": version(code),
                "fingerprint": fingerprint(code)}, units

    def preflight(self):
        previous, units = self.active()
        snapshot_permissions = self.state.stat()
        if self.state.is_symlink() or snapshot_permissions.st_mode & 0o077:
            raise UpdateError("Estado precisa estar protegido por 0700.")
        compatible(Path(previous["code"]), Path(previous["environment"]), self.state)
        if not self.services.healthy(previous["version"], self.state, time.time() - 30):
            raise UpdateError("Instalação ativa sem saúde/frescura confirmadas; não iniciar atualização.")
        return previous, units

    def pending(self):
        for path in sorted(self.root.glob("release-*")):
            manifest = self.read(path.name)
            if manifest["phase"] in {"activating", "recovery-required"}:
                raise UpdateError("Troca interrompida: execute rollback do release pendente antes de continuar.")

    def save(self, release, manifest):
        private_write(release / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())

    def read(self, name):
        if not RELEASE_ID.fullmatch(name):
            raise UpdateError("Identificador de release inválido.")
        release = checked_path(self.root / name, self.home)
        try:
            manifest = json.loads(private_read(release / "manifest.json", 65536))
            if manifest["schemaVersion"] != 1 or manifest["id"] != name or manifest["home"] != str(self.home):
                raise ValueError()
            if manifest["phase"] not in {"preparing", "prepared", "failed", "activating", "active", "rolled-back", "recovery-required"}:
                raise ValueError()
        except (KeyError, ValueError, TypeError) as exc:
            raise UpdateError("Manifesto inválido; preserve o release para recuperação local.") from exc
        return manifest

    def prepare(self, revision):
        if not REVISION.fullmatch(revision):
            raise UpdateError("Informe o SHA completo de 40 caracteres da revisão escolhida.")
        with self.locked():
            self.pending()
            previous, units = self.preflight()
            fingerprint(self.repository)
            resolved = run(["git", "rev-parse", "--verify", revision + "^{commit}"], cwd=self.repository).decode().strip()
            if resolved != revision:
                raise UpdateError("Revisão local não corresponde ao SHA informado.")
            name = f"release-{revision[:12]}-{uuid.uuid4().hex[:8]}"
            release = self.root / name
            release.mkdir(mode=0o700)
            manifest = {"schemaVersion": 1, "id": name, "home": str(self.home), "phase": "preparing",
                        "revision": revision, "createdAt": datetime.now(timezone.utc).isoformat(), "previous": previous}
            self.save(release, manifest)
            try:
                extract_archive(run(["git", "archive", "--format=tar", revision], cwd=self.repository), release / "code")
                candidate = release / "code"
                environment = release / "venv"
                for folder, contents in (("before", units), ("after", render_units(candidate, environment, self.user, self.state, self.templates))):
                    destination = release / folder
                    destination.mkdir(mode=0o700)
                    for unit, text in contents.items():
                        private_write(destination / unit, text.encode())
                snapshot_state(self.state, release / "backup-preparation")
                # The environment is created at its FINAL path; venvs must not be moved.
                run([sys.executable, "-I", "-B", "-m", "venv", str(environment)], timeout=120)
                interpreter = str(environment / "bin/python")
                run([interpreter, "-I", "-B", "-m", "pip", "install", "--disable-pip-version-check",
                     "-r", str(candidate / "requirements.txt")], cwd=candidate, timeout=1800)
                run([interpreter, "-I", "-B", "-m", "pip", "check"], timeout=30)
                test_state = release / "test-state"
                test_state.mkdir(mode=0o700)
                # Defaults used by trusted release tests must not select live dashboard state.
                run([interpreter, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                    cwd=candidate, timeout=600, test_state=test_state)
                compatible(candidate, environment, self.state)
                manifest["candidate"] = {"code": str(candidate), "environment": str(environment),
                                         "version": version(candidate), "fingerprint": fingerprint(candidate)}
                private_write(release / "packages.txt", run([interpreter, "-I", "-B", "-m", "pip", "freeze"]))
                # Refuse ready status if active service paths/code changed during preparation.
                if self.active() != (previous, units):
                    raise UpdateError("Instalação ativa mudou durante a preparação; release não será ativado.")
                manifest["phase"] = "prepared"
                self.save(release, manifest)
                return name
            except BaseException:
                manifest["phase"] = "failed"
                self.save(release, manifest)
                raise

    def verify_target(self, target):
        code = checked_path(target["code"], self.home)
        environment = checked_path(target["environment"], self.home)
        if version(code) != target["version"] or fingerprint(code) != target["fingerprint"]:
            raise UpdateError("Código mudou desde a preparação; troca recusada.")
        if not (environment / "bin/python").is_file() or not (environment / "bin/waitress-serve").is_file():
            raise UpdateError("Ambiente do release incompleto.")
        compatible(code, environment, self.state)
        return code, environment

    def verify_files(self, release, folder, target):
        expected = render_units(Path(target["code"]), Path(target["environment"]), self.user, self.state, self.templates)
        files = release / folder
        if {name: private_read(files / name).decode() for name in UNITS} != expected:
            raise UpdateError("Arquivos de serviço preparados foram modificados; troca recusada.")

    def restore(self, release, manifest):
        self.services.stop()
        self.verify_target(manifest["previous"])
        self.verify_files(release, "before", manifest["previous"])
        self.services.install(release / "before")
        since = time.time()
        self.services.start()
        if not self.services.healthy(manifest["previous"]["version"], self.state, since):
            raise UpdateError("Retorno não passou na saúde; exige diagnóstico local. Estado privado preservado.")
        manifest["phase"] = "rolled-back"
        self.save(release, manifest)

    def activate(self, name):
        with self.locked():
            self.pending()
            manifest = self.read(name)
            release = self.root / name
            if manifest["phase"] != "prepared":
                raise UpdateError("Somente um release preparado pode ser ativado.")
            active, units = self.preflight()
            if active != manifest["previous"]:
                raise UpdateError("Release não corresponde mais à instalação ativa; prepare novamente.")
            self.verify_target(manifest["candidate"])
            self.verify_files(release, "after", manifest["candidate"])
            self.verify_files(release, "before", manifest["previous"])
            if private_read(release / "packages.txt") != run([str(Path(manifest["candidate"]["environment"]) / "bin/python"), "-I", "-B", "-m", "pip", "freeze"]):
                raise UpdateError("Pacotes preparados mudaram; prepare novamente.")
            self.services.authorize()
            manifest["phase"] = "activating"
            self.save(release, manifest)  # Durable journal BEFORE stopping/installing.
            try:
                self.services.stop()
                snapshot_state(self.state, release / "backup-activation")
                self.verify_target(manifest["candidate"])
                self.verify_target(manifest["previous"])
                self.services.install(release / "after")
                since = time.time()
                self.services.start()
                if not self.services.healthy(manifest["candidate"]["version"], self.state, since):
                    raise UpdateError("Nova versão não passou na saúde.")
                manifest["phase"] = "active"
                self.save(release, manifest)
                return "active"
            except BaseException as cause:
                try:
                    self.restore(release, manifest)
                except BaseException:
                    manifest["phase"] = "recovery-required"
                    self.save(release, manifest)
                    raise UpdateError("Recuperação pendente: use rollback no terminal; nunca sobrescreva estado/cofre automaticamente.") from cause
                raise UpdateError("Troca falhou; versão anterior restaurada e saudável. Estado privado não foi revertido.") from cause

    def rollback(self, name):
        with self.locked():
            manifest = self.read(name)
            release = self.root / name
            if manifest["phase"] not in {"active", "activating", "recovery-required"}:
                raise UpdateError("Release não possui troca ativa ou interrompida para retornar.")
            actual = self.services.read_units()
            before = {unit: private_read(release / "before" / unit).decode() for unit in UNITS}
            after = {unit: private_read(release / "after" / unit).decode() for unit in UNITS}
            if any(actual[unit] not in {before[unit], after[unit]} for unit in UNITS):
                raise UpdateError("Serviços não pertencem a esta troca; nenhum serviço será sobrescrito.")
            # Incompatible new config/vault is a manual migration, not permission to erase it.
            self.verify_target(manifest["previous"])
            self.verify_files(release, "before", manifest["previous"])
            self.services.authorize()
            manifest["phase"] = "recovery-required"
            self.save(release, manifest)
            self.restore(release, manifest)
            return "rolled-back"
