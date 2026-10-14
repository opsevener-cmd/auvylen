# Auvylen

**Cloud-first development:** Phase 4A is preserved; Phase 4B custom preference learning
is authorized but not implemented yet. Windows is for code review and browser access
only. Do not run the service startup, dependency installation, build or integration-test
commands below on the user's computer. Use [cloud development](docs/cloud-development.md)
and [the recovery report](docs/recovery-cloud-transition.md). The older local instructions
remain for reproducibility in disposable remote environments, not as a hosting requirement.

The provisional brand is Auvylen. Stable deployment/database identifiers and Python
import paths retain their previous spelling for compatibility. See
[rename audit](docs/brand-rename.md) before changing any legacy technical identifier.

Auvylen is intended to become a cloud-hosted AI facial attractiveness research and evaluation platform,
with multiple scoring engines and user-defined standards. **Implemented baseline is Phase 4A:
Cloud-Ready Architecture and Project Recovery**, preserving Phase 3 first-party pilot accounts,
channel-neutral redemption codes and an immutable credit ledger alongside the preserved
development order/mock-payment flow. No real payments, facial models, uploads, subscriptions
or platform-specific commerce integrations are implemented.

Start with [the Phase 4A audit and runnable cloud simulation](docs/phase4a.md). The new
cloud override adds safe automatic migration gating, private artifact volumes and an
optional CPU worker backed by PostgreSQL jobs. Authorized `/research` jobs do not spend
Credits. Custom training and all four requested third-party models remain unavailable.
Production must run on a future Linux VPS; resource-intensive development must run remotely.
No VPS has been purchased or deployed. [Backup/restore](docs/cloud-backups.md).

The provider-neutral single-VPS deployment adds production API/web images, internal
PostgreSQL/Redis and a Caddy HTTPS proxy. Production checkout and mock-payment simulation
are disabled. Private staging retains the synthetic Phase 1 flow. See
[deployment instructions](docs/deployment.md), [security boundaries](docs/production-security.md)
and [verification](docs/verification.md). Production mock inference remains disabled.
Accounts and redemption do not enable production synthetic execution. No public tunnel is started.

Production startup (after creating the protected env file as documented):

```sh
docker compose --env-file .env.production -f docker-compose.prod.yml build --pull
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --wait postgres redis
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps api alembic -c services/api/alembic.ini upgrade head
docker compose --env-file .env.production -f docker-compose.prod.yml run --rm --no-deps api alembic -c services/api/alembic.ini check
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --wait
```

Only TCP 80/443 are published. DNS and a final domain are required for public TLS.
The separate local override binds 8080/8443 to loopback with a private TLS CA; exact
production/staging test commands are in deployment.md. Development startup below is unchanged.

## Structure

```text
apps/web/             Next.js; accounts, redemption, credit analysis, legacy checkout/status
services/api/         FastAPI; accounts, immutable credits, redemption, payment events
services/inference/   Installable Python scoring package; abstract engine and mock
packages/contracts/   Shared Python response models and TypeScript wire types
infra/                Infrastructure notes; local Compose lives at repository root
docs/                 Architecture and verification notes
```

Inference remains an isolated package, not a running network service. This avoids
an unnecessary deployment boundary while retaining a reusable engine interface.

## Requirements

- Node.js 24 LTS (minimum 22) and npm.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) for Python and dependencies.
  `.python-version` selects Python 3.14; uv can install it automatically.
- Docker Desktop with Linux containers and Docker Compose v2. Make sure Docker is running.
- Free ports 3000, 8000, 5432 and 6379.

On this Windows development machine, Docker Desktop is installed per-user at
`C:\Users\ChenC\AppData\Local\Programs\DockerDesktop`. Its CLI is
`resources\bin\docker.exe` beneath that directory. If a terminal opened before
installation cannot find `docker`, reopen it or add that directory to the current
PowerShell session's PATH. Start Docker Desktop before running Compose.

