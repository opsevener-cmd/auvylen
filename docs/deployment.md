# Auvylen deployment — Phase 2 foundation with Phase 3 accounts

Image names are now auvylen-web and auvylen-api. Rebuild before using the updated Compose
file. Compose project names and environment-variable names remain unchanged to reuse
existing PostgreSQL/TLS volumes and env files. Never switch the project name merely to
match the brand; that can create a fresh empty database volume. Existing checkouts need
not move; /opt/auvylen below is only the suggested path for new installations.
See [brand compatibility audit](brand-rename.md).

Single Ubuntu 24.04 VPS, provider-neutral Docker Compose, Caddy, Next.js, FastAPI,
PostgreSQL 18 and Redis 8. No public deployment has been performed. Production checkout
is deliberately unavailable: there is no real payment provider or production scoring engine.
Do not expose staging to the internet; its unauthenticated mock mutations are test-only.

## Clean VPS preparation

Use a maintained Ubuntu installation with SSH key access and enough disk for images,
PostgreSQL and backups. A small VPS can serve current traffic; image builds need more
memory than normal runtime. Keep SSH reachable before changing firewall rules.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git openssl python3
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

These commands follow [Docker's Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
Resolve conflicting preinstalled Docker packages as described there rather than blindly
removing server software. Compose >=2.24.4 is required for the local override. The Docker
socket and docker group confer root-equivalent access; commands below use sudo on the VPS.

Open **TCP 80 and 443**, plus your restricted SSH port. Do not open 3000, 8000, 5432,
6379 or Caddy's 2019 admin port. Configure the VPS/network firewall too: Docker published
ports may bypass uncomplicated host-firewall rules. Only Caddy publishes ports here.
HTTP/3 UDP is not enabled or required.

## Repository and environment

Replace REPOSITORY_URL with the actual repository and select a reviewed Git revision.

```bash
sudo mkdir -p /opt/auvylen
sudo chown "$USER":"$USER" /opt/auvylen
git clone REPOSITORY_URL /opt/auvylen
cd /opt/auvylen
cp .env.production.example .env.production
chmod 600 .env.production
python3 - <<'PY'
from pathlib import Path
import secrets
path = Path('.env.production')
password = secrets.token_hex(32)
text = path.read_text()
text = text.replace('POSTGRES_PASSWORD=\n', f'POSTGRES_PASSWORD={password}\n')
text = text.replace('DATABASE_URL=\n', f'DATABASE_URL=postgresql+psycopg://aevyra:{password}@postgres:5432/aevyra\n')
text = text.replace('REPLACE_WITH_SECURE_RANDOM_SECRET', secrets.token_hex(48))
path.write_text(text)
PY
nano .env.production
```

Set AEVYRA_DOMAIN to the chosen hostname only (no scheme, port, path or wildcard).
Leave APP_ENV=production and PAYMENT_PROVIDER=mock. Use a reviewed immutable release
identifier for IMAGE_TAG, e.g. the Git commit hash. Set CORS_ORIGINS to the exact browser
origin, e.g. ["https://your-domain.example"], even for same-origin account requests: CSRF
checks validate Origin. Back up REDEMPTION_CODE_PEPPER securely and separately before issuing
any codes. Changing it makes unused codes unredeemable. The mock notification signer uses
an ephemeral process-local key and is unreachable in production. Account sessions use
random opaque tokens with server-side digests; no JWT signing secret is needed.

Required deployment configuration:

| Variable | Responsibility |
| --- | --- |
| APP_ENV | production, staging or development; deployment default is production |
| AEVYRA_DOMAIN | Public hostname used by Caddy |
| DATABASE_URL | Explicit PostgreSQL psycopg URL; URL-encode credentials |
| POSTGRES_PASSWORD | Strong database password matching DATABASE_URL |
| POSTGRES_USER / POSTGRES_DB | PostgreSQL initialization, defaults aevyra |
| REDIS_URL | Explicit service URL; rediss:// for externally managed TLS Redis |
| API_URL | Internal web-to-API URL, default http://api:8000 |
| CORS_ORIGINS | Exact browser HTTPS origins; [] disables account POSTs |
| REDEMPTION_CODE_PEPPER | Required secure random HMAC secret; preserve/back up once issued |
| SESSION_COOKIE_SECURE | Enforced true in staging/production |
| SESSION_LIFETIME_SECONDS | Expiring session lifetime, default 86400 |
| PAYMENT_PROVIDER | mock only; production commercial routes still disabled |
| LOG_LEVEL | INFO, WARNING, ERROR or CRITICAL; deployment DEBUG rejected |
| IMAGE_TAG | Release identifier for locally built images |

Phase 3 requires a database backup and the matching pepper backup before changes. Preserve
the pepper across releases. Never include exports in images or public static directories.
Operator CSV generation inside a container requires a restricted exports directory bind mount;
there is no public generation endpoint. See redemption-codes.md for delivery checks.

Rollback after Phase 3 account/credit activity requires a compatible reviewed release or a
backup restore with an explicit data-loss plan. Do not casually downgrade or run an older
staging API: older analysis routes lack account-ownership checks. The new migration refuses
downgrade when accounts or issued batches exist. No automatic destructive migration/rollback occurs at startup.

APP_ENV supersedes legacy API_ENVIRONMENT. Never deploy the development .env file.
Deployment rejects missing connections, example/short database passwords, non-PostgreSQL
databases, wildcard CORS and debug logging. Containers receive only their required vars;
the web container never receives database credentials. Environment values are inspectable
by Docker administrators: restrict host access and protect the file. Avoid printing
`docker compose config` without `--quiet` or sharing container environment dumps.

## DNS and HTTPS

Point the hostname's A record at the VPS IPv4 address. Add AAAA only if IPv6 reaches this
VPS on both ports. Allow outbound DNS and HTTPS for certificate issuance/renewal. Caddy
uses public ACME issuers, persists certificates in caddy_data, and automatically redirects
HTTP to HTTPS. An explicit HTTP redirect also removes the Server header from redirects.
See [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).
Do not use the local TLS override on the VPS. No DNS-provider plugin is needed.

## First deployment

```bash
cd /opt/auvylen
sudo docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
sudo docker compose --env-file .env.production -f docker-compose.prod.yml build --pull
sudo docker compose --env-file .env.production -f docker-compose.prod.yml up -d --wait postgres redis
sudo docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps api alembic -c services/api/alembic.ini upgrade head
sudo docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps api alembic -c services/api/alembic.ini current
sudo docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps api alembic -c services/api/alembic.ini check
sudo docker compose --env-file .env.production -f docker-compose.prod.yml up -d --wait
sudo docker compose --env-file .env.production -f docker-compose.prod.yml ps
curl --fail https://YOUR_DOMAIN/health
curl --fail https://YOUR_DOMAIN/ready
curl --fail https://YOUR_DOMAIN/status
```

Replace YOUR_DOMAIN with the configured hostname. /health and /ready route directly to
FastAPI; /status is Next.js calling FastAPI internally. /api/* preserves its full path,
including /api/v1. Docker's API readiness check verifies database/cache connectivity;
it does not prove migration currency. Migrations are a separate reviewed step, never an
application startup hook. A fresh deployment should not publish the proxy before migrations.

Verify POST /api/v1/dev/payments/00000000-0000-0000-0000-000000000000/simulate-success
with body {} returns 404 in production. /api/v1/products, orders and results also return
404. The production home shows checkout unavailable and links to status instead of analysis.

## Operations and updates

```bash
sudo docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail 100 -f
sudo docker compose --env-file .env.production -f docker-compose.prod.yml restart api web
sudo docker compose --env-file .env.production -f docker-compose.prod.yml stop
sudo docker compose --env-file .env.production -f docker-compose.prod.yml up -d --wait
```

`down` removes containers/networks but retains named volumes. **Never use down -v on a
deployment you need to preserve.** Keep the Compose project name stable so updates reuse
the same volumes. Restart policies restart exited processes; unhealthy status alone does
not trigger a Docker restart. Investigate readiness/logs rather than assuming self-healing.

For updates, keep the previous Git revision, image tags and environment file securely.
Read migration code first. Plan maintenance for breaking schema changes; Phase 2 does not
promise zero downtime. Back up before every migration.

```bash
sudo bash scripts/backup-db.sh .env.production
git fetch origin
git checkout REVIEWED_RELEASE
# Edit IMAGE_TAG to a new release identifier in .env.production; preserve the old images.
sudo docker compose --env-file .env.production -f docker-compose.prod.yml build --pull
sudo docker compose --env-file .env.production -f docker-compose.prod.yml stop proxy web api
sudo docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps api alembic -c services/api/alembic.ini upgrade head
sudo docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps api alembic -c services/api/alembic.ini check
sudo docker compose --env-file .env.production -f docker-compose.prod.yml up -d --wait
```

If a step fails, leave public traffic stopped until resolved; do not blindly continue.
Roll back application images by restoring the previous checkout/tag/env and running
`up -d --wait --no-build`. This is safe only if the current schema is backward-compatible.
Never blindly Alembic downgrade a populated commercial database. For incompatible changes,
restore a verified backup to a fresh database during maintenance and point DATABASE_URL
at it. PostgreSQL major-version upgrades require a separately planned migration; changing
an image tag does not upgrade an existing volume safely. Refresh base images deliberately;
record image digests/release tags rather than relying on mutable tags for rollback.

## Backup and restore

```bash
sudo bash scripts/backup-db.sh .env.production
```

The script writes a private custom-format pg_dump under backups/ and renames it only
after successful completion. Failed .partial files are not backups. Copy backups encrypted
to a separate host/storage location, define retention, monitor success and practice restores.
Same-VPS copies alone do not protect against disk loss. Back up the protected env file and
release metadata separately. Redis currently holds no durable business state, so it uses
no persistence. Revisit before adding queues. Caddy volumes preserve TLS keys; protect them.

Restore into a new empty database rather than overwriting the live one:

```bash
sudo docker compose --env-file .env.production -f docker-compose.prod.yml stop proxy web api
sudo docker compose --env-file .env.production -f docker-compose.prod.yml exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" auvylen_restore'
sudo docker compose --env-file .env.production -f docker-compose.prod.yml exec -T postgres sh -c 'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d auvylen_restore' < backups/CHOSEN_BACKUP.dump
sudo docker compose --env-file .env.production -f docker-compose.prod.yml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d auvylen_restore -c "SELECT version_num FROM alembic_version"'
```

Then change DATABASE_URL's database component to auvylen_restore, use compatible application
images, run migration current/check, and start/check the stack. Preserve the original database
until recovery is validated. Test business-row counts as well as schema. pg_dump is a consistent
database snapshot, not continuous point-in-time recovery; schedule according to your acceptable
data-loss window. Never pipe binary dumps through Windows PowerShell text redirection.

## Local production and staging simulation

Copy .env.production.example to .env.production.local (ignored), generate a private random
password and matching DATABASE_URL as above, and set AEVYRA_DOMAIN=localhost. Use a separate
Compose project from development; its PostgreSQL volume is independent. No ports conflict
with the Phase 1 host processes. Linux commands (omit sudo if Docker access is configured):

```bash
docker compose --env-file .env.production.local -p aevyra-phase2 -f docker-compose.prod.yml -f docker-compose.prod.local.yml build
docker compose --env-file .env.production.local -p aevyra-phase2 -f docker-compose.prod.yml -f docker-compose.prod.local.yml up -d --wait postgres redis
docker compose --env-file .env.production.local -p aevyra-phase2 -f docker-compose.prod.yml -f docker-compose.prod.local.yml run --rm --no-deps api alembic -c services/api/alembic.ini upgrade head
docker compose --env-file .env.production.local -p aevyra-phase2 -f docker-compose.prod.yml -f docker-compose.prod.local.yml up -d --wait
curl -k --fail https://localhost:8443/ready
curl -I http://localhost:8080/
```

The loopback-only override uses Caddy's private local CA. `-k` is allowed only for this
simulation, never public deployment verification. HTTP redirects to HTTPS on standard
443; use https://localhost:8443 explicitly with the local remapped ports. No system trust
store changes are needed. To test staging, set APP_ENV=staging in this local env file and
rerun `up -d --wait`; images are identical. Run the home-to-result mock browser flow on
https://localhost:8443. Switch APP_ENV back to production and verify all commercial API
calls are rejected. Named volumes persist across this change. Browser test command:

```bash
AEVYRA_TEST_URL=https://localhost:8443 PLAYWRIGHT_CHANNEL=chrome npm exec --workspace @auvylen/web -- playwright test --config playwright.deployment.config.ts
```

Install Chromium with Playwright if Chrome is unavailable and omit PLAYWRIGHT_CHANNEL.
Run with APP_ENV=staging for the test. For production lockdown, set APP_ENV=production,
rerun Compose up, then add AEVYRA_TEST_MODE=production to the browser command. Each mode
runs its own assertions and skips the inapplicable flow. In PowerShell set those variables
using `$env:VARIABLE='value'` before the same npm command. See verification.md for results.

## Later infrastructure moves — not implemented

Change API_URL, DATABASE_URL and REDIS_URL to move service locations; use private networking,
TLS and managed-service credentials. Remove unused local dependency services/depends_on
when moving databases. Do not expose internal Docker ports to compensate. Inference is
still a package within the API, ready for a later service/worker boundary. A static frontend
move requires replacing current server actions, not merely copying build files. No vendor
SDK, object storage, GPU infrastructure or mainland-China deployment is configured.

Application fonts/styles/scripts are self-hosted or system fonts. No external frontend
runtime asset dependency exists. Public TLS still depends on DNS and ACME authorities;
builds depend on package/image registries. Mirror registries if needed without changing
business logic. No ICP filing process is implemented. Before public deployment provide the
VPS address/SSH access, final hostname/DNS control, selected release, and backup destination.
# Phase 4A cloud extension

For the current worker/private-storage/migration-gate deployment, use
[Phase 4A cloud instructions](phase4a.md) and [cloud backup/restore](cloud-backups.md).
The original single-VPS deployment procedure below remains valid for the preserved base
stack. Production is hosted on a future Ubuntu VPS, never on the user's Windows computer;
no server is presently provisioned. Do not use the local TLS or tunnel override publicly.
