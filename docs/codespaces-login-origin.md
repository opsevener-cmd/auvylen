# Private Codespaces login Origin compatibility

Verified in remote Codex Linux on 2026-10-18, starting from Phase 4B `7b95795`
(including the merged Owner implementation). No live Codespace was accessed or changed.

## Finding and scope

FastAPI's CORS preflight and its mutation Origin check are separate. A successful
preflight does not make a POST with a different Origin valid. The existing Next.js
API proxy forwarded the received Origin unchanged, so Codespaces' rewritten
`http://localhost:3000` reached FastAPI and was correctly rejected.

A [first-hand Codespaces reproduction](https://github.com/orgs/community/discussions/147513)
reports this rewrite while preserving the external Host and HTTPS Referer; it also
reports that nonmatching external Origins are not rewritten. This is observed
behavior, not a documented stable GitHub forwarding contract. The reported Auvylen
symptoms are consistent with it. We have not inspected the user's live inbound headers.

`apps/web/src/lib/proxy-origin.ts` now gates POST normalization on all of:

- `CODESPACES=true`, `APP_ENV=staging`, a valid single-label `CODESPACE_NAME`, and
  forwarding domain exactly `app.github.dev` (the controller's existing default).
- Canonical HTTPS Origin computed from that server-side identity and port 3000,
  matching the **single** configured `CORS_ORIGINS` value.
- Incoming Host exactly equal to the canonical host. X-Forwarded-Host, if present,
  must match exactly too; neither header selects the trusted hostname.
- Incoming Origin either already canonical, or exactly `http://localhost:3000`.
  Missing, `null`, multiple, alternate-loopback, other-port, other-Codespace and
  unauthorized external Origins fail closed.
- For the localhost rewrite only: `Sec-Fetch-Site: same-origin` and a valid Referer
  with the canonical HTTPS origin and no URL credentials. Any supplied contradictory
  Fetch Metadata also rejects an otherwise canonical Origin.

Validation precedes body reading and upstream forwarding. The existing controller
already supplies the required environment; no new secrets or deployment flags are
needed. GET behavior and non-Codespaces forwarding are unchanged. FastAPI's exact
Origin allowlist, CSRF validation, Argon2id authentication, opaque expiring sessions,
authorization, rate limits and Secure/HttpOnly/SameSite cookies are unchanged.
No backend localhost allowance, CORS expansion, schema migration or data mutation
is introduced. No Owner provisioning or password rotation is required.

## Executed verification

| Command | Result |
| --- | --- |
| `npm test` | 82 passed, including 47 Origin-policy cases |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm run build` | Passed, Next.js 16.3.8 production build |
| `uv run pytest -q --ignore=services/api/tests/test_codespaces_login_proxy.py` | 148 passed, 24 explicitly skipped integration/pretrained checks |
| `uv run pytest -q --integration services/api/tests/test_codespaces_login_proxy.py services/api/tests/test_postgres_credits.py services/api/tests/test_postgres_owner.py services/api/tests/test_migrations.py` | 15 passed, no skips (33.02 seconds) |
| `uv run --no-sync ruff check .` / `ruff format --check .` | Passed; 144 files formatted |
| `uv run --no-sync mypy` | Passed, 66 source files |

The four new integration cases run the actual production-built Next.js route and
FastAPI login handler with synthetic credentials and a migrated in-memory database.
They verify canonical and rewritten login, invalid-password rejection, session
creation, cookie flags and both Set-Cookie headers, authenticated account access,
ordinary-user rejection from Owner APIs, logout, forged sessions and expiration.
Fifteen hostile header combinations are rejected even with valid credentials/CSRF.
Missing or forged CSRF still fails after normalization. Direct FastAPI localhost
requests still fail Origin validation, while canonical preflight succeeds.

The loopback test client explicitly relays the Secure cookie to simulate the trusted
HTTPS-termination hop; it does not disable Secure cookies in application settings.
This is an HTTP integration simulation, not a live GitHub/browser end-to-end test.
Existing PostgreSQL Credits/Owner concurrency and data-preservation regressions and
Alembic upgrade/check passed against remote development services. The live user
database, `owner_god`, Credits, photographs and models were never accessed.

Initial checks found an environment typing error, corrected before the final pass.
A sandboxed production build failed because Turbopack needed an internal socket;
its cached failure was removed with only this checkout's generated `.next` output.
The clean build passed with the required cloud loopback permission. The sandboxed
backend run was stopped and rerun successfully with test socket/cache access.

CI runs the new integration in the existing `commercial-browser` job after its
production build. The Python-only backend job explicitly excludes that module;
there is no extra Docker build or new CI job for this fix.

## Limits and rollout after approval

Keep forwarded port **3000 Private** and internal protocol **HTTP**; GitHub supplies
external HTTPS. Do not forward FastAPI, PostgreSQL or Redis. The compatibility rule
does not authenticate a forwarder: raw HTTP clients can manufacture these headers,
just as they can manufacture an HTTPS Origin today. Passwords, session tokens and
session-bound CSRF remain mandatory; browser Fetch Metadata and Referer provide
additional evidence for the otherwise ambiguous localhost Origin.

Browsers/extensions that strip Referer or Fetch Metadata will fail closed on the
rewrite path. If GitHub changes the scheme, host or rewrite behavior, login may fail
closed again. Inspect only sanitized Host/Origin/Referer-origin/Fetch-Metadata values
in the private terminal before changing this policy; never dump cookies, tokens or
request bodies, or add wildcard/localhost exceptions to FastAPI. A live private
Codespaces login check remains necessary after the user approves rollout.

After reviewing and merging the PR, in the **existing Codespace terminal**:

1. Follow [the encrypted backup procedure](codespaces-private-preview.md#encrypted-backup)
   and keep the verified encrypted copy outside the Codespace.
2. Ensure `git status --short` is clean, then update without overwriting local work:

   ```sh
   git switch codex/phase4b-custom-preferences
   git pull --ff-only origin codex/phase4b-custom-preferences
   python scripts/codespaces-preview.py stop
   npm run build
   python scripts/codespaces-preview.py start
   python scripts/codespaces-preview.py status
   ```

   If the build fails, keep services stopped and investigate rather than starting
   an incomplete build. No dependency update, migration, container recreation,
   volume deletion or account reinitialization is needed for this fix alone.
3. Confirm port 3000 remains Private. Refresh the existing HTTPS login page to obtain
   a fresh CSRF token, then sign in with the existing password. Confirm `/account`,
   Owner dashboard access for `owner_god`, and logout. Do not share credentials or
   full network captures. No merge or deployment was performed during implementation.