Dependencies are resolved in `package-lock.json` and `uv.lock`; use the locks for
reproducibility. Upgrade them deliberately instead of replacing them with floating installs.
Run all following commands from the repository root unless specified otherwise.

## Local setup

These initialization commands are for a fresh checkout. Never overwrite an existing env
file or regenerate its pepper after issuing codes. Restart existing API/web processes
after updating so they load the current application code.

PowerShell:

```powershell
Copy-Item .env.example .env
Set-Content apps/web/.env.local 'API_URL=http://127.0.0.1:8000'
npm ci
uv sync --locked
uv run python -c "from pathlib import Path; import secrets; p=Path('.env'); p.write_text(p.read_text().replace('REPLACE_WITH_SECURE_RANDOM_SECRET', secrets.token_hex(48)))"
docker compose up -d --wait
uv run alembic -c services/api/alembic.ini upgrade head
uv run alembic -c services/api/alembic.ini current
uv run alembic -c services/api/alembic.ini check
```

macOS/Linux: use `cp .env.example .env` and create `apps/web/.env.local` containing only
`API_URL=http://127.0.0.1:8000` for the first two commands; remaining commands are identical.
Generate the pepper once, keep it stable and back it up securely. Do not copy API secrets
to the web environment. CORS_ORIGINS must contain the exact browser origin you use.

In one terminal start the API:

```sh
uv run uvicorn aevyra_api.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal start the web application:

```sh
npm run dev
```

Application processes run on the host for quick reloads; Compose runs only PostgreSQL
and Redis. Their published ports bind to loopback. Persistent volumes survive
`docker compose down`; `docker compose down -v` **destroys local database/cache data**.
This Compose configuration is development-only and is not a production deployment.

## Environment configuration

Never commit `.env` or `.env.local`. Defaults in `.env.example` are public development
fixtures, not deployment secrets. Backend settings read root `.env` and OS environment
variables (OS values take precedence). Next.js reads `apps/web/.env.local`.

| Variable | Purpose | Development default |
| --- | --- | --- |
| `API_ENVIRONMENT` | Legacy API selector: development/test/staging/production | `development` |
| `APP_ENV` | Deployment selector; supersedes API_ENVIRONMENT | production in production Compose |
| `DATABASE_URL` | SQLAlchemy psycopg URL | Local PostgreSQL / database `aevyra` |
| `REDIS_URL` | Redis URL | `redis://127.0.0.1:6379/0` |
| `LOG_LEVEL` | Application JSON log level | `INFO` |
| `CORS_ORIGINS` | JSON list of allowed browser origins | `["http://localhost:3000"]` |
| `API_URL` | Server-side web-to-API origin | `http://127.0.0.1:8000` |
| `POSTGRES_USER` | Compose database user | `aevyra` |
| `POSTGRES_PASSWORD` | Compose database password | `aevyra_dev_only` (local only) |
| `POSTGRES_DB` | Compose database name | `aevyra` |
| `PAYMENT_PROVIDER` | Only `mock` is available in Phase 1 | `mock` |
| `REDEMPTION_CODE_PEPPER` | Required HMAC secret; generate once and back up | placeholder only |
| `SESSION_LIFETIME_SECONDS` | Server/cookie session lifetime | `86400` |
| `SESSION_COOKIE_SECURE` | Secure on HTTPS; forced in staging/production | `false` for local HTTP |

If you change Compose database credentials, update `DATABASE_URL` too. PostgreSQL
initialization variables take effect only on a fresh volume. Percent-encode special
characters in connection URLs. Never print those URLs in logs. Production settings
reject the example database password and wildcard CORS. Debug is always off; production
disables interactive API docs. These defaults are not a complete deployment security plan.
Legacy mock checkout and synthetic execution are disabled in production. Accounts/ledger
remain protected by sessions, CSRF and server authorization. Future WeChat Pay
and Alipay placeholders in `.env.example` are comments, not consumed settings. Leave them
empty; no real credentials are requested. Keep the legacy unauthenticated mock flow private.

