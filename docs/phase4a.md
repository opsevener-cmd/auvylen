# Phase 4A: cloud-ready recovery and research foundation

The production website and inference workers belong on a future Linux cloud host.
The user's Windows computer is used only for disposable development verification.
No VPS, public hostname, remote deployment or tunnel account exists as part of this work.

## Repository audit

The repository was present and continued in place. At audit, Git had no commits and all
application files were untracked on `codex/cloud-custom-scoring`. Work continues on
`codex/phase4a-cloud-ready`; no history was reset or files replaced wholesale. Commit and
back up the reviewed source before provisioning a server. Never add ignored env files,
exports, backups or private artifacts to that commit.

Confirmed in source and tests:

| Component | Evidence | Initial limitation |
| --- | --- | --- |
| Next.js/TypeScript | apps/web; locked npm workspace | Interrupted pilot edits existed |
| FastAPI | services/api; modular routers and structured logs | No asynchronous worker |
| PostgreSQL/SQLAlchemy | commercial and credit models; Alembic 0001–0003 | No research jobs |
| Redis | connectivity/readiness; atomic authentication/redemption rate limits | Production cache was disposable |
| Caddy/Compose | production HTTPS proxy; non-root application images | No private image/checkpoint volumes |
| Accounts | Argon2id; hashed server sessions; exact-Origin and CSRF checks | No research authorization grant |
| Credits/redemption | append-only ledger, locks, HMAC codes, operator CSV | Preserved without changing financial logic |
| Mock analysis | policy-gated registry; deterministic synthetic results | Only a synthetic fixture, no facial inference |
| Payments | order/event/provider abstractions and adapter scaffolds | Not prioritized or connected to real providers |

The incomplete `docker-compose.pilot.yml` and public-origin safeguards are retained for
compatibility, but are not the cloud deployment path. Windows tunnel hosting is not a
production requirement. Several older architecture paragraphs were stale about Redis
rate limiting; current responsibilities are clarified below.

## Implemented architecture

Python, Node and uv build images and cloud PostgreSQL/Redis/Caddy inputs are pinned by
image digest; npm and Python dependencies use locked installs. Record release image
digests and review/update these pins for security fixes, rebuilding and retesting before
deployment. Pins make inputs reproducible; they do not remove dependency maintenance.

Internet → Caddy HTTPS → Next.js / FastAPI → private PostgreSQL / Redis.
An optional non-root CPU worker consumes PostgreSQL research jobs. PostgreSQL owns the
queue and result history; Redis AOF preserves rate-limit state, not financial/job truth.
Private upload and model volumes are never mounted in the web or proxy containers.
The API has read-only model access; workers can persist checkpoints. Upload HTTP and
model download routes remain absent. The blob storage primitive is not an image decoder
or a consent system, and does not enable public image import.

The cloud override adds a serialized migration service. `APPLY_MIGRATIONS=true` is an
explicit review/backup authorization. An unsuccessful migration prevents fresh API and
worker startup via `service_completed_successfully`. A PostgreSQL advisory lock prevents
concurrent migrators. Upgrade and drift check must both succeed. No migration is hidden
in application startup, and no old migration is rewritten. On updates, stop the old API
and worker first: Compose cannot retroactively stop an already-running old application
when a new migration fails. The deployment helper below does so.

New migration `0004_research` adds only `research_access` and `research_jobs`. Existing
accounts, wallets, codes, analyses and payments are unchanged. Research results have
their own job record and never invent an Analysis debit or refund.

## Disposable development simulation (Linux or Windows)

The full file manifest and verified results are in [the completion report](phase4a-report.md).

Requirements: Docker Engine/Compose >=2.24.4 (Docker Desktop on Windows), Node 24,
Python 3.12–3.14, uv. All repository paths are relative and portable.
On Windows, add the existing Docker CLI directory to your terminal PATH if necessary;
no firewall, antivirus, router or OS security changes are needed.

From the repository root, create the ignored local env exactly once:

