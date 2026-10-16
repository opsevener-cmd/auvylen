"""Private Codespaces lifecycle only; existing application/model code is unchanged."""

import argparse
import getpass
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def context() -> tuple[Path, str, Path]:
    if (
        sys.platform != "linux"
        or "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
    ):
        raise SystemExit("Use the remote Codespace; Windows/WSL services are not supported.")
    if os.environ.get("AUVYLEN_PREVIEW_TEST") == "1":
        origin = os.environ["AUVYLEN_PREVIEW_TEST_ORIGIN"]
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "localhost"
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
        ):
            raise SystemExit("Preview test origin must be a loopback HTTPS origin")
        return (
            Path(os.environ["AUVYLEN_PREVIEW_TEST_DATA"]),
            origin,
            Path(os.environ["AUVYLEN_PREVIEW_TEST_SECRETS"]),
        )
    if os.environ.get("CODESPACES") != "true":
        raise SystemExit("This command runs only inside GitHub Codespaces.")
    name = os.environ.get("CODESPACE_NAME", "")
    domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    if not re.fullmatch(r"[a-z0-9-]{1,100}", name) or domain != "app.github.dev":
        raise SystemExit("Unexpected Codespaces forwarding identity; do not guess an origin")
    return (
        ROOT / "private-data/codespaces",
        f"https://{name}-3000.{domain}",
        Path("/run/auvylen-preview-secrets"),
    )


def call(command: list[str], env: dict[str, str], **options: object) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True, **options)


def environment(data: Path, origin: str, secret_dir: Path) -> dict[str, str]:
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("runtime", "uploads", "models"):
        (data / name).mkdir(exist_ok=True, mode=0o700)
    password = (secret_dir / "postgres-password").read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{96}", password):
        raise SystemExit("Invalid preview database credential file")
    config = data / "credentials.json"
    if not config.exists():
        database_env = dict(os.environ, PGPASSWORD=password)
        migrated = (
            subprocess.run(
                [
                    "psql",
                    "-h",
                    "postgres",
                    "-U",
                    "aevyra",
                    "-d",
                    "aevyra",
                    "-Atc",
                    "SELECT to_regclass('public.alembic_version') IS NOT NULL",
                ],
                env=database_env,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            ).stdout.strip()
            == b"t"
        )
        if migrated:
            raise SystemExit(
                "Existing preview database lost app credentials; restore its matching backup"
            )
        # Refuse silent pepper replacement if existing research artifacts survive.
        if any((data / "uploads").iterdir()) or (data / "models/custom").exists():
            raise SystemExit(
                "Retained private data has lost its credentials; restore the matching backup"
            )
        with config.open("x") as file:
            os.chmod(config, 0o600)
            json.dump({"postgres_password": password, "pepper": secrets.token_hex(48)}, file)
    stored = json.loads(config.read_text())
    if stored["postgres_password"] != password:
        raise SystemExit(
            "Preview credentials do not match the retained database; restore matching state"
        )
    env = dict(os.environ)
    env.update(
        {
            "APP_ENV": "staging",
            "DATABASE_URL": f"postgresql+psycopg://aevyra:{password}@postgres:5432/aevyra",
            "REDIS_URL": "redis://redis:6379/0",
            "API_URL": "http://127.0.0.1:8000",
            "REDEMPTION_CODE_PEPPER": stored["pepper"],
            "CORS_ORIGINS": json.dumps([origin]),
            "SESSION_COOKIE_SECURE": "true",
            "RESEARCH_MODE": "true",
            "SHARED_PROXY_RATE_LIMITS": "true",
            "MOCK_CHECKOUT_ENABLED": "false",
            "PUBLIC_PILOT": "false",
            "ENABLED_MODEL_PROVIDERS": "[]",
            "PRIVATE_UPLOAD_ROOT": str(data / "uploads"),
            "PRIVATE_MODEL_ROOT": str(data / "models"),
            "UV_PROJECT_ENVIRONMENT": str(data / "venv"),
            "UV_CACHE_DIR": str(data / "package-cache"),
            "NEXT_TELEMETRY_DISABLED": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "APPLY_MIGRATIONS": "true",
        }
    )
    env.pop("PUBLIC_BASE_URL", None)
    for name in ("NO_PROXY", "no_proxy"):
        env[name] = ",".join(
            filter(None, [env.get(name, ""), "localhost,127.0.0.1,::1,postgres,redis"])
        )
    return env


def python(data: Path) -> str:
    return str(data / "venv/bin/python")


