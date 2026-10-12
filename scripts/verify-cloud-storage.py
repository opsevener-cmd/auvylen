"""Disposable cloud simulation only: test private volumes and database restoration.

Does not touch any non-test project, real images, weights, or user secrets.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
docker = shutil.which("docker")
if not docker and os.environ.get("LOCALAPPDATA"):
    candidate = Path(os.environ["LOCALAPPDATA"]) / "Programs/DockerDesktop/resources/bin/docker.exe"
    if candidate.exists():
        docker = str(candidate)
if not docker:
    raise SystemExit("Docker CLI required")
compose = [
    docker,
    "compose",
    "--env-file",
    ".env.cloud.local",
    "-p",
    "auvylen-phase4a-test",
    "-f",
    "docker-compose.prod.yml",
    "-f",
    "docker-compose.cloud.yml",
    "-f",
    "docker-compose.cloud.local.yml",
    "--profile",
    "research",
]


def run(*args: str) -> str:
    result = subprocess.run([*compose, *args], cwd=root, capture_output=True, check=False)
    if result.returncode:
        line = sys._getframe(1).f_lineno
        raise SystemExit(
            f"Storage verification command at line {line} failed; inspect container logs"
        )
    return result.stdout.decode().strip()


probe = """import json
from uuid import UUID
from aevyra_api.config import Settings
from aevyra_api.research.storage import PrivateArtifactStore
s=Settings(); owner=UUID('00000000-0000-4000-8000-000000000004')
kind=__import__('sys').argv[1]
store=PrivateArtifactStore(s.private_upload_root if kind=='uploads' else s.private_model_root)
artifact,digest=store.put(owner, b'phase4a-synthetic-artifact-not-image-or-model')
print(json.dumps({'owner':str(owner),'artifact':str(artifact),'sha256':digest,'kind':kind}))
"""
records = [
    json.loads(run("exec", "-T", service, "python", "-c", probe, kind))
    for service, kind in [("api", "uploads"), ("worker", "models")]
]
run("exec", "-T", "redis", "redis-cli", "SET", "phase4a:verification", "synthetic-counter")
run("restart", "api", "worker", "redis")
run("up", "-d", "--wait")
assert run("exec", "-T", "redis", "redis-cli", "GET", "phase4a:verification") == "synthetic-counter"
verify = """import hashlib,sys
from uuid import UUID
from aevyra_api.config import Settings
from aevyra_api.research.storage import PrivateArtifactStore
s=Settings()
artifact_root=s.private_upload_root if sys.argv[1]=='uploads' else s.private_model_root
store=PrivateArtifactStore(artifact_root)
data=store.read(UUID(sys.argv[2]),UUID(sys.argv[3]))
assert hashlib.sha256(data).hexdigest()==sys.argv[4]
print('private_artifact_hash_verified')
"""
for record in records:
    assert (
        run(
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            verify,
            record["kind"],
            record["owner"],
            record["artifact"],
            record["sha256"],
        )
        == "private_artifact_hash_verified"
    )
restore_database = "phase4a_restore_" + uuid4().hex
backup = root / "backups" / ("phase4a-" + uuid4().hex)
backup.mkdir(parents=True)
run("stop", "api", "worker")
try:
    run(
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/phase4a-verification.dump',
    )
    # A fresh database in the disposable test cluster, never a production restore.
    run(
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        f'createdb -U "$POSTGRES_USER" {restore_database}',
    )
    run(
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        'pg_restore --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" '
        f"-d {restore_database} /tmp/phase4a-verification.dump",
    )
    result = run(
        "exec",
        "-T",
        "postgres",
        "sh",
        "-c",
        f'psql -U "$POSTGRES_USER" -d {restore_database} -Atc "'
        "SELECT version_num FROM alembic_version; "
        "SELECT count(*) FROM wallets WHERE cached_balance=9; "
        "SELECT count(*) FROM research_jobs WHERE status='COMPLETED';\"",
    )
    rows = result.splitlines()
    assert rows[0] == "0004_research" and int(rows[1]) >= 1 and int(rows[2]) >= 1
    run(
        "run",
        "--rm",
        "--no-deps",
        "--user",
        "0",
        "--cap-add",
        "DAC_OVERRIDE",
        "--cap-add",
        "CHOWN",
        "--volume",
        f"{backup}:/backup",
        "api",
        "python",
        "-c",
        "import tarfile; t=tarfile.open('/backup/artifacts.tar.gz','w:gz'); "
        "t.add('/var/lib/auvylen/uploads',arcname='uploads'); "
        "t.add('/var/lib/auvylen/models',arcname='models'); t.close()",
    )
    restore_volume = "auvylen-phase4a-test_restore_" + uuid4().hex
    run(
        "run",
        "--rm",
        "--no-deps",
        "--user",
        "0",
        "--cap-add",
        "DAC_OVERRIDE",
        "--cap-add",
        "CHOWN",
        "--volume",
        f"{backup}:/backup:ro",
        "--volume",
        f"{restore_volume}_uploads:/var/lib/auvylen/uploads",
        "--volume",
        f"{restore_volume}_models:/var/lib/auvylen/models",
        "api",
        "python",
        "-c",
        "import os,tarfile; from pathlib import Path; t=tarfile.open('/backup/artifacts.tar.gz'); "
        "t.extractall('/var/lib/auvylen',filter='data'); t.close(); "
        "roots=[Path('/var/lib/auvylen/uploads'),Path('/var/lib/auvylen/models')]; "
        "[os.chown(p,10001,10001,follow_symlinks=False) for r in roots for p in [r,*r.rglob('*')]]",
    )
    for record in records:
        assert (
            run(
                "run",
                "--rm",
                "--no-deps",
                "--volume",
                f"{restore_volume}_uploads:/var/lib/auvylen/uploads:ro",
                "--volume",
                f"{restore_volume}_models:/var/lib/auvylen/models:ro",
                "api",
                "python",
                "-c",
                verify,
                record["kind"],
                record["owner"],
                record["artifact"],
                record["sha256"],
            )
            == "private_artifact_hash_verified"
        )
    print("Private artifacts and Redis survived restart; database and artifact archives restored")
    print("Restored schema, 9-Credit wallets, completed research jobs and matching artifact hashes")
finally:
    run("start", "api", "worker")
