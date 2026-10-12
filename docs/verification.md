# Verification history and Phase 3 status

## Phase 3 verification — 2026-10-06

- Backend/live infrastructure: **88 passed, zero skipped**, including all prior Phase 0–2
  tests. New account tests cover register/login/logout, Argon2id storage, session expiry,
  disabled users, CSRF/origin, rate limits, generic redemption errors, strict payloads,
  ownership and production credit-analysis protection. No test depends on a real AI model.
  Default non-integration invocation also passed: 78 passed, ten opt-in infrastructure tests
  skipped; those same ten passed in the full --integration run above.
- Real PostgreSQL races: eight different users redeeming one code yielded one redemption,
  one ledger credit and total balance 10. Eight analysis submissions with one Credit yielded
  one debit/result/execution; same-key concurrent retries returned the same result. Eight
  duplicate failure handlers yielded one refund. Ledger/cache totals matched throughout.
- PostgreSQL rejects ledger UPDATE, DELETE and TRUNCATE. Positive/debit/idempotency limits,
  insufficient funds, backend credit cost, synthetic persistence and exactly-once refunds pass.
  CSV generation verified exact quantity, uniqueness, keyed digests and absence of plaintext
  codes in stored code records. Exports are ignored by Git and Docker; account browser traces
  are disabled to avoid collecting credentials/codes.
  Interrupted post-deduction fulfillment resumes without double spend/execution; downgrade
  refuses issued batches even when no customer accounts exist yet.
- Frontend: **18 unit tests passed**. Development browser: **2 passed**, covering original
  order/payment flow and registration → zero balance → operator CSV → redeem ten → spend one
  → saved synthetic result → nine balance → +10/-1 history → logout/login.
- Ruff lint/format, strict mypy, ESLint, TypeScript and frontend production build passed.
  Both non-root production images build with the updated Argon2 dependency and no exports/env.
- Development PostgreSQL was backed up before migration, and 0003_credits upgraded/checks
  without drift. The local production-simulation database was separately backed up and
  migrated/checks using the built API image. Original migrations and persisted IDs remain intact.
- HTTPS production account/redemption test passed: Secure/HttpOnly/SameSite cookies, zero
  initial balance, +10 redemption; mock credit analysis returns 404 without deduction. Original
  HTTPS readiness/proxy and production checkout protection tests also pass (**3 applicable
  tests passed**, one staging-only test skipped). Local-only TLS override remains loopback.
- HTTPS private staging: **3 applicable tests passed**, one production-only test skipped.
  Both credit-funded analysis (10 → 9) and original mock checkout completed with saved
  synthetic results. The stack was restored to production; all five services are healthy.
- No real provider/model, platform API integration or public tunnel/deployment was added.
  Password recovery, email verification, trusted-proxy rate tuning and launch retention/support
  policies remain pilot limitations. See accounts.md, credits.md and redemption-codes.md.

Earlier results below are historical snapshots, not current test counts.

## Controlled brand rename — 2026-10-06

The provisional brand is Auvylen. npm/Python distribution labels, frontend branding, API
title, Docker image labels and new backup filenames were renamed. Migration files and
scoring/payment behavior are unchanged. Stable identities are listed in brand-rename.md.
The new brand compatibility test verifies the unchanged stored product name, slug, price
and public order prefix while API responses display the renamed brand.

