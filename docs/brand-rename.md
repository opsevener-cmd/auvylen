# Auvylen controlled rename audit

The previous brand, Aevyra, is replaced in visible branding and safe package/image labels.
This audit documents every remaining maintained-source occurrence by file/line. It also
scans ignored generated/dependency files, grouping their occurrences below. Env values
are never printed. Run `uv run python scripts/audit-brand.py` to refresh this report.

## Decisions and compatibility

- npm root/workspaces now use auvylen and @auvylen; Python distributions use auvylen-*.
  Python import directories remain aevyra_api/aevyra_inference/aevyra_contracts so existing
  imports, Uvicorn targets, migration imports and operator commands continue to work.
- Images use auvylen-api/auvylen-web. API container username changed; numeric UID 10001
  remains unchanged. Generic service names api/web/postgres/redis/proxy are unchanged.
- Compose project names aevyra/aevyra-prod/aevyra-phase2 are retained, preserving named
  volumes and existing container/network identities. Keep using the existing project name.
- Database/user names, original migration bytes, product slug aevyra-test-analysis,
  seeded product name Aevyra Analysis and public order prefix av_ are retained. Product
  responses translate the original display name to Auvylen Analysis without a DB write.
- Scoring fixture prefix aevyra-development: is unchanged: rebranding it would change
  synthetic scores for the same order. No scoring/payment/state-machine code was renamed.
- Health IDs and log namespaces stay stable for monitors. Environment prefixes AEVYRA_
  remain accepted unchanged; a provisional branding change does not justify env churn.
- No files/directories or physical checkout were moved. New VPS checkout examples use
  /opt/auvylen; existing checkouts need not move. Remote repository names were not changed.
- New backup filenames use auvylen-. Historical backups retain their original filenames
  and binary payloads; Git history, binary caches and backups are not rewritten. Installed
  dependencies/generated outputs may contain compatibility strings, historical caches and
  the old physical checkout path. They are not maintained branding sources.
- This report and the audit script intentionally mention the prior brand/identifiers to
  document and enforce these decisions; their self-references are excluded from the ledger.

## Cosmetic rename verification (historical)

Backend/infrastructure: 62 passed. Frontend unit tests: 15 passed. Ruff lint/format, mypy,
ESLint, TypeScript and frontend production build passed. Development browser checkout
passed with the new visible product name. See verification.md for deployment evidence.
The cosmetic rename changed no schema, payment architecture or scoring algorithm. Later
Phase 3 changes are documented separately in verification.md; this ledger audits names only.

## Remaining-reference ledger

Maintained-source occurrences: **298**. Must rename: **0**.

