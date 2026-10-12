#!/usr/bin/env bash
# Remote development dependencies only. No services, model weights or datasets.
set -euo pipefail

if [[ "${AUVYLEN_REMOTE_DEV:-}" != "1" ]]; then
  echo "Refusing setup: confirm a remote Linux environment with AUVYLEN_REMOTE_DEV=1." >&2
  exit 1
fi
if [[ "$(uname -s)" != "Linux" ]] || grep -qi microsoft /proc/sys/kernel/osrelease; then
  echo "Refusing setup on Windows or WSL; use the remote cloud environment." >&2
  exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."
for tool in git uv node npm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing $tool; configure the cloud environment runtime before continuing." >&2
    exit 1
  fi
done
node -e 'if (Number(process.versions.node.split(".")[0]) !== 24) { console.error("Use Node.js 24 for the locked project baseline"); process.exit(1); }'

uv sync --locked
npm ci
npm exec --workspace @auvylen/web -- next typegen
echo "Locked development dependencies installed. No application services were started."
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "Docker Engine and Compose available; remote container checks can run when requested."
else
  echo "Docker unavailable. Infrastructure/browser verification requires another approved remote runner."
fi
