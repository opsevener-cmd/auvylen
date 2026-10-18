# Private Codespaces login Origin compatibility

Updated in remote Codex Linux on 2026-10-18, starting from Phase 4B `db6f429`
(including merged PR #2). The implementation session did not access or change the
live Codespace; the user supplied the captured ingress headers below.

## Finding and scope

FastAPI's CORS preflight and its mutation Origin check are separate. A successful
preflight does not make a POST with a different Origin valid. The existing Next.js
API proxy forwarded the received Origin unchanged, so Codespaces' rewritten
`http://localhost:3000` reached FastAPI and was correctly rejected.

The initial compatibility fix assumed GitHub retained the external Host, based on
an earlier public reproduction. The user's actual private Codespace capture shows
that **both Host and Origin are rewritten**:

```text
Host: localhost:3000
Origin: http://localhost:3000
X-Forwarded-Host: opulent-umbrella-6v5456gw9jx5hrg69-3000.app.github.dev
X-Forwarded-Proto: https
Sec-Fetch-Site: same-origin
Referer origin: https://opulent-umbrella-6v5456gw9jx5hrg69-3000.app.github.dev
```

Requiring the external Host rejected this legitimate request before forwarding to
FastAPI. The regression now replays this captured combination. Referer paths in
tests are synthetic; only its captured origin is known. This is observed behavior,
not a guaranteed stable GitHub forwarding contract.

`apps/web/src/lib/proxy-origin.ts` now gates POST normalization on all of:

- `CODESPACES=true`, `APP_ENV=staging`, a valid single-label `CODESPACE_NAME`, and
  forwarding domain exactly `app.github.dev` (the controller's existing default).
- Canonical HTTPS Origin computed from that server-side identity and port 3000,
  matching the **single** configured `CORS_ORIGINS` value.
- Either the unchanged canonical Host and HTTPS Origin pair, or exactly
  `Host: localhost:3000` with `Origin: http://localhost:3000`. Mixed pairs, missing
  Host/Origin, `null`, multiple values, alternate loopback addresses, other ports,
  other Codespaces and unauthorized external Origins fail closed.
- For the localhost pair, all four additional headers are mandatory:
  X-Forwarded-Host exactly equals the configured canonical host,
  X-Forwarded-Proto is exactly `https`, Sec-Fetch-Site is exactly `same-origin`,
  and Referer is a single valid URL with the canonical HTTPS origin and no
  credentials or fragment. No trusted origin is ever derived from request headers.
- The unchanged canonical pair does not need forwarding headers. If forwarded
  host/protocol, Fetch Metadata or Referer are supplied, they must agree with the
  same policy. Combined duplicate values and ambiguous Referer forms are rejected.

Validation precedes body reading and upstream forwarding. The existing controller
already supplies the required environment; no new secrets or deployment flags are
needed. GET behavior and non-Codespaces forwarding are unchanged. FastAPI's exact
Origin allowlist, CSRF validation, Argon2id authentication, opaque expiring sessions,
authorization, rate limits and Secure/HttpOnly/SameSite cookies are unchanged.
No backend localhost allowance, CORS expansion, schema migration or data mutation
is introduced. No Owner provisioning or password rotation is required.

## Captured-ingress correction verification

Executed against the correction in remote Linux:

- `npm test`: 114 passed, including 79 Origin-policy cases.
- `npm run lint`, `npm run typecheck`, `npm run build`: passed.
- `uv run pytest -q --integration services/api/tests/test_codespaces_login_proxy.py`:
  4 passed. The production-built Next.js proxy and real FastAPI handler accept the
  captured localhost pair and the unchanged canonical pair, while rejecting missing,
  forged, multiple and contradictory forwarding values even with valid credentials
  and CSRF. Session, cookie, CSRF and direct FastAPI Origin checks remain covered.
- `uv run pytest -q services/api/tests/test_credits.py services/api/tests/test_owner.py`:
  30 passed, 1 integration test skipped (covered by the CI integration run).
- Ruff lint/format and mypy: passed (145 Python files formatted, 66 source files typed).

The isolated integration uses only synthetic credentials and a migrated in-memory
database. Replay is verified; a live browser login after approved rollout remains
to be confirmed. The PR records the final commit's five GitHub Actions job results.

## Original PR #2 verification (historical)

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
closed again. Inspect only sanitized Host/Origin/X-Forwarded-Host/X-Forwarded-Proto/
Referer-origin/Fetch-Metadata values
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