Backend/integration tests: 62 passed, zero skipped. Frontend unit tests: 15 passed.
Ruff formatting/lint, mypy, ESLint, TypeScript and production frontend build passed.
Production Compose configuration validation and both renamed image builds passed. Development
checkout passed; HTTPS staging checkout and production lockdown each passed their two applicable
browser tests (the other mode's test is intentionally skipped). Existing volumes were reused,
all five services remain healthy, and Alembic reports no drift. The local stack is left in
production mode. See brand-rename.md for the occurrence ledger; earlier evidence is historical.

## Phase 2 verification — 2026-10-06

- Backend and live infrastructure suite: **61 passed, zero skipped**. Existing Phase 0/1
  tests remain included. New tests cover deployment settings, production route protection,
  staging commercial flow and sanitized server exception logging.
- Frontend: **15 unit tests passed**; ESLint, TypeScript and host production build passed.
  Ruff lint/format and strict mypy passed. Runtime npm audit: zero vulnerabilities.
- Multi-stage Linux API/web images built successfully with Docker Desktop's Linux engine.
  API and web run as non-root; API runtime has no pytest/Ruff or root .env file.
  A later package-registry timeout was resolved by retrying with a persistent build cache;
  final images passed both staging and production checks. The stack was left in production.
- Isolated production Compose project aevyra-phase2: five services healthy. Only Caddy
  publishes ports (loopback 8080/8443 for this simulation); API, web, PostgreSQL and Redis
  have no host port bindings. Public template publishes only TCP 80/443.
- Online migrations and Alembic schema check passed within the API image at 0002_commercial.
  No Phase 2 schema changes were required.
- HTTPS production browser checks: **2 passed**, staging-only test intentionally skipped.
  Verified web/API/readiness, 1 MB body limit (413), removed Server header, hidden checkout
  and rejected products/order/simulation API calls (404).
- HTTPS staging browser checks: **2 passed**, production-only test intentionally skipped.
  Full mock checkout persisted a COMPLETED order and synthetic result in PostgreSQL.
  The original development browser test also passed on host ports 8001/3001.
- HTTP redirects to HTTPS; redirect Server header removed. Both Caddy templates validate.
  TLS certificate validation succeeded against the local CA using curl --cacert (Windows
  local-CA revocation checking disabled), without changing system trust. Browser simulation
  permits only localhost and accepts the private test CA. No public ACME issuance was tested.
- Redis outage produced 503 with a safe unavailable dependency; recovery returned 200.
- Backup script passed Bash syntax and execution checks. Binary pg_dump restored to a
  separate temporary database with migration revision, one order and one result intact.
  The restore-check database was removed. PostgreSQL restart preserved those live rows.

No public VPS/domain is configured, so external DNS, certificate issuance and remote-host
operations remain to be verified during actual deployment. CI deployment checks were added;
no remote CI execution was dispatched. Known development-tool advisory below is unchanged.
Phase 3 has not started. No real payment provider or facial scoring model is integrated.

## Phase 1 verification — 2026-10-06

The commercial skeleton adds `0002_commercial`, six commercial tables, mock provider
adapters, event idempotency, an isolated fulfillment service, and browser routes.

- Backend suite with `uv run pytest --integration`: **48 passed, zero skipped**.
  This includes Phase 0 regression tests, PostgreSQL/Redis connectivity, online migration
  and schema checks, the commercial HTTP flow, and eight concurrent duplicate callbacks
  producing one engine execution, analysis and result.
- Frontend unit tests: 10 passed.
- Strict mypy, frontend ESLint and TypeScript checks passed. Production build passed.
- The mobile browser checkout journey passed using the normal PostgreSQL API and a
  production Next.js build (Chrome, 390px viewport, isolated app ports 8001/3001).
  It checks the persisted COMPLETED order, backend price and explicitly synthetic result.
- WSL 3.0.1 and Docker Desktop 4.94.0 are installed. Docker 29.8.2 runs Linux containers;
  Compose v5.5.1 completed `docker compose up -d --wait`. Both PostgreSQL 18 and Redis 8
  are healthy; direct `pg_isready` and Redis `PING` succeeded.
- Online Alembic upgrade reached `0002_commercial (head)`; `alembic check` reported no
  new upgrade operations. No application database fallback was used.
- Host API `/health` and `/ready` returned 200, with database and Redis both `ok`.
  The frontend `/` and `/status` returned 200; `/status` showed the API connected and ready.
- The production build initially encountered sandbox path access denial. Rerunning
  outside the sandbox passed without source changes.

Phase 1's commercial flow and infrastructure checks pass. No real provider,
authentication, uploads or real model exists. Phase 2 verification is recorded above.

## Phase 0 historical verification

The following records earlier Phase 0 checks before Docker was installed. The live
PostgreSQL/Redis verification above supersedes the historical infrastructure blocker.
This records local evidence, not a production certification.

## Successful checks

- Backend unit tests: **16 passed, 3 integration tests skipped**. Health, readiness
  success/failure combinations, CORS, safe errors,
  production configuration, driver probes, deterministic mock scores, registry lookup,
  duplicate rejection and production policy enforcement.
- Frontend tests: **6 passed**. Valid readiness, unhealthy dependencies, network errors and malformed
  or inconsistent API responses.
- Ruff lint and formatting, strict mypy, ESLint with zero warnings, TypeScript type check.
- Next.js production build with static `/` and dynamic `/status`.
- API and frontend startup smoke checks. HTTP 200 for `/health`, engine metadata, `/`,
  and `/status`. The status page reached the API and rendered unavailable dependencies.
- Alembic offline PostgreSQL upgrade SQL generated successfully with a single head
  (`0001_foundation`). This does not prove an online migration succeeded.

## Historical infrastructure blocker (resolved)

At the earlier Phase 0 check, Docker CLI/Desktop, PostgreSQL and Redis were unavailable. Live
integration tests (**3 failed, 16 unit tests passed**) and online Alembic upgrade/check
were attempted and failed to connect.
`/ready` correctly returned 503 with both dependencies unavailable. The unit test run
explicitly skips real infrastructure tests. CI is configured with PostgreSQL 18 and
Redis 8, but no remote CI run was dispatched or observed during this implementation.

To complete the outstanding verification on a Docker-enabled host:

```sh
docker compose up -d --wait
uv run alembic -c services/api/alembic.ini upgrade head
uv run alembic -c services/api/alembic.ini check
uv run pytest --integration
```

With both apps running, `/ready` must return 200 and `/status` must show all services
healthy. Do not mark the complete definition of done as satisfied until this is verified.

## Dependency advisory

`npm audit` reports five high-severity dependency entries representing the same upstream
development-tool chain: `eslint-config-next` → `@next/eslint-plugin-next` → `fast-glob`
→ `micromatch` → `braces`. The root advisory is
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm): deeply nested
patterns can exhaust the stack. The current published `braces` release (3.0.3) remains
affected. No patched release was available at implementation time. This chain is used
by lint tooling, not by the production application's runtime dependency tree.

