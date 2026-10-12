# Auvylen architecture — Phase 4A

Phase 4A is the preserved implementation baseline. Phase 4B custom preference learning
is now authorized for remote development, but its datasets, annotations and genuine
training/inference are not implemented. See [cloud development](cloud-development.md)
and [the master instruction](phase4b-master-instruction.md). Do not run resource-intensive
development on the user's Windows computer. No remote host is configured yet.

The current cloud-ready additions and audit are described in [Phase 4A](phase4a.md).
Use the production Compose base plus `docker-compose.cloud.yml`: a migration gate,
optional CPU worker, private artifacts and PostgreSQL-backed research jobs augment the
preserved account/Credit/payment application. `/research` is authenticated and explicitly
authorized, with no Credits mutation. Custom trainer/provider contracts exist; real models
and training do not. Windows hosting and tunnels are not production dependencies.
The older foundation explanations below describe the retained Phase 0–3 layers.

Brand labels and package distributions use Auvylen. Python import namespaces, database
identifiers, health/logging IDs and deterministic scoring inputs remain stable. The product
response translates the original seeded display name without updating the stored row.
See [rename compatibility audit](brand-rename.md). The cosmetic rename changed no schema;
Phase 3 adds account/credit tables without rewriting payment architecture.

## Implemented structure

Production deployment: Internet → Caddy (80/443, automatic HTTPS) → Next.js web or
FastAPI `/api/*`, `/health`, `/ready` → internal PostgreSQL/Redis. The web makes server-side
calls through API_URL; inference remains installed inside the API image. Both application
images run non-root; only Caddy publishes ports. Database and TLS storage use named volumes.
The original production base retains disposable Redis; the cloud override enables AOF
and a Redis volume for rate-limit recovery. PostgreSQL owns durable research jobs.
Development Compose remains unchanged. No migration was needed in Phase 2.

Production mock checkout/inference are disabled; pilot account/redemption APIs require
sessions, CSRF and exact browser origins. Staging can
execute the synthetic commercial flow but must remain private. See [deployment](deployment.md)
and [production security](production-security.md) for exact operational safeguards.

```text
Browser → Next.js / and /status → FastAPI /ready
                                      ├─ PostgreSQL (SQLAlchemy / psycopg)
                                      └─ Redis (bounded PING)
FastAPI /api/v1/scoring-engines → scoring registry → mock metadata
Next.js server actions → orders → payment adapter → verified event processor
                                                → committed PAID order
                                                → fulfillment service → scoring registry
                                                → saved synthetic result / COMPLETED
```

The frontend owns rendering, navigation and a server-side readiness request. FastAPI
owns domain HTTP contracts, dependency checks, settings and logging. No browser receives
database credentials or model assets. The web app validates readiness responses at the
network boundary and distinguishes transport failures from service dependency failures.
Checks use bounded connection/socket timeouts and do not cache results.

Python response models and TypeScript readiness types live in `packages/contracts`.
They are deliberately small, manually maintained contracts. Changes must update both
representations and boundary tests. FastAPI also exposes its generated OpenAPI document.
The repository uses npm workspaces and uv workspaces with committed dependency locks.

## PostgreSQL

SQLAlchemy provides an engine and session factory. PostgreSQL owns durable relational
state. Alembic manages every schema change. The first
migration creates a small operational marker table to prove the migration path. Startup
does not call `create_all` or mutate schema. Readiness checks connectivity only; migration
currency is verified through `alembic check` and integration tests.

Phase 1 adds six commercial tables and a development product through `0002_commercial`.
Money is stored as integer minor units. Orders snapshot the backend product amount and
currency. PostgreSQL row locks serialize order mutations; durable unique constraints
protect event identifiers, provider payment identifiers, one analysis per order, and one
result per analysis. Payment confirmation commits before synchronous scoring begins.
See [payments](payments.md) and [order lifecycle](order-lifecycle.md).

## Redis

Redis is a separate local dependency with a connection check. It does not currently
host jobs or financial history. It does host atomic account/redemption rate limits. Its interface is isolated from inference,
leaving later worker integration possible. Persistent development volumes are provided,
but Redis must not become the sole source of truth for financial state.

## Inference and model policy

`services/inference` is an independently installable Python package. It is not a running
HTTP service yet: introducing network scheduling before there is inference work would
add complexity without benefit. This is the documented interpretation of the service
directory for Phase 0. It can later be hosted by a dedicated service or worker.

