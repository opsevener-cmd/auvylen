# Phase 4A completion report — 2026-10-11

Post-interruption check on 2026-10-12: source and development branch remain intact.
Docker Desktop was restarted, the same disposable volume set was reused, the migration
gate again exited 0, and all six running cloud-simulation services were healthy. The
test counts below are from the completed verification runs, not a claim that the entire
suite was rerun during this recovery check.

## Confirmed baseline and recovery

The actual existing repository was audited and continued in place. Next.js, FastAPI,
PostgreSQL, Redis, Caddy, Compose, accounts/sessions, Credits, redemption, migrations,
the mock registry and the retained commercial flow all existed. There were also unfinished
public-pilot changes. No replacement application was created. Git had no commits and all
source was untracked; `codex/phase4a-cloud-ready` is the current development branch.
No files were globally renamed or migration history rewritten.

All 104 pre-existing backend/inference tests passed with real PostgreSQL/Redis, and the
25 pre-existing frontend tests passed. Existing commercial and Credit browser regressions
also passed after the changes. The audit, implementation boundaries, interfaces and
exact local/future-VPS commands are in [phase4a.md](phase4a.md).

## New files

- `.env.cloud.example`, `docker-compose.cloud.yml`, `docker-compose.cloud.local.yml`
- `services/api/migrations/versions/0004_research_jobs.py`
- `services/api/src/aevyra_api/migrate.py`
- `services/api/src/aevyra_api/research/__init__.py`
- `services/api/src/aevyra_api/research/models.py`
- `services/api/src/aevyra_api/research/jobs.py`
- `services/api/src/aevyra_api/research/storage.py`
- `services/api/src/aevyra_api/research/worker.py`
- `services/api/src/aevyra_api/research/operator.py`
- `services/api/src/aevyra_api/routes/research.py`
- `services/api/tests/test_cloud_config.py`, `test_research.py`, `test_postgres_research.py`
- `services/inference/src/aevyra_inference/providers.py`, `custom.py`
- `services/inference/tests/test_providers.py`
- `packages/contracts/src/aevyra_contracts/research.py`
- `apps/web/src/lib/research-api.ts`, `research-api.test.ts`
- `apps/web/src/components/research-page.tsx`, `apps/web/src/app/research/page.tsx`
- `apps/web/playwright.cloud.config.ts`, `apps/web/cloud-tests/research.spec.ts`
- `scripts/create-cloud-test-env.py`, `deploy-cloud.sh`, `backup-cloud.sh`, `verify-cloud-storage.py`
- `docs/phase4a.md`, `cloud-backups.md`, this report

## Modified files

- `.gitignore`, `.dockerignore`, `.github/workflows/ci.yml`
- `AGENTS.md`, `README.md`, `docs/architecture.md`, `docs/deployment.md`,
  `docs/production-security.md`, `docs/verification.md`
- `services/api/Dockerfile`, `apps/web/Dockerfile` (digest-pinned inputs; non-root runtime;
  private directory ownership; separate optional checks stage)
- `services/api/migrations/env.py` (register the new metadata)
- `services/api/src/aevyra_api/config.py`, `main.py`
- `services/api/src/aevyra_api/routes/accounts.py`, `commercial.py` (cloud aggregate
  rate-limit policy and checkout gate; no change to payment/event/ledger services)
- `packages/contracts/src/index.ts`
- `apps/web/src/lib/environment.ts`, `apps/web/src/app/layout.tsx`, `page.tsx`,
  `analyze/page.tsx` (research navigation; cloud checkout disabled)

`0004_research` follows `0003_credits`, adding only `research_access` and `research_jobs`.
No existing product, order, payment, account, wallet, code or analysis schema changed.
No destructive migration was run. Tests use isolated schemas or the separate disposable
cloud project. Previous migration files and stable technical identifiers are retained.

## Verification actually executed

