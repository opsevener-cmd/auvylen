# Phase 3 implementation report

Scope: accounts, immutable Credits and channel-neutral redemption; local/private testing only.
Existing order/payment provider architecture, PostgreSQL/Redis deployment, legacy identifiers
and scoring policy are preserved. No real providers/models, upload, commerce API or tunnel.

## Files created

- services/api/src/aevyra_api/accounts.py and operator.py.
- services/api/src/aevyra_api/credits/__init__.py, models.py, ledger.py, codes.py, analysis.py.
- services/api/src/aevyra_api/routes/accounts.py.
- services/api/migrations/versions/0003_accounts_credits_redemption.py.
- services/api/tests/test_credits.py, test_postgres_credits.py and test_credit_recovery.py.
- packages/contracts/src/aevyra_contracts/accounts.py.
- apps/web/src/lib/account-api.ts and account-api.test.ts.
- apps/web/src/components/account-pages.tsx.
- apps/web/src/app/register/page.tsx, login/page.tsx, account/page.tsx, redeem/page.tsx,
  history/page.tsx and api/[...path]/route.ts.
- apps/web/e2e/credits.spec.ts and deployment-tests/accounts.spec.ts.
- docs/accounts.md, credits.md, redemption-codes.md and this report.

## Files modified

- .dockerignore, .gitignore, .env.example, .env.production.example, docker-compose.prod.yml.
- .github/workflows/ci.yml, conftest.py, uv.lock, AGENTS.md and README.md.
- services/api/pyproject.toml, migrations/env.py, src/aevyra_api/config.py, main.py,
  commercial/models.py and routes/commercial.py.
- packages/contracts/src/index.ts.
- apps/web/playwright.config.ts, src/app/layout.tsx, analyze/page.tsx and
  result/[analysisId]/page.tsx.
- docs/architecture.md, deployment.md, production-security.md, verification.md and
  brand-rename.md; scripts/audit-brand.py keeps the cosmetic rename evidence historical.

Ignored local configuration now holds generated peppers. Ignored exports/ contains pilot
and browser exports; backups/ contains pre-migration development and simulation dumps.
No secrets or exported codes belong in source control or container images. No existing
files/import directories or previous migrations were renamed.

## Migration and database tables

Revision 0003_credits follows 0002_commercial. New tables: users, sessions, wallets,
credit_transactions, redemption_batches, redemption_codes, redemptions. The migration adds
Product.credit_cost and nullable account ownership/request key to analyses, retaining existing
order ownership and enforcing exclusive funding. PostgreSQL trigger protections reject
ledger updates/deletes/truncation. Original product rows, IDs and migration history survive.

Backups were made before upgrading both local PostgreSQL stacks. Alembic checks show no drift.
Downgrade is intentionally guarded; prefer reviewed compatible releases or backup restore
after accounts or issued batches exist. Do not run old staging APIs against account-owned analysis data.

## Exact manual flow

Start local PostgreSQL/Redis, migrate, run API and web using README. Use
http://localhost:3000 as the browser origin (or update CORS_ORIGINS exactly).

1. /register: choose a username/email-like identifier and a password of 12–128 characters.
   /account shows 0 Credits. /account Sign out and /login exercise server-side sessions.
2. From repository root:

```sh
uv run python -m aevyra_api.operator generate-batch --name "Pilot 10 Credits" --channel manual --sku pilot-10 --credits 10 --quantity 10 --output ./exports/pilot-10.csv
```

The ten-code batch has ten Credits per code. Output is exports/pilot-10.csv, not application
logs. Existing files cannot be overwritten. Run batch-summary using the printed batch ID
before delivery; open the protected CSV locally to obtain a code.

3. /redeem: enter one code, click Redeem, see 10 Credits added and balance 10.
4. /analyze while signed in: Cost 1 Credit, click Run Analysis. The saved result explicitly
   says Development / Synthetic Result. /account now shows 9 Credits and +10 REDEMPTION,
   -1 ANALYSIS. /history links to the result.

The documented pilot export was actually generated during verification with batch ID
batch_0e457b01207b4f298f9dbb53aab242dc. Protect its CSV; regenerate to a new filename if needed.

## Results and limitations

88 backend/infrastructure tests and 18 frontend unit tests passed. Two development browser
tests passed. Three applicable HTTPS tests passed in each mode; one test for the opposite
mode was intentionally skipped each time. Ruff lint/format, mypy, frontend lint/TypeScript,
frontend production build, both Docker builds, Compose validation and migration checks pass.

Real PostgreSQL tests prove one concurrent redemption, no wallet overspending, one analysis
execution for identical retries, and one compensating refund. Auth/ownership/CSRF, Redis
limits, hash-only code/session storage, no negative balances and production gates pass.
The local simulation is restored to production with all five services healthy.

Pilot limitations: no verified email/password recovery, no public launch, no real inference,
conservative shared proxy IP limits, no worker or complete retention/support policy. Protect
exports/peppers and establish operator delivery/support procedures before serving customers.
If deduction committed but the process/storage failed, the analysis remains recoverable;
resume it using the documented operator command after fixing infrastructure. No public
tunnel or future phase is started automatically.