Scoring stays outside frontend code so model assets, provenance checks and execution
policy remain server-side. `ScoringEngine` exposes preprocessing, prediction,
normalization and metadata through a common interface. The API lists engines without
implementing a public scoring endpoint. Paid development orders execute through an
isolated fulfillment service. The registry rejects duplicate slugs and checks policy
before engine operations. Production execution requires both `commercial_allowed` and
`production_enabled`. Metadata includes model version, licensing status, provenance and
an explicit synthetic marker. A flag alone is insufficient for future legal approval;
evidence and review must be defined before adding real models.

Only the internal mock exists. Its SHA-256-based numeric outputs are repeatable but
meaningless for facial aesthetics. Production execution is disabled. Scoring results
preserve raw/display scores, engine version, optional calibration version, UTC execution
timestamp and synthetic status. Real engine output structure and normalization need
validation before later models are introduced.

## Configuration, security and observability

Settings read environment variables and ignored local env files. Connection URLs use
secret types and are never included in HTTP failures or application logs. CORS permits
explicit frontend origins with cookie credentials and CSRF header support. Application errors return
generic 500 responses. Debug is off in every environment. Dependency failures produce
structured events with safe dependency names/error classes. Each request gets a generated
request ID. JSON logs identify the API service and correlate analysis/order IDs
through commercial services where applicable. Startup resource ownership
uses lifespan cleanup. Legacy mock-payment routes are disabled in production until authorization
and real payment verification are designed and implemented.

Development Compose binds dependency ports to loopback; production Compose publishes no
database/cache ports. Production uses runtime secrets, strict connection configuration,
Caddy HTTPS and rotating container logs. First-party pilot authentication, ownership and
Redis rate limits are implemented. Retention policy and full operational monitoring need
a later launch review.

## Implemented Phase 3 accounts and Credits

Migration 0003_credits adds users, sessions, wallets, credit_transactions, redemption_batches,
redemption_codes and redemptions. Product.credit_cost is server-owned. Analysis.order_id can
be null for account-funded analyses; an exclusive-funding check requires either an order,
or a user plus credit request key. Existing order records and seeded identifiers are preserved.

Browser → cookie/CSRF protected API → account service → wallet/append-only ledger.
Operator CLI → HMAC code generation → protected one-time CSV. Customer redemption locks
batch/code/wallet and credits atomically. Credit analysis locks wallet, commits deduction,
then runs isolated fulfillment with the existing scoring registry. Permanent inference
failure appends a compensating refund. Production mock execution remains policy-disabled.
Redis holds only short-lived rate counters, never balances or financial locks.

The frontend uses same-origin account requests; local Next.js provides an allowlisted proxy
while Caddy routes production API calls directly. Session/cost/ownership decisions remain
server-side. Shared Python/TypeScript contracts cover the new wire responses.
See [accounts](accounts.md), [credits](credits.md) and [redemption codes](redemption-codes.md)
for locking order, immutable history, secret backup and operator commands. A future worker
can replace synchronous fulfillment. A future verified payment product can fund the same
ledger without replacing the existing payment provider interface; this is not implemented.

APP_ENV supports development/staging/production and supersedes legacy API_ENVIRONMENT.
Service URLs isolate infrastructure locations from business logic. No cloud vendor SDK
is required. Assets/fonts are local/system-based; only public DNS/ACME certificate renewal
is an external deployment runtime dependency. Build registries are external build dependencies.

## Future architecture — not implemented

### Real payments

The payment interface, mock adapter and transactional event processor are implemented.
WeChat Pay and Alipay adapters are inert scaffolds; each operation raises NotImplementedError.
Real credentials, signature verification, queries, notifications and refunds remain future
work. No public webhook route exists; its reserved integration point is
`POST /api/v1/payments/webhooks/{provider}`, which must verify before normalizing an event.
No real funds are moved and there is no real-payment refund workflow. Credit-funded
analysis has an implemented compensating ledger refund, described above.

### Object storage

Later image storage should use private object storage, authorization, retention controls
and carefully constrained upload/download grants. Store object references rather than
large image blobs in the database. No storage SDK, upload route or image processing exists.

### Background workers

Later workers can import the scoring package and execute through the same registry
policy gate. Choose a queue after defining retry, timeout, deduplication and observability
requirements. Redis may support queue transport, while durable analysis state remains
in PostgreSQL. No queue, scheduler or worker is currently implemented.

### Analysis and custom standards

Later phases must define input validation, authorization, provenance snapshots,
calibration versioning and user-defined standards without coupling to a single model.
No real model, dataset, face detection or scoring preference system is integrated now.