| File:line | Occurrences | Classification | Reason |
| --- | ---: | --- | --- |
| .env.example:5 | 3 | intentionally retained | Existing database identity / development-password rejection guard |
| .env.example:11 | 1 | intentionally retained | Existing database identity / development-password rejection guard |
| .env.example:12 | 1 | intentionally retained | Existing database identity / development-password rejection guard |
| .env.example:13 | 1 | intentionally retained | Existing database identity / development-password rejection guard |
| .env.production.example:3 | 1 | intentionally retained | Existing environment interface retained without aliases |
| .env.production.example:5 | 1 | intentionally retained | Existing database identity / development-password rejection guard |
| .env.production.example:6 | 1 | intentionally retained | Existing database identity / development-password rejection guard |
| .github/workflows/ci.yml:14 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| .github/workflows/ci.yml:15 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| .github/workflows/ci.yml:16 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| .github/workflows/ci.yml:19 | 2 | intentionally retained | Existing database/user credentials or compatible setup example |
| .github/workflows/ci.yml:58 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| .github/workflows/ci.yml:59 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| .github/workflows/ci.yml:60 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| .github/workflows/ci.yml:63 | 2 | intentionally retained | Existing database/user credentials or compatible setup example |
| .github/workflows/ci.yml:87 | 1 | intentionally retained | Compose project identity preserves volume/network names |
| .github/workflows/ci.yml:103 | 2 | intentionally retained | Existing database/user credentials or compatible setup example |
| .github/workflows/ci.yml:117 | 1 | intentionally retained | Existing environment interface retained without aliases |
| README.md:95 | 1 | intentionally retained | Stable Python import/CLI namespace |
| README.md:119 | 1 | intentionally retained | Documented existing database/user identity |
| README.md:124 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| README.md:125 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| README.md:126 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| README.md:149 | 1 | intentionally retained | Stable Python import/CLI namespace |
| README.md:195 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| README.md:228 | 1 | intentionally retained | Existing isolated PostgreSQL test-schema namespace |
| README.md:269 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| README.md:276 | 1 | intentionally retained | Stable Python import/CLI namespace |
| apps/web/Dockerfile:10 | 1 | intentionally retained | Existing environment interface retained without aliases |
| apps/web/deployment-tests/accounts.spec.ts:13 | 1 | intentionally retained | Compose project identity preserves volume/network names |
| apps/web/deployment-tests/accounts.spec.ts:16 | 1 | intentionally retained | Stable Python import/CLI namespace |
| apps/web/deployment-tests/accounts.spec.ts:35 | 1 | intentionally retained | Existing environment interface retained without aliases |
| apps/web/deployment-tests/accounts.spec.ts:41 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| apps/web/deployment-tests/deployment.spec.ts:17 | 1 | intentionally retained | Existing environment interface retained without aliases |
| apps/web/deployment-tests/deployment.spec.ts:22 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| apps/web/deployment-tests/deployment.spec.ts:27 | 1 | intentionally retained | Existing environment interface retained without aliases |
| apps/web/e2e/credits.spec.ts:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| apps/web/next.config.ts:6 | 1 | intentionally retained | Existing environment interface retained without aliases |
| apps/web/playwright.config.ts:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| apps/web/playwright.deployment.config.ts:3 | 1 | intentionally retained | Existing environment interface retained without aliases |
| apps/web/src/app/analyze/page.tsx:13 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| apps/web/src/app/health/route.ts:2 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| apps/web/src/lib/commercial-api.test.ts:8 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| apps/web/src/lib/commercial-api.test.ts:9 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| apps/web/src/lib/logging.test.ts:9 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| apps/web/src/lib/logging.ts:4 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| docker-compose.prod.yml:1 | 1 | intentionally retained | Compose project identity preserves volume/network names |
| docker-compose.prod.yml:51 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| docker-compose.prod.yml:52 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| docker-compose.prod.yml:80 | 2 | intentionally retained | Existing environment interface retained without aliases |
| docker-compose.yml:1 | 1 | intentionally retained | Compose project identity preserves volume/network names |
| docker-compose.yml:6 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| docker-compose.yml:7 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| docker-compose.yml:8 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| docs/credits.md:48 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/credits.md:49 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/credits.md:50 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/credits.md:51 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/credits.md:52 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/deployment.md:70 | 2 | intentionally retained | Existing database/user credentials or compatible setup example |
| docs/deployment.md:77 | 1 | intentionally retained | Existing environment interface retained without aliases |
| docs/deployment.md:91 | 1 | intentionally retained | Existing environment interface retained without aliases |
| docs/deployment.md:94 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| docs/deployment.md:228 | 1 | intentionally retained | Existing environment interface retained without aliases |
| docs/deployment.md:233 | 1 | intentionally retained | Compose project identity preserves volume/network names |
| docs/deployment.md:234 | 1 | intentionally retained | Compose project identity preserves volume/network names |
| docs/deployment.md:235 | 1 | intentionally retained | Compose project identity preserves volume/network names |
| docs/deployment.md:236 | 1 | intentionally retained | Compose project identity preserves volume/network names |
| docs/deployment.md:250 | 1 | intentionally retained | Existing environment interface retained without aliases |
| docs/deployment.md:255 | 1 | intentionally retained | Existing environment interface retained without aliases |
| docs/order-lifecycle.md:52 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/phase3-report.md:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/phase3-report.md:10 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/phase3-report.md:11 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/phase3-report.md:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/phase3-report.md:26 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/phase3-report.md:61 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/redemption-codes.md:31 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/redemption-codes.md:51 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/redemption-codes.md:52 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/redemption-codes.md:53 | 1 | intentionally retained | Stable Python import/CLI namespace |
| docs/verification.md:70 | 1 | intentionally retained | Compose project identity preserves volume/network names |
| infra/caddy/Caddyfile:4 | 1 | intentionally retained | Existing environment interface retained without aliases |
| infra/caddy/Caddyfile:7 | 1 | intentionally retained | Existing environment interface retained without aliases |
| infra/caddy/Caddyfile:9 | 1 | intentionally retained | Existing environment interface retained without aliases |
| packages/contracts/pyproject.toml:12 | 1 | intentionally retained | Stable Python import/CLI namespace |
| packages/contracts/src/aevyra_contracts/__init__.py:33 | 2 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| packages/contracts/src/aevyra_contracts/accounts.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| packages/contracts/src/aevyra_contracts/commercial.py:56 | 2 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/Dockerfile:21 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/migrations/env.py:1 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/migrations/env.py:2 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/migrations/env.py:3 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/migrations/env.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/migrations/env.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/migrations/versions/0002_commercial_skeleton.py:140 | 1 | intentionally retained | Immutable migration history / original seed |
| services/api/migrations/versions/0002_commercial_skeleton.py:141 | 1 | intentionally retained | Immutable migration history / original seed |
| services/api/pyproject.toml:20 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/accounts.py:18 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/accounts.py:19 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/accounts.py:20 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/accounts.py:21 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/accounts.py:22 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/events.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/events.py:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/events.py:10 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/events.py:11 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/events.py:12 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/events.py:14 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/src/aevyra_api/commercial/fulfillment.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/fulfillment.py:6 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/fulfillment.py:10 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/fulfillment.py:11 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/fulfillment.py:13 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/src/aevyra_api/commercial/fulfillment.py:55 | 1 | intentionally retained | Scoring fixture bytes: changing them changes deterministic scores |
| services/api/src/aevyra_api/commercial/models.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/models.py:20 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/orders.py:3 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/orders.py:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/orders.py:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/orders.py:15 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/state.py:1 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/commercial/state.py:3 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/config.py:16 | 3 | intentionally retained | Existing database identity / development-password rejection guard |
| services/api/src/aevyra_api/config.py:49 | 1 | intentionally retained | Existing database identity / development-password rejection guard |
| services/api/src/aevyra_api/credits/analysis.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/analysis.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/analysis.py:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/analysis.py:10 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/analysis.py:11 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/analysis.py:13 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/src/aevyra_api/credits/codes.py:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/codes.py:15 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/codes.py:16 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/codes.py:17 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/ledger.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/ledger.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/models.py:19 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/credits/models.py:20 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/database.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/logging.py:19 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/src/aevyra_api/logging.py:36 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/src/aevyra_api/main.py:12 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:15 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:16 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:17 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:18 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:19 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:20 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:21 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/main.py:83 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/src/aevyra_api/main.py:92 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/src/aevyra_api/models.py:6 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:12 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:15 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:16 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:17 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:18 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:19 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:26 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/operator.py:27 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/payments/future.py:3 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/payments/mock.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/payments/mock.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/payments/mock.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/payments/provider.py:6 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/retry_fulfillment.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/retry_fulfillment.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/retry_fulfillment.py:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/retry_fulfillment.py:10 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/retry_fulfillment.py:11 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/retry_fulfillment.py:12 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/retry_fulfillment.py:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/accounts.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/accounts.py:19 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/accounts.py:24 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/accounts.py:32 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/accounts.py:33 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/accounts.py:34 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/accounts.py:35 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/accounts.py:36 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/accounts.py:37 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/commercial.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/commercial.py:17 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/commercial.py:18 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/commercial.py:19 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/commercial.py:20 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/commercial.py:21 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/commercial.py:22 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/health.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/health.py:8 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/src/aevyra_api/routes/scoring.py:1 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/scoring.py:2 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/src/aevyra_api/routes/scoring.py:3 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/conftest.py:6 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/conftest.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/conftest.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/conftest.py:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/conftest.py:10 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/conftest.py:11 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/conftest.py:12 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/conftest.py:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_api.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_api.py:6 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_api.py:36 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/tests/test_brand_compatibility.py:1 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_brand_compatibility.py:9 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_brand_compatibility.py:12 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_commercial.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_commercial.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_commercial.py:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_commercial.py:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_commercial.py:15 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_commercial.py:16 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_commercial.py:17 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_commercial.py:18 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_commercial.py:22 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_commercial.py:265 | 1 | intentionally retained | Existing database/user credentials or compatible setup example |
| services/api/tests/test_credit_recovery.py:6 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credit_recovery.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credit_recovery.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credit_recovery.py:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credit_recovery.py:28 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_credit_recovery.py:32 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_credit_recovery.py:33 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_credits.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credits.py:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credits.py:10 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credits.py:11 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credits.py:12 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credits.py:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credits.py:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credits.py:15 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credits.py:24 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_credits.py:110 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_credits.py:276 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_dependencies.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_dependencies.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_dependencies.py:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_deployment_config.py:6 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_deployment_config.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_deployment_config.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_deployment_config.py:15 | 2 | intentionally retained | Existing database/user credentials or compatible setup example |
| services/api/tests/test_deployment_config.py:27 | 2 | intentionally retained | Existing database/user credentials or compatible setup example |
| services/api/tests/test_deployment_config.py:72 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_deployment_config.py:83 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_deployment_config.py:100 | 1 | intentionally retained | Stable health/logging identity for monitoring compatibility |
| services/api/tests/test_migrations.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_migrations.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:10 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:11 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:12 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:15 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_commercial.py:28 | 1 | intentionally retained | Existing isolated PostgreSQL test-schema namespace |
| services/api/tests/test_postgres_commercial.py:59 | 1 | intentionally retained | Existing isolated PostgreSQL test-schema namespace |
| services/api/tests/test_postgres_commercial.py:74 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_postgres_commercial.py:100 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_postgres_credits.py:6 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:7 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:8 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:9 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:10 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:11 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:12 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:13 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:14 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:15 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:16 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/api/tests/test_postgres_credits.py:100 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/api/tests/test_postgres_credits.py:126 | 1 | intentionally retained | Persisted product slug/name, presentation alias or compatibility assertion |
| services/inference/pyproject.toml:15 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/inference/src/aevyra_inference/engine.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/inference/src/aevyra_inference/mock.py:3 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/inference/src/aevyra_inference/mock.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/inference/tests/test_engine.py:4 | 1 | intentionally retained | Stable Python import/CLI namespace |
| services/inference/tests/test_engine.py:5 | 1 | intentionally retained | Stable Python import/CLI namespace |

## Ignored/generated text matches

| Group | Occurrences | Classification |
| --- | ---: | --- |
| .next | 792 | intentionally retained compatibility/cache artifacts |
| .venv | 25 | intentionally retained compatibility/cache artifacts |
| ignored local environment files (values redacted) | 11 | intentionally retained compatibility/cache artifacts |

Total scanned textual occurrences (excluding audit self-references): 1126.