def supervisor(data: Path, action: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["supervisorctl", "-c", str(data / "runtime/supervisord.conf"), action],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def write_supervisor(data: Path) -> None:
    runtime = data / "runtime"
    text = f"""[unix_http_server]
file={runtime}/supervisor.sock
chmod=0700
[supervisord]
logfile={runtime}/supervisor.log
logfile_maxbytes=1MB
logfile_backups=2
pidfile={runtime}/supervisor.pid
childlogdir={runtime}
[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface
[supervisorctl]
serverurl=unix://{runtime}/supervisor.sock
"""
    for priority, service in enumerate(("api", "worker", "web"), 10):
        text += f"""[program:{service}]
command={python(data)} {ROOT}/scripts/codespaces-preview.py run {service}
directory={ROOT}
priority={priority}
autostart=true
autorestart=unexpected
startsecs=2
stopwaitsecs=30
stopasgroup=true
killasgroup=true
redirect_stderr=true
stdout_logfile={runtime}/{service}.log
stdout_logfile_maxbytes=2MB
stdout_logfile_backups=2
"""
    config = runtime / "supervisord.conf"
    config.write_text(text)
    os.chmod(config, 0o600)


def stop(data: Path) -> None:
    if (data / "runtime/supervisord.conf").exists():
        result = supervisor(data, "shutdown")
        if result.returncode == 0:
            for _ in range(40):
                if not (data / "runtime/supervisor.sock").exists():
                    break
                time.sleep(1)
            else:
                raise SystemExit("Preview shutdown did not complete; inspect private runtime logs")
        elif (data / "runtime/supervisor.sock").exists():
            raise SystemExit("Cannot stop the preview safely; inspect private runtime logs")
    print("Application stopped; database, uploads and models retained.")


def restore_model(data: Path, env: dict[str, str]) -> None:
    graph = data / "models/pretrained/mobilenetv3-small-100-lamb-embedding-v1.onnx"
    if not graph.exists():
        export = data / "export-tools"
        call(["uv", "venv", str(export), "--python", "3.14"], env)
        export_python = str(export / "bin/python")
        call(
            [
                "uv",
                "pip",
                "install",
                "--python",
                export_python,
                "--index-url",
                "https://download.pytorch.org/whl/cpu",
                "torch==2.10.0+cpu",
                "torchvision==0.25.0+cpu",
            ],
            env,
        )
        call(
            [
                "uv",
                "pip",
                "install",
                "--python",
                export_python,
                "timm==1.0.30",
                "onnx==1.22.0",
                "numpy==2.5.4",
            ],
            env,
        )
        output = data / "exported/mobilenetv3-small-100-lamb-embedding-v1.onnx"
        call(
            [
                export_python,
                "scripts/export-pretrained-extractor.py",
                "--download",
                "--output",
                str(output),
            ],
            env,
        )
        call(
            [
                python(data),
                "scripts/install-pretrained-extractor.py",
                "--source-file",
                str(output),
                "--root",
                str(graph.parent),
            ],
            env,
        )
        # Only disposable conversion tools; preserve source data/checkpoints and the verified graph.
        shutil.rmtree(export)
        shutil.rmtree(data / "exported")
        call(["uv", "cache", "clean", "torch", "torchvision", "timm", "onnx"], env)
    call(
        [
            python(data),
            "-c",
            (
                "from pathlib import Path; import os; "
                "from aevyra_inference.extractors import verified_weights; "
                "verified_weights(Path(os.environ['PRIVATE_MODEL_ROOT'])/'pretrained'); "
                "print('Verified MobileNetV3 graph ready')"
            ),
        ],
        env,
    )


def setup(data: Path, env: dict[str, str]) -> None:
    if (data / "runtime/supervisor.sock").exists():
        stop(data)
    call(["uv", "sync", "--locked"], env)
    call(["npm", "ci", "--strict-ssl=true"], env)
    restore_model(data, env)
    call([python(data), "-m", "aevyra_api.migrate"], env)
    call(["npm", "run", "build"], env)
    write_supervisor(data)
    print("Preview setup complete. Start: python scripts/codespaces-preview.py start")


def start(data: Path, origin: str, env: dict[str, str]) -> None:
    if not (ROOT / "apps/web/.next/BUILD_ID").is_file() or not Path(python(data)).is_file():
        raise SystemExit("Run the setup command first; check the Codespaces creation log")
    restore_model(data, env)
    call([python(data), "-m", "aevyra_api.migrate"], env)
    socket = data / "runtime/supervisor.sock"
    if socket.exists() and supervisor(data, "pid").returncode != 0:
        # A Codespace/container stop can leave filesystem state after all processes die.
        socket.unlink()
        (data / "runtime/supervisor.pid").unlink(missing_ok=True)
    if not socket.exists():
        write_supervisor(data)
        call(["supervisord", "-c", str(data / "runtime/supervisord.conf")], env)
    # Fixed loopback readiness only, never route a private origin through an outbound proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(90):
        try:
            with opener.open("http://127.0.0.1:8000/ready", timeout=2) as response:
                ready = response.status == 200
            with opener.open("http://127.0.0.1:3000/health", timeout=2) as response:
                ready = ready and response.status == 200
            statuses = supervisor(data, "status")
            if ready and statuses.returncode == 0 and statuses.stdout.count(b"RUNNING") == 3:
                print("Open port 3000 in the Codespaces Ports tab; keep visibility Private.")
                print(origin)
                return
        except (OSError, urllib.error.URLError):
            pass  # Expected startup readiness retries, bounded to 90 attempts.
        time.sleep(1)
    raise SystemExit("Preview did not become ready; inspect private-data/codespaces/runtime/*.log")


def run(data: Path, env: dict[str, str], service: str) -> None:
    if service == "web":
        os.chdir(ROOT / "apps/web")
        command = [
            shutil.which("node") or "node",
            str(ROOT / "node_modules/next/dist/bin/next"),
            "start",
            "--hostname",
            "0.0.0.0",
            "--port",
            "3000",
        ]
    else:
        command = (
            [
                python(data),
                "-m",
                "uvicorn",
                "aevyra_api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            ]
            if service == "api"
            else [python(data), "-m", "aevyra_api.research.worker"]
        )
    os.execve(command[0], command, env)


def backup(data: Path, env: dict[str, str]) -> None:
    password = getpass.getpass("Encrypted backup passphrase (save separately): ")
    if len(password) < 12:
        raise SystemExit("Use a backup passphrase of at least 12 characters")
    was_running = (data / "runtime/supervisor.sock").exists()
    stop(data)
    destination = ROOT / "backups/codespaces"
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = destination / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".tar.gz.gpg")
    try:
        with tempfile.TemporaryDirectory(dir=destination) as temporary:
            directory = Path(temporary)
            dump_env = dict(
                env,
                PGPASSWORD=json.loads((data / "credentials.json").read_text())["postgres_password"],
            )
            call(
                [
                    "pg_dump",
                    "-h",
                    "postgres",
                    "-U",
                    "aevyra",
                    "-d",
                    "aevyra",
                    "-Fc",
                    "-f",
                    str(directory / "database.dump"),
                ],
                dump_env,
            )
            archive = directory / "backup.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(directory / "database.dump", arcname="database.dump")
                for name in ("credentials.json", "uploads", "models"):
                    tar.add(data / name, arcname=name)
            call(
                [
                    "gpg",
                    "--batch",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase-fd",
                    "0",
                    "--symmetric",
                    "--cipher-algo",
                    "AES256",
                    "--output",
                    str(output),
                    str(archive),
                ],
                env,
                input=(password + "\n").encode(),
            )
        os.chmod(output, 0o600)
        output.with_suffix(output.suffix + ".sha256").write_text(
            hashlib.sha256(output.read_bytes()).hexdigest() + "  " + output.name + "\n"
        )
        print("Encrypted consistent backup:", output)
        print("Keep this backup in approved private storage before deleting the Codespace.")
    finally:
        if was_running:
            start(data, context()[1], env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["setup", "start", "stop", "status", "grant", "backup", "run", "owner-init"]
    )
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    data, origin, secret_dir = context()
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.action in {"setup", "start", "stop", "backup", "owner-init"}:
        import fcntl

        with (data / "control.lock").open("a") as lock:
            os.chmod(data / "control.lock", 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            dispatch(args, data, origin, secret_dir)
    else:
        dispatch(args, data, origin, secret_dir)


def dispatch(args: argparse.Namespace, data: Path, origin: str, secret_dir: Path) -> None:
    if args.action == "stop":
        stop(data)
        return
    if args.action == "status":
        result = supervisor(data, "status")
        print(result.stdout.decode())
        raise SystemExit(result.returncode)
    env = environment(data, origin, secret_dir)
    if args.action == "setup":
        setup(data, env)
    elif args.action == "owner-init":
        call([python(data), "-m", "aevyra_api.owner"], env)
    elif args.action == "start":
        start(data, origin, env)
    elif args.action == "backup":
        backup(data, env)
    elif args.action == "grant":
        if not args.value:
            raise SystemExit("grant requires your registered login/username")
        login = args.value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._@+-]{2,119}", login):
            raise SystemExit("Use your exact registered username")
        lookup = (
            "import sys; from sqlalchemy import select; "
            "from aevyra_api.config import Settings; "
            "from aevyra_api.database import DependencyChecks; "
            "from aevyra_api.credits.models import User; "
            "db=DependencyChecks(Settings())\n"
            "with db.sessions() as session: "
            "value=session.scalar(select(User.public_user_id).where("
            "User.login_identifier==sys.argv[1],User.disabled_at.is_(None)))\n"
            "db.close()\n"
            "if value is None: raise SystemExit('Registered user not found')\n"
            "print(value)"
        )
        public_id = (
            subprocess.check_output([python(data), "-c", lookup, login], env=env, cwd=ROOT)
            .decode()
            .strip()
        )
        call(
            [
                python(data),
                "-m",
                "aevyra_api.research.operator",
                "grant",
                public_id,
                "--reason",
                "Owner-authorized private Codespaces preview",
            ],
            env,
        )
    elif args.action == "run":
        if args.value not in {"api", "worker", "web"}:
            raise SystemExit("Invalid preview service")
        run(data, env, args.value)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit(
            "Preview command failed; see the setup log or private runtime logs"
        ) from None
