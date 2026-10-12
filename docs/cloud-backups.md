# Cloud backups and restoration

Back up PostgreSQL, private uploads, checkpoints and the protected environment/pepper.
The latter belongs in separately encrypted off-host storage. An artifact archive alone
cannot recover accounts, ownership, jobs, Credits or unused redemption lookups. Redis
contains no job truth; rebuilding it resets recent rate-limit counters. AOF persists it
across normal restarts, but it is not a replacement for PostgreSQL backups.

On Linux from the repository root, with the same COMPOSE_PROJECT_NAME as deployment:

```bash
bash scripts/backup-cloud.sh .env.cloud backups/pre-upgrade
```

The script pauses running API/workers for a consistent database/artifact snapshot and
resumes them on exit, including failure. It writes `database.dump` and
`artifacts.tar.gz` with restricted directory/file permissions. Take this backup before
setting APPLY_MIGRATIONS=true for an upgrade. Copy it to encrypted off-host storage,
record the source commit/image tag and test restoration regularly. Exported redemption
CSV files need their own protected operator backup; they are intentionally absent from
application images and artifact volumes. Do not publish backup paths or archive contents.

Only a successful backup with `SHA256SUMS` is complete. Partial files from a failed run
are not restoration candidates. Before restoration, run `sha256sum -c SHA256SUMS` in
the backup directory. Protect that manifest alongside the archive and database dump.

Restore into a fresh, isolated Compose project first. Do not overwrite a live database.
Create a matching protected env file with the backed-up pepper and suitable DB
credentials. Keep APPLICATION services stopped; do not run automatic migrations before
restoring a database already containing its Alembic revision. Example Linux commands:

```bash
export COMPOSE_PROJECT_NAME=auvylen-restore-test
docker compose --env-file .env.restore -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d --wait postgres redis
docker compose --env-file .env.restore -f docker-compose.prod.yml -f docker-compose.cloud.yml exec -T postgres sh -c 'exec pg_restore --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backups/pre-upgrade/database.dump
docker compose --env-file .env.restore -f docker-compose.prod.yml -f docker-compose.cloud.yml run --rm --no-deps --user 0 --cap-add DAC_OVERRIDE --cap-add CHOWN --volume "$PWD/backups/pre-upgrade:/backup:ro" --volume auvylen-restore-test_private_models:/var/lib/auvylen/models api python -c "import os,tarfile; from pathlib import Path; t=tarfile.open('/backup/artifacts.tar.gz'); t.extractall('/var/lib/auvylen',filter='data'); t.close(); roots=[Path('/var/lib/auvylen/uploads'),Path('/var/lib/auvylen/models')]; [os.chown(p,10001,10001,follow_symlinks=False) for r in roots for p in [r,*r.rglob('*')]]"
docker compose --env-file .env.restore -f docker-compose.prod.yml -f docker-compose.cloud.yml run --rm --no-deps api alembic -c services/api/alembic.ini current
docker compose --env-file .env.restore -f docker-compose.prod.yml -f docker-compose.cloud.yml run --rm --no-deps api alembic -c services/api/alembic.ini check
```

The offline backup/restore utility explicitly grants DAC_OVERRIDE/CHOWN so it can read
UID 10001 private files and preserve ownership; normal application containers keep all
capabilities dropped. The explicit model-volume mount replaces the API's normally read-only model mount for
this offline restoration only. Use only your trusted backup archive. Retain UID/GID
10001 permissions on private directories; API/workers normally remain non-root.
After verification, authorize the migration gate and start the isolated application.
For browser verification, add the documented local override rather than expose the
restore project publicly. Inspect balances, redemption digests, job history and artifact
hashes; do not print codes or secrets.

Rollback: stop API/workers, choose the last verified image/source release, and determine
schema compatibility. Do not automatically downgrade issued-credit tables. If an old
release cannot read the new additive schema, restore the matched snapshot into a new
database/volume set and switch configuration after verification. Restoration loses
changes since the backup; plan downtime and communicate it. No destructive rollback
has been executed against the existing development database.
