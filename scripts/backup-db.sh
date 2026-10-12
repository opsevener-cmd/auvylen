#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
env_file="${1:-.env.production}"
backup_dir="${2:-backups}"
mkdir -p "$backup_dir"
backup_path="$backup_dir/auvylen-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
# Redirect on Linux, never through Windows PowerShell's text pipeline.
docker compose --env-file "$env_file" -f docker-compose.prod.yml exec -T postgres \
  sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_path.partial"
test -s "$backup_path.partial"
mv -- "$backup_path.partial" "$backup_path"
printf 'Backup saved: %s\n' "$backup_path"
