# Auvylen engineering rules

The brand rename is cosmetic. Retain legacy Python import paths, database/product IDs,
Compose project names, environment names and scoring fixture bytes as documented in
docs/brand-rename.md. Do not "clean up" these identifiers with a global replacement.

Auvylen is intended to become a paid production application. Financial correctness,
privacy, authorization and model provenance eventually take priority over development
convenience. Preserve completed **Phase 4A**. Current scope is **Phase 4B: Custom AI
Preference Learning**, authorized by [the master instruction](docs/phase4b-master-instruction.md).
In a local Windows session, perform recovery and cloud preparation only. Implement and
test resource-intensive Phase 4B work in an available remote development environment.
Follow [the cloud development handoff](docs/cloud-development.md); never silently fall
back to Windows/WSL or local Docker. No cloud environment or paid server is assumed.

## Boundaries

- Keep the frontend in `apps/web`, HTTP orchestration in `services/api`, scoring in
  `services/inference`, shared wire contracts in `packages/contracts`.
- Never commit secrets or credentials other than clearly labelled local-only examples.
- Never expose model weight files to the browser.
- Never fabricate production model outputs or make unsupported accuracy claims.
- Never tightly couple business logic to one AI model.
- Never silently swallow exceptions. Handle expected failures explicitly; log safe event
  names and error classes, without exception text that could contain secrets.
- Never log authentication tokens, request payloads or connection URLs.
- Never create unversioned database schema changes. Use Alembic; do not call `create_all`
  during application startup.
- Never commit downloaded research code, real model weights, private images or datasets.
  Phase 4B may install reviewed dependencies/weights remotely after verifying both code
  and weight licenses; do not download these to the user's Windows computer.
- Production website and workers run on a future Linux cloud host, never depend on the user's Windows computer. No VPS exists yet; do not claim remote deployment.
- Keep custom-model contracts independent from removable third-party providers. Missing adapters/weights must report unavailable; never fabricate real predictions.
- The mock engine must remain explicitly synthetic and disabled in production.
  Phase 4B now includes the reviewed first-party visual rating baseline; see
  docs/custom-preference-models.md and docs/pretrained-representation.md. Custom training and inference are non-commercial
  research operations and use the registry research policy gate. Unavailable external
  models must stay unavailable.
- Phase 6 (authorized by the user on 2026-10-26) adds the first-party aesthetic
  rating-distribution model; see docs/aesthetic-scoring.md. It stays disabled until an
  authorized human-rated dataset produces a checkpoint that passes the release gate and the
  user approves pinning it. Never train on distributions derived from mean scores, never
  infer adulthood from appearance, and never enable synthetic checkpoints outside
  development/test.
- Every future execution must use the registry policy gate; new engines require explicit
  provenance and licensing review. A commercial flag is not a substitute for evidence.

## Future invariants

Every future scoring result must preserve engine/model version, calibration version
where applicable, raw score, normalized/display score and timestamp. Capture licensing
and provenance evidence independently of presentation code.

Future financial mutations must be transactional, idempotent and auditable. Authorization
must be enforced on the server. Retention and access controls must precede real uploads.

## Working practice

For Next.js changes, consult the documentation bundled with the installed version in
`node_modules/next/dist/docs` and heed deprecations. Framework-generated agent files are
disabled so these repository-wide engineering rules remain intentionally maintained.

Prefer small reviewable changes, explicit interfaces, documented migrations and automated
tests. Do not perform giant rewrites without a documented engineering reason. Do not
suppress errors merely to pass checks. Update both Python and TypeScript contracts when
wire responses change. Keep future architecture labelled as unimplemented.

Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`,
`npm test`, `npm run lint`, `npm run typecheck`, and `npm run build` for relevant changes.
With Compose running, also run `uv run pytest --integration`, migrations and `alembic check`
using the commands in README, in the remote development environment. Report unavailable
infrastructure honestly; skips are not successful integration checks. Do not start local
persistent services or heavy builds/tests. Do not proceed to a later phase or public deployment automatically.

Production deployment uses provider-neutral Compose and Caddy. Only the proxy publishes
ports. Keep PostgreSQL and Redis internal, authorize the serialized cloud migration gate explicitly, and back up before schema
changes. Never use the local TLS override or staging mock flow as a public deployment.
Production images must exclude env files and dev tools; application containers run non-root.

Payment-event processing exclusively owns payment success and the PAID transition.
Keep prices in integer minor units, loaded from the backend product record. Lock orders
for financial mutations; use durable unique keys and transactions for event idempotency.
Commit payment confirmation before scoring. Mock commercial routes must stay disabled
in production. First-party accounts are authorized. Phase 4B authorizes private adult-image
ingestion, annotations and real custom models only after consent, ownership, decoding,
retention and resource safeguards are implemented. Real payment integrations remain excluded.

Credit history is append-only. Lock wallets for every financial mutation, derive balance
from ledger history, and use compensating entries for corrections/refunds. Keep refund
and analysis request keys durable. Never directly edit cached balances through operator tools.
Redemption codes use HMAC lookup with the protected pepper; never store/log plaintext
codes or session tokens. Plaintext exports belong only in gitignored exports/ and must
also be excluded from Docker builds. Operators must protect exports and back up the pepper.
Require account ownership, exact Origin and CSRF validation for account mutations.

Research execution requires explicit RESEARCH_MODE and an operator-granted user access record
for standard users; the unique database-backed Owner receives permanent research entitlement
through `entitlements.py`. Future product features must integrate with this central policy
without bypassing registry licensing, availability, private ownership or resource safeguards.
Owner administration requires explicit server-side authorization and recent authentication;
mutations must commit their append-only audit records with financial/state changes.
Research jobs never mutate Credits. Durable jobs are owned by PostgreSQL; workers execute
outside HTTP requests, fence stale completions, and enforce bounded retries. At the Phase
4A baseline, no training algorithm or real inference is implemented. Private upload/model
volumes never belong in web/proxy containers. Do not enable image ingestion or long-running
training until consent, decoding limits, retention, lease renewal, cancellation and reviewed
implementations exist. Custom labels come from the user, never third-party predictions.
Keep subject identities grouped across validation splits and report measured limitations.
