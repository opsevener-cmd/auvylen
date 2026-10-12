"""Audit the provisional rename without printing local env values or binary backups."""

import json
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/brand-rename.md"
GENERATED = {
    "node_modules",
    ".venv",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "test-results",
    "playwright-report",
}


def reason_for(path: str, line: str) -> str | None:
    if path.startswith("services/api/migrations/versions/"):
        return "Immutable migration history / original seed"
    if "aevyra-development:" in line:
        return "Scoring fixture bytes: changing them changes deterministic scores"
    if "aevyra-test-analysis" in line or "Aevyra Analysis" in line:
        return "Persisted product slug/name, presentation alias or compatibility assertion"
    if any(token in line for token in ("aevyra_api", "aevyra_inference", "aevyra_contracts")):
        return "Stable Python import/CLI namespace"
    if "AEVYRA_" in line:
        return "Existing environment interface retained without aliases"
    if "aevyra-phase2" in line or "aevyra-prod" in line or line == "name: aevyra\n":
        return "Compose project identity preserves volume/network names"
    if "aevyra_test_" in line:
        return "Existing isolated PostgreSQL test-schema namespace"
    if "aevyra-api" in line or "aevyra-web" in line or 'getLogger("aevyra' in line:
        return "Stable health/logging identity for monitoring compatibility"
    if path in {"services/api/src/aevyra_api/config.py", ".env.example", ".env.production.example"}:
        return "Existing database identity / development-password rejection guard"
    if "POSTGRES_" in line or "pg_isready" in line or "postgresql+psycopg://" in line:
        return "Existing database/user credentials or compatible setup example"
    if "`aevyra`" in line or "defaults aevyra" in line:
        return "Documented existing database/user identity"
    return None


def main() -> None:
    result = subprocess.run(
        [
            "rg",
            "--json",
            "--hidden",
            "--no-ignore",
            "-i",
            "aevyra",
            "-g",
            "!.git/**",
            "-g",
            "!backups/**",
            "-g",
            "!**/*.pyc",
            "-g",
            "!docs/brand-rename.md",
            "-g",
            "!scripts/audit-brand.py",
            ".",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError("Repository search failed")
    rows = []
    artifacts: Counter[str] = Counter()
    total = 0
    for raw in result.stdout.splitlines():
        event = json.loads(raw)
        if event["type"] != "match":
            continue
        data = event["data"]
        path = data["path"]["text"].replace("\\", "/").removeprefix("./")
        count = len(data["submatches"])
        total += count
        parts = Path(path).parts
        group = next((part for part in parts if part in GENERATED), None)
        if group:
            artifacts[group] += count
            continue
        if Path(path).name.startswith(".env") and not path.endswith(".example"):
            artifacts["ignored local environment files (values redacted)"] += count
            continue
        reason = reason_for(path, data["lines"]["text"])
        rows.append((path, data["line_number"], count, reason))
    unresolved = sum(count for _, _, count, reason in rows if reason is None)
    source_count = sum(count for _, _, count, _ in rows)
    text = """# Auvylen controlled rename audit

The previous brand, Aevyra, is replaced in visible branding and safe package/image labels.
This audit documents every remaining maintained-source occurrence by file/line. It also
scans ignored generated/dependency files, grouping their occurrences below. Env values
are never printed. Run `uv run python scripts/audit-brand.py` to refresh this report.

## Decisions and compatibility

- npm root/workspaces now use auvylen and @auvylen; Python distributions use auvylen-*.
  Python import directories remain aevyra_api/aevyra_inference/aevyra_contracts so existing
  imports, Uvicorn targets, migration imports and operator commands continue to work.
- Images use auvylen-api/auvylen-web. API container username changed; numeric UID 10001
  remains unchanged. Generic service names api/web/postgres/redis/proxy are unchanged.
- Compose project names aevyra/aevyra-prod/aevyra-phase2 are retained, preserving named
  volumes and existing container/network identities. Keep using the existing project name.
- Database/user names, original migration bytes, product slug aevyra-test-analysis,
  seeded product name Aevyra Analysis and public order prefix av_ are retained. Product
  responses translate the original display name to Auvylen Analysis without a DB write.
- Scoring fixture prefix aevyra-development: is unchanged: rebranding it would change
  synthetic scores for the same order. No scoring/payment/state-machine code was renamed.
- Health IDs and log namespaces stay stable for monitors. Environment prefixes AEVYRA_
  remain accepted unchanged; a provisional branding change does not justify env churn.
- No files/directories or physical checkout were moved. New VPS checkout examples use
  /opt/auvylen; existing checkouts need not move. Remote repository names were not changed.
- New backup filenames use auvylen-. Historical backups retain their original filenames
  and binary payloads; Git history, binary caches and backups are not rewritten. Installed
  dependencies/generated outputs may contain compatibility strings, historical caches and
  the old physical checkout path. They are not maintained branding sources.
- This report and the audit script intentionally mention the prior brand/identifiers to
  document and enforce these decisions; their self-references are excluded from the ledger.

## Cosmetic rename verification (historical)

Backend/infrastructure: 62 passed. Frontend unit tests: 15 passed. Ruff lint/format, mypy,
ESLint, TypeScript and frontend production build passed. Development browser checkout
passed with the new visible product name. See verification.md for deployment evidence.
The cosmetic rename changed no schema, payment architecture or scoring algorithm. Later
Phase 3 changes are documented separately in verification.md; this ledger audits names only.

## Remaining-reference ledger

"""
    text += f"Maintained-source occurrences: **{source_count}**. Must rename: **{unresolved}**.\n\n"
    text += "| File:line | Occurrences | Classification | Reason |\n| --- | ---: | --- | --- |\n"
    for path, number, count, reason in sorted(rows):
        label = "intentionally retained" if reason else "must rename"
        text += f"| {path}:{number} | {count} | {label} | {reason or 'Needs review'} |\n"
    text += "\n## Ignored/generated text matches\n\n"
    text += "| Group | Occurrences | Classification |\n| --- | ---: | --- |\n"
    for group, count in sorted(artifacts.items()):
        text += f"| {group} | {count} | intentionally retained compatibility/cache artifacts |\n"
    text += f"\nTotal scanned textual occurrences (excluding audit self-references): {total}.\n"
    REPORT.write_text(text, encoding="utf-8", newline="\n")
    print(
        f"Source: {source_count}; generated/local: {total - source_count}; "
        f"must rename: {unresolved}"
    )
    if unresolved:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