| Check | Result |
| --- | --- |
| Full backend/inference suite with infrastructure | 117 passed, zero skipped |
| Default backend suite | 105 passed, 12 opt-in infrastructure skips; all 12 passed above |
| Frontend unit tests | 27 passed |
| Existing development browser tests | 2 passed: original checkout and Credit/redemption flows |
| New cloud HTTPS browser test | 1 passed on final rebuilt images |
| Ruff lint | Passed |
| Ruff formatting | Passed for all checked source files |
| Mypy | 46 source files passed |
| ESLint / TypeScript | Passed |
| Next.js production build | Passed on host and in production Docker image |
| API/web production images | Built successfully from digest-pinned inputs and locked dependencies |
| Production + cloud Compose validation | Passed; only proxy publishes ports; data network internal |
| Migration startup gate | Exited 0, Alembic check reports no drift |
| Unauthorized migration container | Refused APPLY_MIGRATIONS=false with nonzero exit |
| Service health | PostgreSQL, Redis, API, web, Caddy and CPU worker healthy |
| Application image isolation | API UID 10001; env and exports absent; private volumes absent from web/proxy |
| Shell helpers | bash syntax checks passed |
| Restart/persistence/restore drill | Passed for database, job results, balances, private artifact hashes and Redis AOF |

The browser test verified HTTPS Secure/HttpOnly/Lax sessions, register/login/logout,
redemption of ten Credits, one-Credit Mock Analysis, operator-gated free research,
unchanged balance 9 after research, saved synthetic result, and recovery after restarting
PostgreSQL/Redis/API/worker. Browser requests stayed on the site origin. Payment
simulation and source/env/Git/export/model-file probes returned 404.

Six concurrent same-key research submissions produced one durable job, and six competing
workers produced one lease. Expired leases recover; stale tokens cannot overwrite a newer
completion. Retries are bounded. Disabled/revoked research authorization and ownership
checks are enforced. Existing financial concurrency/refund/idempotency tests still pass.

The storage drill used synthetic byte strings, not photos or model weights. It verified
upload/checkpoint volume persistence, restored a PostgreSQL dump into a separate database,
and restored tar archives into separate volumes, validating matching hashes and UID 10001
access. Backup/restore needed explicitly confined offline read/chown permissions; normal
application capabilities remain dropped. Failed drill archives are not certified backups.
The production backup helper emits a completion checksum manifest and keeps failures partial.

Windows's old uv trampoline and generated mypy launcher were blocked by application
control. Verification used an ignored `.venv-phase4a` built with the installed Python and
locked dependencies; mypy was invoked as `python -m mypy`. No OS security was disabled.
These host launcher limitations do not affect the Linux container runtime. CI gained a
Linux cloud-research job but was not executed remotely: there is no pushed release here.

## Deployment status and remaining work

The disposable stack is `auvylen-phase4a-test`, with only loopback 18080/18443 bindings.
It can be stopped using the documented Compose `down` command without deleting volumes.
Its protected `.env.cloud.local` is ignored and should be retained for those volumes.
All cloud configuration is portable; no Windows computer is a production dependency.
No VPS, public tunnel, public deployment, real payment provider or real AI model was used.

Custom dataset/ratings/pairwise/checkpoint contracts, private artifact storage and durable
workers are implemented foundations. Custom image import, persistent annotation services,
training algorithms and real custom inference remain unimplemented. ComboLoss, FPEM,
FACLIP and SwinGFVQA-ca are independent plugin slots and explicitly unavailable without
reviewed adapters/dependencies/weights. No synthetic fallback is used for them. Mock
research is allowed only outside production and is visibly labelled synthetic.

Phase 4B needs a reviewed committed release, VPS/domain, off-host backups/monitoring,
confirmed upstream FACLIP/SwinGFVQA-ca identities, license/data provenance review,
authorized image ingestion/consent/retention and decoding limits, persistent annotation
storage, a real custom trainer, long-job lease renewal/cancellation/checkpoint resume,
and separately locked model worker images. GPU/private artifact transport is future work,
not a CPU foundation prerequisite. Commercial billing is not the next dependency.
