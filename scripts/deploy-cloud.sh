#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
env_file="${1:-.env.cloud}"
compose=(docker compose --env-file "$env_file" -f docker-compose.prod.yml -f docker-compose.cloud.yml)
# Opt-in worker follows explicit operator selection, never host GPU autodetection.
if [[ "${RESEARCH_WORKER:-false}" == true ]]; then compose+=(--profile research); fi
"${compose[@]}" config --quiet
"${compose[@]}" stop api worker web proxy
"${compose[@]}" up -d --wait postgres redis
# Always recreate the gate on updates, including when only migration files changed.
"${compose[@]}" rm -f migrate
"${compose[@]}" up -d --wait