The suggested automatic fix downgrades `eslint-config-next` to 14.2.35, which is not
appropriate for this Next.js 16 foundation. No blanket force-fix or advisory suppression
was applied. Monitor the upstream patch and update the lock. `npm audit --omit=dev` is
the separate runtime audit command; full audit remains nonzero until patched. The runtime
audit passed with zero vulnerabilities.

ESLint 10 is current but some React plugin rules in Next.js's config still use legacy
ESLint APIs. The official `@eslint/compat` adapter keeps those rules active. Remove the
adapter once upstream plugins support the current API directly.

## Phase 1 handoff

- Keep inference as a reusable Python boundary; choose worker/network transport only
  after workload and retry requirements are defined.
- Mock production execution remains disabled. Its commercial flag provides no approval
  for future real models. Registry execution requires an explicit production context.
- No scoring execution route exists. Before introducing one, define authorization,
  input validation, resource limits and provenance evidence.
- The initial table is operational only; design product tables via future migrations.
- Wire contracts are explicit Python/TypeScript definitions; update both when they change.
- Production deployment, privacy controls and financial invariants need their own phases.
# Historical Phase 4A verification

See [the Phase 4A report](phase4a-report.md) for the audited baseline, file manifest,
exact test evidence, persistence/restore drill and known limitations. The final full
infrastructure suite passed **117 tests**; frontend passed **27 tests**, old browser flows
passed **2 tests**, and the cloud HTTPS research/credit/restart flow passed **1 test**.
Ruff/formatting/mypy/ESLint/TypeScript/build/image/Compose/migration checks passed.
No public deployment is claimed. The earlier Phase 0–3 records remain historical evidence.

# Cloud-transition recovery — 2026-10-12

The current session is local Windows, so the master instruction permits only recovery
and cloud preparation. Thirteen project-specific containers were inspected and stopped;
all fifteen persistent volumes and matching env files were retained. Source inspection
confirmed the Phase 4A components and migration chain; it does not claim runtime success.

Lightweight recovery verification covers Git candidate/secret exclusion, original
application/infrastructure file hashes, Python migration syntax/chain, guarded shell
setup syntax and refusal on Windows, and commit contents. No application dependency
installation, backend/frontend regression suite, Docker build, training or public
deployment ran in this recovery session. The historical test counts above have not
been refreshed. Full checks are prepared for the remote environment in
[cloud-development.md](cloud-development.md). See
[recovery-cloud-transition.md](recovery-cloud-transition.md) for measured resource
usage, file changes, preserved data and the exact cloud-access blocker.


## 2026-10-12 — remote Linux Phase 4B dataset increment

Fresh verification in the managed Debian 13 cloud environment: baseline 117 backend/
infrastructure, 27 frontend and two development browser tests passed before implementation.
Final increment: 134 backend/infrastructure tests, 30 frontend tests, three development
browser tests and two HTTPS cloud tests passed. Ruff, formatting, mypy, ESLint, TypeScript,
host/production Docker builds and migration drift checks passed. All six cloud services
reached healthy state. Private images and annotations survived API/worker recreation;
worker deletion removed the files. Existing financial/research regressions remain passing.

See [Phase 4B progress](phase4b-progress.md) for limits, cloud portability fixes, exact
verification scope and remaining work. Real training, checkpoints and custom predictions
are not implemented or claimed by this milestone. No public deployment took place.
