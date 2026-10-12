#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
env_file="${1:-.env.cloud}"
destination="${2:-backups/cloud-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$destination"
destination="$(cd "$destination" && pwd)"
compose=(docker compose --env-file "$env_file" -f docker-compose.prod.yml -f docker-compose.cloud.yml --profile research)
paused=()
while IFS= read -r service; do
  if [[ "$service" == api || "$service" == worker ]]; then paused+=("$service"); fi
done < <("${compose[@]}" ps --services --status running)
resume() { if ((${#paused[@]})); then "${compose[@]}" start "${paused[@]}"; fi; }
trap resume EXIT
if ((${#paused[@]})); then "${compose[@]}" stop "${paused[@]}"; fi
"${compose[@]}" exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$destination/database.dump.partial"
test -s "$destination/database.dump.partial"
mv -- "$destination/database.dump.partial" "$destination/database.dump"
"${compose[@]}" run --rm --no-deps --user 0 --cap-add DAC_OVERRIDE --cap-add CHOWN --volume "$destination:/backup" api python -c \
  "import os,sys,tarfile; os.umask(0o077); t=tarfile.open('/backup/artifacts.tar.gz.partial','w:gz'); t.add('/var/lib/auvylen/uploads',arcname='uploads'); t.add('/var/lib/auvylen/models',arcname='models'); t.close(); os.chown('/backup/artifacts.tar.gz.partial',int(sys.argv[1]),int(sys.argv[2]))" "$(id -u)" "$(id -g)"
mv -- "$destination/artifacts.tar.gz.partial" "$destination/artifacts.tar.gz"
(cd "$destination" && sha256sum database.dump artifacts.tar.gz > SHA256SUMS)
printf 'Consistent database/artifact backup: %s\nBack up the environment and redemption pepper separately in encrypted storage.\n' "$destination"
