#!/usr/bin/env bash
# Encrypted, consistent backup of the docker-compose.prod.yml deployment.
#
# Usage (as root, from the repository): scripts/backup-prod.sh [ENV_FILE] [DESTINATION]
#   ENV_FILE     default .env.production
#   DESTINATION  default /var/backups/auvylen
# Encryption (one of, never both):
#   BACKUP_GPG_RECIPIENT  public key ID/fingerprint in root's keyring (private key off-host)
#   BACKUP_PASSPHRASE_FILE  root-only (0600) file holding a symmetric passphrase
# BACKUP_RETENTION_DAYS (default 14) prunes older local archives.
#
# The archive holds database.dump, uploads/, models/ and the env file (database password
# and redemption pepper), so it is only ever written encrypted. API and worker pause for
# the snapshot and resume on exit, including failure. Nothing secret is printed.
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
env_file="${1:-.env.production}"
destination="${2:-/var/backups/auvylen}"
retention="${BACKUP_RETENTION_DAYS:-14}"
[[ -f "$env_file" ]] || { echo "Missing $env_file" >&2; exit 1; }
if [[ -n "${BACKUP_GPG_RECIPIENT:-}" && -n "${BACKUP_PASSPHRASE_FILE:-}" ]]; then
  echo "Set BACKUP_GPG_RECIPIENT or BACKUP_PASSPHRASE_FILE, not both" >&2; exit 1
fi
if [[ -n "${BACKUP_PASSPHRASE_FILE:-}" ]]; then
  [[ -f "$BACKUP_PASSPHRASE_FILE" && "$(stat -c %a "$BACKUP_PASSPHRASE_FILE")" == 600 ]] \
    || { echo "Passphrase file must exist with mode 600" >&2; exit 1; }
elif [[ -z "${BACKUP_GPG_RECIPIENT:-}" ]]; then
  echo "Set BACKUP_GPG_RECIPIENT or BACKUP_PASSPHRASE_FILE; refusing an unencrypted backup" >&2
  exit 1
fi
compose=(docker compose --env-file "$env_file" -f docker-compose.prod.yml --profile research)
mkdir -p "$destination"
chmod 700 "$destination"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
work="$(mktemp -d "$destination/.work-$stamp-XXXX")"
paused=()
cleanup() {
  if ((${#paused[@]})); then "${compose[@]}" start "${paused[@]}" >/dev/null; fi
  rm -rf -- "$work"
}
trap cleanup EXIT
while IFS= read -r service; do
  if [[ "$service" == api || "$service" == worker ]]; then paused+=("$service"); fi
done < <("${compose[@]}" ps --services --status running)
if ((${#paused[@]})); then "${compose[@]}" stop "${paused[@]}" >/dev/null; fi
"${compose[@]}" exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$work/database.dump"
test -s "$work/database.dump"
"${compose[@]}" run --rm --no-deps -T --user 0 --cap-add DAC_OVERRIDE \
  --volume "$work:/backup" api sh -c \
  'tar -C /var/lib/auvylen -cf /backup/private.tar uploads models && chown "$1:$2" /backup/private.tar' \
  sh "$(id -u)" "$(id -g)"
cp -- "$env_file" "$work/env"
git rev-parse HEAD > "$work/commit" 2>/dev/null || echo unknown > "$work/commit"
tar -C "$work" -czf "$work/backup.tar.gz" database.dump private.tar env commit
output="$destination/auvylen-$stamp.tar.gz.gpg"
if [[ -n "${BACKUP_GPG_RECIPIENT:-}" ]]; then
  gpg --batch --yes --trust-model always --encrypt --recipient "$BACKUP_GPG_RECIPIENT" \
    --output "$output.partial" "$work/backup.tar.gz"
else
  gpg --batch --yes --pinentry-mode loopback --passphrase-file "$BACKUP_PASSPHRASE_FILE" \
    --symmetric --cipher-algo AES256 --output "$output.partial" "$work/backup.tar.gz"
fi
mv -- "$output.partial" "$output"
(cd "$destination" && sha256sum "$(basename "$output")" > "$(basename "$output").sha256")
find "$destination" -maxdepth 1 -name 'auvylen-*.tar.gz.gpg*' -mtime +"$retention" -delete
echo "Encrypted backup written: $output"
echo "Copy it off this server; a same-disk copy does not survive disk loss."