```bash
uv sync --locked
uv run python scripts/create-cloud-test-env.py
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research build
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research up -d --wait
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research ps -a
```

Only `127.0.0.1:18080` and `127.0.0.1:18443` are published in this disposable override.

On this Windows checkout, an ignored `.env.cloud.local` is already generated; do not
regenerate it. The verified host environment is `.venv-phase4a`; in PowerShell use
`$env:UV_PROJECT_ENVIRONMENT='.venv-phase4a'` for uv commands if the older default
launcher is blocked. Use `uv run python -m mypy` instead of a blocked generated launcher.
On a fresh Linux checkout, the standard commands above work without Windows paths.
Browse `https://localhost:18443`; Caddy uses a local test certificate. Accept it only for
this local simulation. `http://localhost:18080` redirects to HTTPS and is not the account
test origin. Check `https://localhost:18443/health` and `/ready`. Session cookies are
Secure/HttpOnly/SameSite=Lax; use HTTPS for account testing.

Register through `/register`; copy your own `public_user_id` from the authenticated
`GET /api/v1/auth/me` response. Then grant access locally:

```bash
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research exec api python -m aevyra_api.research.operator grant usr_YOUR_PUBLIC_ID --reason "Authorized local research pilot"
```

Open `/research` and run Synthetic Research Analysis. Submission returns 202, the worker
saves an explicitly synthetic result, and `/account` shows the same Credit balance.
The four third-party models and custom trainer display unavailable. Grant/revoke is CLI
only. Anonymous users cannot submit; other users cannot read the job. The existing
redemption and credit-funded Mock Analysis still work through `/redeem` and `/analyze`
in this staging simulation. Cloud mock checkout is disabled in both API and web;
private development Compose retains the old commercial tests.

```bash
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research logs --tail 100 api worker migrate
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research restart api worker postgres redis
docker compose --env-file .env.cloud.local -p auvylen-phase4a-test -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.cloud.local.yml --profile research down
```

`down` preserves volumes. Do not add `-v` unless deliberately destroying this disposable
database, Redis state, TLS state and private artifacts. Preserve `.env.cloud.local` for
this volume set: regenerating credentials does not change an existing database password.

## Future Ubuntu VPS deployment