## Phase 3 local pilot flow

1. Open http://localhost:3000/register; create an identifier and a password of 12–128 characters.
   The account page starts at **0 Credits**. Logout/login use /account and /login.
2. Generate a batch from the repository root:

```sh
uv run python -m aevyra_api.operator generate-batch --name "Pilot 10 Credits" --channel manual --sku pilot-10 --credits 10 --quantity 10 --output ./exports/pilot-10.csv
```

3. The protected, gitignored `exports/pilot-10.csv` contains ten one-time codes worth ten
   Credits each. Inspect the printed batch ID with `batch-summary` before distributing it.
   Open the file locally; do not paste codes into logs or Git. Existing files are never overwritten.
4. Open /redeem, enter one code and click Redeem. The balance becomes **10 Credits**.
5. Open /analyze while signed in. The backend advertises **Cost: 1 Credit**. Click Run Analysis;
   the result is explicitly synthetic and the account balance becomes **9 Credits**.
6. /account shows +10 REDEMPTION and -1 ANALYSIS. /history links to the saved result.
   A used code fails generically; inference failure appends an exactly-once refund.

Operator commands and security details: [accounts](docs/accounts.md), [credit ledger](docs/credits.md),
[redemption codes](docs/redemption-codes.md). The external sale is outside Auvylen; channels are
metadata. Existing Product/Order/Payment abstractions are preserved for future direct funding.

## Health and metadata URLs

| URL | Meaning |
| --- | --- |
| `http://localhost:3000/` | Minimal Auvylen shell |
| `http://localhost:3000/status` | Live server-side API readiness request; no cache |
| `http://localhost:3000/analyze` | Development product selection |
| `http://localhost:3000/checkout/{public_order_id}` | Mock checkout |
| `http://localhost:3000/result/{analysis_id}` | Explicitly synthetic result |
| `http://127.0.0.1:8000/health` | Liveness, independent of PostgreSQL/Redis |
| `http://127.0.0.1:8000/ready` | SQL `SELECT 1` and Redis `PING`; 200 or 503 |
| `http://127.0.0.1:8000/api/v1/scoring-engines` | Engine provenance and licensing metadata |
| `http://127.0.0.1:8000/docs` | Development API documentation |

`/status` distinguishes a connected API with unhealthy dependencies from an unreachable
API. Reload the page for another check. Readiness proves connectivity, not schema currency;
run migrations before startup. Operational endpoints are unversioned; domain routes use
`/api/v1`.

## Database migrations

```sh
uv run alembic -c services/api/alembic.ini upgrade head
uv run alembic -c services/api/alembic.ini check
uv run alembic -c services/api/alembic.ini revision --autogenerate -m "Describe schema change"
```

Always review generated migrations before applying them. The first migration creates
only `foundation_records`, an operational marker table. `0002_commercial` adds Product,
Order, PaymentAttempt, PaymentEvent, Analysis and AnalysisResult tables, their constraints,
and the development product `aevyra-test-analysis` at 100 CNY minor units (¥1.00).
Migrations are explicit and never run automatically during API startup.

