# Restore the Codespace backup onto the production VPS

Copy-paste procedure for the VPS operator, run **as root** in `/opt/auvylen`. It moves a
`scripts/codespaces-preview.py backup` archive (`database.dump`, `credentials.json`,
`uploads/`, `models/`, GPG-encrypted) onto the `docker-compose.prod.yml` deployment.
Secrets are typed at prompts or read from files; no command prints them. Never paste a
password, passphrase or pepper into chat, Git or a shell history.

Assumptions: Docker CE with the Compose plugin, the repository at `/opt/auvylen`, a working
`.env.production` (mode 600) and `https://auvylen.duckdns.org` already serving the empty
production stack. The current production database is empty and disposable. Steps 6–8
replace it; check step 5's output before continuing.

## 0. Session setup (every new root shell)

```bash
export APP_DIR=/opt/auvylen
export RESTORE_DIR=/root/auvylen-restore
cd "$APP_DIR"
dc() { docker compose --env-file .env.production -f docker-compose.prod.yml --profile research "$@"; }
```

## 1. Release, research mode and images

Use the reviewed commit of `main` that contains this guide.

```bash
git fetch origin
git checkout --detach REVIEWED_COMMIT
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$(git rev-parse --short=12 HEAD)/" .env.production
# Research features and the worker need RESEARCH_MODE=true (the Codespace ran with it).
grep -q '^RESEARCH_MODE=' .env.production \
  && sed -i 's/^RESEARCH_MODE=.*/RESEARCH_MODE=true/' .env.production \
  || echo 'RESEARCH_MODE=true' >> .env.production
grep -q '^ENABLED_MODEL_PROVIDERS=' .env.production || echo 'ENABLED_MODEL_PROVIDERS=[]' >> .env.production
chmod 600 .env.production
dc config --quiet && echo "compose config ok"
dc build --pull
```

The build needs memory; keep the 4 GB swap enabled.

## 2. Copy the backup onto the VPS

