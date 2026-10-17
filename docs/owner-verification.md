# Owner administration verification

Verification date: 2026-10-17 (Asia/Shanghai). Branch: `codex/owner-god-provisioning`.
This extends existing draft [PR #1](https://github.com/opsevener-cmd/auvylen/pull/1),
starting from its `4c142c6` implementation above the private-preview commit `290d664`.
No merge, public deployment, purchase or operation against the user's live Codespace was performed.

## Delivered implementation

| Area | Files / behavior |
| --- | --- |
| Persistent identity | `credits/models.py`, `accounts.py`, `owner.py`; reserved registration, one Owner, Argon2id interactive init/rotation/recovery, normal opaque sessions |
| Policy | `entitlements.py`, `config.py`; generic free-product entitlement with independent provider/privacy gates and bounded Owner quotas |
| Durable free usage | `admin_models.py`, `credits/analysis.py`; immutable product-specific free funding records, retry conflicts, no fictitious debit/refund |
| Administration | `administration.py`, `routes/owner.py`, `main.py`; protected overview/user/ledger/grant/batch/job/audit endpoints, fresh authentication, transactional idempotency |
| Existing operator tools | `operator.py`, `research/operator.py`, `credits/codes.py`; preserve existing financial primitives and add terminal-attributed audit events |
| Research safety | `research/jobs.py`, `research/worker.py`, `preferences/service.py`, `preferences/training.py`; global live-job cap, heartbeat, per-role bounded storage/queues, retained-model visibility |
| Website | `/owner/page.tsx`, `owner-dashboard.tsx`, `owner-api.ts`, proxy allowlist, account/preference components; protected responsive administration, role/free-use indicator, controlled code export |
| Contracts | Python `accounts.py` / `owner.py`, TypeScript `index.ts`; strict roles and bounded mutation fields |
| Migrations | Existing `0007_owner_role` (format only), new `0008_owner_administration`, metadata imports; role checks, immutable identity/audit/free-usage guards |
| Operations | `scripts/codespaces-preview.py` init/rotate/recover commands; [approved same-Codespace rollout](owner-account.md) |
| Verification | Owner unit/security tests, real PostgreSQL concurrency/migration/terminal/capacity tests, frontend tests and isolated HTTPS browser/backup tests |

No numerical learning algorithm, pretrained checkpoint, provider plugin, payment integration,
existing private model format or production image was replaced. MobileNetV3-Small and the
handcrafted baseline remain independent of third-party scoring providers.

## Environment and isolation

Managed remote Linux cloud, x86_64, cgroup CPU limit 2 and memory limit 8 GiB, approximately
32 GiB filesystem. Tests used real PostgreSQL 18 and Redis 8. The existing Codespaces image
was reused; **no Docker images were built** for this milestone. Next.js production builds
ran in this remote environment. The HTTPS test edge bound only `127.0.0.1:19443`; API,
PostgreSQL and Redis had no published test-preview ports.

A platform restart interrupted one full test run. Source changes and persistent volumes
survived. The test preview resumed with its original database/pepper/model artifacts. The
interrupted run is not counted as a pass; checks were run again after recovery.

The early terminal test exposed that the existing connection factory overrides URL
connection options. The fixture was corrected to explicitly isolate its generated PostgreSQL
schema via a test-only connection listener. A random synthetic Owner created during that
first attempt remains confined to the remote development database; it was not provisioned
in the user's Codespace. No actual owner password was supplied, committed or reused.
Subsequent terminal initialization tests verify the isolated schema and do not mutate the
development database's accounts.

## Executed checks

The following checks were executed successfully. Synthetic fixtures validate
software correctness, privacy/financial boundaries and persistence, not attractiveness accuracy.

| Check | Result |
| --- | --- |
| `OPENBLAS_NUM_THREADS=1 uv run pytest --integration --pretrained -q` | 171 passed, no skips, 115.61 seconds |
| Additional `test_pr1_owner_upgrade_preserves_password_and_distinguishes_free_funding --integration` | 1 passed, 1.11 seconds; existing PR #1 Owner/password/free-funding compatibility |
| `npm test` | 35 passed |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm run build` | Production build passed; `/owner` included |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed |
| `uv run mypy` | 66 source files passed |
| HTTPS Playwright Owner workflow + encrypted backup | 2 passed, 46.7 seconds |
| Incremental upgrade + repeat upgrade + `alembic check` | Passed on real PostgreSQL |
| Injected migration failure | Rolled back schema and version marker; prior rows preserved |

The HTTPS browser flow exercised 390px mobile and 1365px desktop viewports: ordinary-user
rejection, Owner login/cookies, overview/provider status, CSRF/Origin denial, promotional
Credits and reconciliation, disable/restore and old-session revocation, research grant/revoke,
code export/redemption/disable, audit inspection, fresh password login, real MobileNet
training and retraining from synthetic numerical annotations, unseen-image prediction,
zero Credit balance, and application restart persistence. It also checks mobile document
width. The backup test decrypted the existing encrypted backup format internally, compared
private file bytes, restored a disposable database, and checked the Owner, immutable guard,
audit records, ready models and wallet/ledger consistency. No secrets or private file bytes
were printed to the test logs.

Security/backend tests cover reserved/case-normalized signup, forged role fields and session
cookies, duplicate and concurrent bootstrap, an occupied reserved login, actual interactive
hidden password confirmation (including mismatch rejection), password verification/rotation/
recovery, session expiry, missing/stale auth, CSRF and exact Origin, unavailable/production
synthetic provider refusal, cross-user dataset/image/model denial, and revocation fencing.
Four simultaneous bootstrap attempts produce exactly one Owner. Six identical free-analysis
requests run inference once with no ledger entry; six promotional-grant requests create one
entry and one success audit. Concurrent batch creation discloses one set of codes once.
PostgreSQL rejects mutation/truncation of audit and free-funding history. Existing immutable
Credits/refund/concurrency tests remain in the full suite.

## Data preservation and capacity evidence

A generated PostgreSQL schema at `0006_custom_models` was seeded with an existing password
hash, session, wallet/ledger, research grant, project, dataset, image metadata/rating, research
job and model/checkpoint reference. Every pre-existing table's rows were compared after
upgrading through `0007` and `0008` twice. Only the default `user` role was added to old
accounts. Old credentials/session remained valid and private fixture bytes were unchanged.
An injected error after migration began restored the old version marker and schema. The
separate encrypted restore test exercised actual trained model artifacts and verified bytes.

The Owner capacity test actually ingested **1,000 generated synthetic images** into private
storage and PostgreSQL, rejected the 1,001st, and rejected a training request with 501 rated
images before scheduling. Existing full-worker capacity tests still exercise 500-image
training for both real MobileNet embeddings and the handcrafted baseline. The Owner's
300-version listing is tested with metadata fixtures; it is not a benchmark of 300 model
training jobs. No 2 GiB saturation test was performed. The default global concurrent-job cap
of one is tested with four parallel claimers; only one receives a live lease. The optional
cap of two has not been capacity-qualified for the preview.

## Review findings and limits

- PR #1's free-analysis retry originally failed to bind its product, and refund logic inferred
  free funding from the current role. Both use a durable immutable funding decision now.
- PR #1 lacked matching ORM uniqueness metadata, role constraints, an immutable identity guard,
  administration/auditing, fresh-auth mutations, password rotation/recovery and Owner quotas.
  Those are implemented, preserving ordinary-user financial and privacy boundaries.
- New privileged commands revalidate the account and current session under the Owner row lock.
  Positive grant and audit commit together; raw codes never enter audit/read endpoints.
- Failure auditing is best-effort only when dependencies or the bounded failure-event budget
  are exhausted; the denied operation stays denied. Successful mutations require their audit
  transaction. Database-superuser access can alter guards; there is no external tamper-proof
  audit sink or separate least-privilege database-role rollout in this milestone.
- The initial UI/static runs caught strict fixture selectors, typing/formatting and fixture
  isolation issues; these were corrected. Final results above refer to executed reruns.
- Browser MFA/passkeys and self-service ordinary-user recovery are not implemented. Owner
  recovery is explicit deployment-terminal control with a new secret and session revocation.
- The user’s live GitHub gateway, quota/billing configuration and running Codespace were not
  changed or retested. Deployment remains a separate approved action using the existing private
  port. No automatic Owner provisioning is performed by setup/start/migrations.
- No new real-face evaluation, pairwise trainer, unavailable GitHub engine, commercial provider
  or payment gateway was introduced. Those capabilities must still be independently installed,
  licensed, implemented and verified. Synthetic model tests imply no real facial accuracy.

Use [Owner initialization and approved deployment instructions](owner-account.md). Keep an
off-Codespace encrypted backup and its passphrase protected; do not reset volumes or merge
this branch without review and explicit approval.