Purchase/provision a server separately; no existing remote server is assumed. Install
Docker Engine and the Compose plugin using [Docker's Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).
Keep its firewall enabled, publish only 80/443 (and restrict operator SSH), and point a
chosen domain's DNS to it. Do not use the local override or Windows tunnel mode there.
Automatic certificate issuance needs working DNS and reachable HTTP/HTTPS ports.

```bash
git clone YOUR_REVIEWED_REPOSITORY_URL auvylen
cd auvylen
cp .env.cloud.example .env.cloud
chmod 600 .env.cloud
# Edit .env.cloud with secure database credentials, preserved pepper, domain,
# DATABASE_URL, REDIS_URL, exact HTTPS CORS_ORIGINS and release IMAGE_TAG.
docker compose --env-file .env.cloud -f docker-compose.prod.yml -f docker-compose.cloud.yml build --pull
docker compose --env-file .env.cloud -f docker-compose.prod.yml -f docker-compose.cloud.yml up -d --wait postgres redis
# Back up any existing data before upgrades. First deployment has no prior data.
# Review new migrations, then explicitly set APPLY_MIGRATIONS=true in .env.cloud.
bash scripts/deploy-cloud.sh .env.cloud
curl --fail https://YOUR_DOMAIN/health
curl --fail https://YOUR_DOMAIN/ready
```

Defaults are `APP_ENV=production`, `RESEARCH_MODE=false`, mock checkout disabled, no
providers enabled. Production still refuses MockScoringEngine. There is no usable real
model yet; do not describe this as a working facial-analysis deployment. A future
authorized synthetic research pilot may explicitly use staging + RESEARCH_MODE=true,
while keeping mock checkout disabled and exact HTTPS origins. Do not enable all users:
grant research access individually via CLI. Add `--profile research` for the worker.

## Queue and research correctness

The HTTP request only authenticates, checks CSRF/Origin/rate/resource limits, locks the
user row, and inserts a job. It never runs training. Per-user request keys are unique;
repeated submissions return the same job. Defaults permit two queued/running jobs and
50 new jobs per rolling day per authorized user. Current jobs are CPU-only synthetic
scores with no user-uploaded image. Model, user ID, cost and result cannot be forged in
the request. No Credits are touched by research execution.

Workers claim using `FOR UPDATE SKIP LOCKED`, execute outside the claim transaction,
and save only if their random lease token still owns the job. An expired lease can be
retried up to three claims; authorization is checked at claim and completion. Results
persist in PostgreSQL across container restarts. Execution is at-least-once, not an
exactly-once training guarantee. Current 60-second leases are suitable for the fast mock.
Long training requires lease renewal, cancellation and checkpoint-resume support before
it is enabled. `TRAIN` and `gpu` are reserved schema capabilities, not working training
or GPU support. Future GPU workers will need authenticated private DB/cache connectivity
and shared private artifact storage; no public database ports are part of that plan.

## Custom and optional model interfaces

`aevyra_inference.custom` permanently owns validated DatasetSnapshot, Rating,
PairwisePreference, CheckpointManifest and CustomTrainer contracts. Dataset versions,
owners, consent references, checkpoint hash/version and training provenance are explicit.
No image import UI, annotation database/API, training algorithm or real inference exists.
Removing every optional provider leaves these contracts and the research queue intact.

`aevyra_inference.providers` defines isolated ModelProvider plugins. Each is independently
installed in an operator-built worker image as a reviewed Python wheel with entry point
group `auvylen.model_providers`, named `comboloss`, `fpem`, `faclip`, `swingfvqa-ca` or
`custom`. Enable only selected slugs using `ENABLED_MODEL_PROVIDERS=["comboloss"]`.
Rebuild that worker image to remove a wheel, disable its slug, and leave the custom
subsystem untouched. Do not install incompatible research dependencies in the web image
or core API environment. No runtime pip install, source cloning or weight download occurs.

Plugin factory returns `ModelProvider`; `availability(model_root)` must check pinned
dependencies, verified private weights, input specification and licensing/provenance;
`load(model_root)` returns the existing ScoringEngine. Missing adapter/dependencies/weights
must fail, never return mock/random scores. Real image inference remains rejected by the
HTTP route even if a plugin is installed, until authorized image import and integration
are implemented in Phase 4B. All scoring execution must retain the existing registry
policy gate. Production mock execution remains forbidden.

Upstream reference identities verified: [ComboLoss official implementation](https://github.com/lucasxlu/ComboLoss)
and [FPEM official implementation](https://github.com/Estella-LH/FPEM). No code, dataset,
weights or dependencies from them were installed. Exact canonical sources and versions
for FACLIP and SwinGFVQA-ca still need operator confirmation; similarly named packages
must not be substituted. A repository license does not prove checkpoint/dataset rights.

## Capacity estimate and Phase 4B prerequisites

Engineering sizing estimate for this foundation: 2 vCPU, 4 GB RAM, 60 GB SSD for low
traffic and mock CPU jobs; 4 vCPU / 8 GB RAM gives more build and database headroom.
This is not a sizing promise for real models or training. Build images elsewhere if the
small VPS cannot accommodate builds. Storage needs must be recalculated for actual
consented images/checkpoints; no GPU is required now.

Before Phase 4B: choose VPS/domain and reviewed release commit; configure off-host
encrypted backups and monitoring; confirm model identities/licenses/input requirements;
implement consent, image decoding/size/pixel limits, retention/deletion and ownership
metadata; implement persistent annotations/dataset import; select and test a real custom
training algorithm; add long-job leases/cancellation/checkpoint resume; build separately
locked model worker images; test real research inference and any future GPU transport.
No commercial payment integration is a prerequisite. No public deployment is claimed.