## Tests and quality checks

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
npm test
npm run lint
npm run typecheck
npm run build
```

Unit tests use injected dependency failures. They do not claim real infrastructure
connectivity. To run real PostgreSQL/Redis connectivity and migration/schema checks:

```sh
docker compose up -d --wait
uv run pytest --integration
uv run alembic -c services/api/alembic.ini check
```

Integration tests use the configured database and never downgrade it. Prefer a dedicated
test database. Default runs explicitly skip integration tests; `--integration` fails if
dependencies are missing. CI runs all tests with ephemeral PostgreSQL/Redis services.
Frontend tests cover successful, failed and inconsistent readiness responses.
Commercial unit tests apply real Alembic migrations to isolated SQLite test fixtures and
verify schema drift, price authority, event idempotency, state transitions and recovery.
SQLite is never an application database fallback. PostgreSQL integration tests additionally
verify concurrent callback delivery in isolated temporary PostgreSQL schemas. The configured
test user needs CREATE SCHEMA permission; only generated `aevyra_test_...` schemas are removed.

For the complete browser flow with PostgreSQL and Redis running:

```sh
npm run build
npm exec --workspace @auvylen/web -- playwright install chromium
npm run test:e2e --workspace @auvylen/web
```

Playwright starts the API and production-built web app if they are not running. Restart
stale app processes before testing. The browser test uses a 390px mobile viewport, performs
real server actions, and checks the persisted order/result through the API.

## Synthetic engine

`MockScoringEngine` requires no model, image, GPU or dataset. Numeric outputs are
deterministic for identical fixture bytes; timestamps record each invocation. A hash
mapped to a score does **not** measure any property of a face. Metadata states
`synthetic=true`, `commercial_allowed=true` and `production_enabled=false`. Commercial
permission covers only the internal synthetic implementation, not any future model.
The registry refuses production execution unless both approval flags are true.
Paid development orders invoke this engine through the registry. There is no standalone mock scoring execution endpoint. The separate authorized research
dataset UI accepts private images but does not yet run real scoring.

## Manual commercial flow

1. Open `http://localhost:3000/` and select **Start Analysis**.
2. `/analyze` loads **Auvylen Analysis**, development price **¥1.00**, from the backend.
3. Select **Create order**. The backend loads the product price; the web submits only
   `product_slug`. A pending mock payment attempt is established before checkout.
4. On `/checkout/{public_order_id}`, select **Simulate successful payment**.
5. The server creates and verifies a mock notification, processes it transactionally,
   commits the payment and PAID state, then runs isolated synchronous fulfillment.
6. `/result/{analysis_id}` displays **Development / Synthetic Result**, raw/display scores,
   engine/version and COMPLETED status. The order is now COMPLETED.

API capabilities (all under `/api/v1`): `GET /products`, `POST /orders`,
`GET /orders/{public_order_id}`, `POST /orders/{public_order_id}/payments`,
`POST /dev/payments/{payment_id}/simulate-success`, `GET /analyses/{analysis_id}`,
and `GET /analyses/{analysis_id}/result`. Mutation bodies are `{}` except order creation:
`{"product_slug":"aevyra-test-analysis"}`. Client-supplied price/state/version fields are rejected.

Repeated simulation of the same payment preserves the original analysis and result.
Failure leaves the payment successful and order/analysis explicitly FAILED. Development
operators can explicitly retry a paid or failed order with:

```sh
uv run python -m aevyra_api.retry_fulfillment av_REPLACE_WITH_PUBLIC_ORDER_ID
```

There is no automatic retry of failed scoring on duplicate notifications. The retry uses
the same analysis ID and is disabled in production. See [payments](docs/payments.md) and
[order lifecycle](docs/order-lifecycle.md) for transaction boundaries and limitations.

## Limitations and next-phase boundaries

See [architecture](docs/architecture.md) and [verification](docs/verification.md).
Pilot accounts have no email verification, automated password recovery or social login.
Phase 4B now includes private datasets, image ingestion, ratings and pairwise annotations;
see [the tested implementation report](docs/phase4b-progress.md). Real numerical-rating model training, versioned checkpoints, retraining and unseen-image
predictions are implemented; see [custom preference models](docs/custom-preference-models.md).
Real payments and external GitHub-model comparisons remain unimplemented. Production hosting templates
remain provider-neutral, but public deployment is not performed. Shared TypeScript wire types are
maintained explicitly alongside Python models; update both and tests when routes change.
Engine inputs are opaque bytes; later phases must define safe input limits and validated
image/domain representations before accepting untrusted content.

Phase 4B also supports the independent frozen MobileNetV3-Small representation. See
[pretrained model setup and licenses](docs/pretrained-representation.md) and
[measured verification](docs/phase4b-representation-report.md).