From the computer that holds the backup (PowerShell's built-in OpenSSH works), copy
the archive and its `.sha256` to your sudo user, then move them into a root-only folder:

```powershell
scp BACKUP.tar.gz.gpg BACKUP.tar.gz.gpg.sha256 auvylen@43.155.131.145:/tmp/
```

```bash
install -d -m 700 "$RESTORE_DIR"
mv /tmp/BACKUP.tar.gz.gpg /tmp/BACKUP.tar.gz.gpg.sha256 "$RESTORE_DIR"/
chmod 600 "$RESTORE_DIR"/BACKUP.tar.gz.gpg*
export BACKUP="$RESTORE_DIR/BACKUP.tar.gz.gpg"
```

## 3. Verify and decrypt

```bash
(cd "$RESTORE_DIR" && sha256sum -c "$(basename "$BACKUP").sha256")
command -v gpg >/dev/null || apt-get install -y gnupg
install -d -m 700 "$RESTORE_DIR/work"
# Prompts for the Codespace backup passphrase.
gpg --pinentry-mode loopback --decrypt --output "$RESTORE_DIR/work/backup.tar.gz" "$BACKUP"
tar --no-same-owner -xzf "$RESTORE_DIR/work/backup.tar.gz" -C "$RESTORE_DIR/work"
ls "$RESTORE_DIR/work"   # expect: backup.tar.gz credentials.json database.dump models uploads
test -f "$RESTORE_DIR/work/models/pretrained/mobilenetv3-small-100-lamb-embedding-v1.onnx" \
  && echo "reviewed encoder present"
```

## 4. Redemption pepper from `credentials.json`

The restored redemption codes only work with the Codespace's pepper. The database
password is **not** copied; production keeps its own.

```bash
cp -p .env.production "$RESTORE_DIR/env.before-restore"
python3 - "$RESTORE_DIR/work/credentials.json" "$APP_DIR/.env.production" <<'PY'
import json, re, sys
from pathlib import Path
pepper = json.loads(Path(sys.argv[1]).read_text())["pepper"]
assert re.fullmatch(r"[0-9a-f]{96}", pepper), "unexpected pepper format"
env = Path(sys.argv[2])
text, count = re.subn(r"(?m)^REDEMPTION_CODE_PEPPER=.*$", "REDEMPTION_CODE_PEPPER=" + pepper, env.read_text())
assert count == 1, "REDEMPTION_CODE_PEPPER line not found exactly once"
env.write_text(text)
print("pepper updated")
PY
chmod 600 .env.production
```

Store the same pepper in your password manager if it is not already there.

## 5. Stop the application and confirm the database is disposable

```bash
dc stop proxy web api worker
dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' <<'SQL'
SELECT 'tables=' || count(*) FROM information_schema.tables WHERE table_schema = 'public';
SELECT 'users=' || (xpath('/row/c/text()', query_to_xml('SELECT count(*) AS c FROM users', false, true, '')))[1]::text
WHERE to_regclass('public.users') IS NOT NULL;
SQL
```

Continue only if there is no `users=` line or it says `users=0`. Otherwise stop: that
database holds data, and this guide would delete it.

## 6. Replace the empty database with the Codespace dump

```bash
dc exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" --force "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
dc exec -T postgres sh -c 'pg_restore --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < "$RESTORE_DIR/work/database.dump"
```

## 7. Copy uploads and models into the private volume (UID 10001)

The `auvylen_private` volume is mounted at `/var/lib/auvylen` in the API and worker only.
This one-off root container refuses to overwrite non-empty folders.

```bash
dc run --rm --no-deps -T --user 0 --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER \
  --volume "$RESTORE_DIR/work:/restore:ro" api sh -c '
set -e
for d in uploads models; do
  if [ -n "$(ls -A /var/lib/auvylen/$d)" ]; then echo "/var/lib/auvylen/$d is not empty; stopping"; exit 1; fi
  cp -a /restore/$d/. /var/lib/auvylen/$d/
done
chown -R 10001:10001 /var/lib/auvylen
chmod 700 /var/lib/auvylen /var/lib/auvylen/uploads /var/lib/auvylen/models
echo "uploads files: $(find /var/lib/auvylen/uploads -type f | wc -l)"
echo "models files: $(find /var/lib/auvylen/models -type f | wc -l)"'
```

## 8. Migrate and check the schema

The Codespace database may be at an older revision; `upgrade head` applies the rest.

```bash
dc run --rm --no-deps api alembic -c services/api/alembic.ini upgrade head
dc run --rm --no-deps api alembic -c services/api/alembic.ini current
dc run --rm --no-deps api alembic -c services/api/alembic.ini check
```

`current` must end with `(head)`; `check` must say `No new upgrade operations detected.`

## 9. Confirm the reviewed ONNX encoder is the one in use

```bash
dc run --rm --no-deps -T api python -c "import os; from pathlib import Path; from aevyra_inference.extractors import MOBILENET, availability; print(availability(MOBILENET, Path(os.environ['PRIVATE_MODEL_ROOT']) / 'pretrained'))"
```

Expect `(True, 'Verified pretrained checkpoint installed')`. The file's SHA-256 is checked
against the reviewed graph `164c4816…eedd2a6`. Anything else means the encoder is missing
or altered, and MobileNet personal models will report unavailable.

## 10. Start and verify

```bash
dc up -d --wait
dc ps
curl -fsS https://auvylen.duckdns.org/health && echo
curl -fsS https://auvylen.duckdns.org/ready && echo
curl -fsS -o /dev/null -w "status page %{http_code}\n" https://auvylen.duckdns.org/status
# Restored data, counts only:
dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT '"'"'users='"'"' || count(*) FROM users; SELECT '"'"'owners='"'"' || count(*) FROM users WHERE role = '"'"'owner'"'"'"'
# Pepper matches the backup (prints short fingerprints only):
python3 -c "import json,hashlib,sys; print('backup', hashlib.sha256(json.load(open(sys.argv[1]))['pepper'].encode()).hexdigest()[:12])" "$RESTORE_DIR/work/credentials.json"
dc exec -T api python -c "import os,hashlib; print('live  ', hashlib.sha256(os.environ['REDEMPTION_CODE_PEPPER'].encode()).hexdigest()[:12])"
# Only 22, 80 and 443 listen publicly:
ss -tlnp | awk 'NR==1 || $4 !~ /^(127\.0\.0\.1|\[::1\]):/'
```

Then sign in at `https://auvylen.duckdns.org` as `owner_god` with the **Codespace** Owner
password, open the Owner dashboard and an existing personal research dataset/model, and
confirm photos load.

Once everything is verified, delete the decrypted plaintext (database dump and pepper) and
keep only the encrypted archive in private storage:

```bash
rm -rf "$RESTORE_DIR/work" "$RESTORE_DIR/env.before-restore"
```

## Owner password: rotate or recover

The Owner CLI runs only in an interactive terminal. On the VPS, opt in for that one
command; the variable is never set in Compose or env files.

```bash
# Change the password (asks for the current one):
dc exec -it -e AUVYLEN_OWNER_TERMINAL=deployment api python -m aevyra_api.owner rotate
# Forgotten password: revokes all sessions, asks you to type RECOVER <owner public id>:
dc exec -it -e AUVYLEN_OWNER_TERMINAL=deployment api python -m aevyra_api.owner recover
# Fresh database without an Owner only:
dc exec -it -e AUVYLEN_OWNER_TERMINAL=deployment api python -m aevyra_api.owner init
```

Sessions older than `OWNER_FRESH_AUTH_SECONDS` (default 10 minutes) must sign in again
before Owner-only actions.

## Update procedure

The live VPS runs from `/opt/auvylen-b` under the Compose project name `auvylen-b`.
`docker-compose.prod.yml` declares `name: aevyra-prod`, so **always** select the project
explicitly; `COMPOSE_PROJECT_NAME` also makes `scripts/backup-prod.sh` target it. Without
it, Compose would address an empty `aevyra-prod` project instead of the running stack.

```bash
export APP_DIR=/opt/auvylen-b
export COMPOSE_PROJECT_NAME=auvylen-b
cd "$APP_DIR"
dc() { docker compose --env-file .env.production -p auvylen-b -f docker-compose.prod.yml --profile research "$@"; }
# 1. Encrypted backup first (see below).
BACKUP_PASSPHRASE_FILE=/root/.auvylen-backup-passphrase scripts/backup-prod.sh
# 2. New reviewed release.
git fetch origin
git checkout --detach REVIEWED_COMMIT
sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$(git rev-parse --short=12 HEAD)/" .env.production
dc config --quiet && dc build --pull
# 3. Stop public traffic and jobs, migrate, check, start.
dc stop proxy web api worker
dc run --rm --no-deps api alembic -c services/api/alembic.ini upgrade head
dc run --rm --no-deps api alembic -c services/api/alembic.ini check
dc up -d --wait
curl -fsS https://auvylen.duckdns.org/ready && echo
```

Every service has a `mem_limit` (web 384m, api 512m, worker 512m, postgres 512m, redis 256m,
proxy 128m; about 2.3 GB in total on the 4 GB host; see [memory-budget.md](memory-budget.md)) and PostgreSQL starts with
`shared_buffers=128MB`, `effective_cache_size=1GB` and `max_connections=50`. Changing
these settings recreates the containers on `dc up`, including a short PostgreSQL restart;
the data volume is kept. Check memory after an update:

```bash
docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}'; free -h
dc exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SHOW shared_buffers; SHOW max_connections"'
```

If a container shows `OOMKilled` (`docker inspect --format '{{.State.OOMKilled}}' auvylen-b-worker-1`),
raise that service's `mem_limit` in a reviewed change rather than removing it.

If a step fails, leave traffic stopped. Roll back by checking out the previous commit,
restoring its `IMAGE_TAG` and running `dc up -d --wait --no-build`. That is safe only when
the schema did not change incompatibly. Otherwise restore the backup taken in step 1 into a
fresh database. Never `docker compose down -v`: it deletes the database and private volumes.

## Daily encrypted backups

`scripts/backup-prod.sh` pauses the API and worker for a consistent snapshot (a few
seconds), dumps PostgreSQL and archives `uploads/` and `models/`. It adds `.env.production`
(pepper and database password) and encrypts the whole archive with GPG. Archives older
than 14 days are pruned (`BACKUP_RETENTION_DAYS`).

Choose one encryption method:

- **Recommended: public key.** Generate a GPG key pair on a trusted machine, import only the
  public key on the VPS (`gpg --import auvylen-backup.pub`), and set
  `BACKUP_GPG_RECIPIENT=<fingerprint>`. The server cannot decrypt its own backups.
- **Simpler: passphrase file.** Create it without echoing, and store the same passphrase in
  your password manager. Anyone with root on the VPS can read this file.

```bash
read -rs -p "Backup passphrase: " p && printf '%s' "$p" > /root/.auvylen-backup-passphrase && unset p && echo
chmod 600 /root/.auvylen-backup-passphrase
```

Run one backup by hand, then schedule it daily at 03:17 UTC:

```bash
BACKUP_PASSPHRASE_FILE=/root/.auvylen-backup-passphrase /opt/auvylen/scripts/backup-prod.sh
cat > /etc/cron.d/auvylen-backup <<'EOF'
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
17 3 * * * root BACKUP_PASSPHRASE_FILE=/root/.auvylen-backup-passphrase /opt/auvylen/scripts/backup-prod.sh >> /var/log/auvylen-backup.log 2>&1
EOF
chmod 644 /etc/cron.d/auvylen-backup
```

With a public key, replace `BACKUP_PASSPHRASE_FILE=…` with `BACKUP_GPG_RECIPIENT=<fingerprint>`.
Archives land in `/var/backups/auvylen/`. **Copy them off the server** (for example with
`scp` from your computer); a same-disk copy does not survive losing the VPS. Test a
restore regularly. To restore one, decrypt it, then follow steps 5–10 with
`database.dump`, `private.tar` (extract it to get `uploads/` and `models/`) and the
included `env` (its pepper and database password).

## Features that `APP_ENV=production` disables

| Feature | Production behaviour |
| --- | --- |
| Native 1–7 Owner research preview | Refused at startup if enabled; allowed only in `development`/`test` |
| Synthetic `/analyze` credit analysis and mock research jobs | Return 404 |
| Mock checkout / development payment routes | Off |
| API documentation (`/docs`) | Hidden |
| Phase 6 aesthetic scoring | Off until a validated, pinned checkpoint passes its release gate |

The web app also hides unfinished pages in production. They are absent from navigation and
links and answer **404** (not an "unavailable" page): `/research/aesthetic`,
`/research/native-preview`, `/analyze`, `/history`, `/result/…` and `/checkout/…`.
`/redeem` redirects to the Account page, whose **Credits** section holds the balance,
redemption form and credit history. Set `PREVIEW_FEATURES_ENABLED=true` in
`.env.production` to show the two research previews again (their API gates still apply);
synthetic analysis and mock checkout can never be shown in production.

Personal preference research (datasets, ratings, MobileNet/handcrafted models, prediction),
Owner administration, accounts, Credits and redemption all work in production with
`RESEARCH_MODE=true`. The Codespace ran `APP_ENV=staging`, where the same restrictions
apply except that synthetic analysis is available.
