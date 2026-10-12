# Pilot accounts

Implemented: register, login, logout, server-side authorization and expiring opaque sessions.
Identifiers are case-insensitive ASCII usernames or email-like identifiers (3–120 characters).
They are not verified email addresses. Passwords are 12–128 characters, never stored or logged
as plaintext. Argon2id uses 64 MiB, three iterations and one lane. See
[OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Each account gets a UUID-based public `usr_` identifier and one zero-balance wallet in the
registration transaction. Login has a generic invalid-credentials response for unknown,
incorrect-password and disabled accounts. Unknown accounts perform equivalent hash work.
Session tokens contain 256 bits of randomness; only SHA-256 digests are stored in PostgreSQL.
Login rotates the current session. Sessions expire after SESSION_LIFETIME_SECONDS (default
24 hours, maximum seven days). Logout deletes the current server-side session. Every
authenticated request checks session expiration and the user's disabled_at field.

Cookies are HttpOnly, host-only, SameSite=Lax and path=/; staging/production force Secure.
For any HTTPS development server set SESSION_COOKIE_SECURE=true. Plain HTTP is local-only.
TLS is mandatory for real pilot use. Cookie lifetime mirrors server expiration.

## CSRF and limits

GET /api/v1/auth/csrf returns a CSRF token, creating a random HttpOnly pre-login cookie if
needed. The token is HMAC-bound to that cookie or to the authenticated session token.
All account mutations, including login/register, require both X-CSRF-Token and an exact
Origin in CORS_ORIGINS. SameSite is defense in depth; it does not replace these checks.
Configure the actual browser origin even for same-origin HTTPS deployments, for example
CORS_ORIGINS=["https://your-domain.example"]. Empty origins fail closed for POSTs.
No passwords, codes or rejected input are echoed by validation errors. Account responses
use Cache-Control: no-store. See [OWASP session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

Redis atomic counters enforce five registrations, ten login attempts, ten redemptions,
and thirty analysis submissions per five minutes. Login also limits a keyed identifier;
authenticated operations additionally limit the public user ID. Addresses/identifiers are
keyed hashes in Redis. Redis failure returns 503; it never disables protection.
Proxy headers remain untrusted. Behind Caddy or the development proxy, IP limits apply
conservatively to the shared proxy address as well as individual account limits. This
can throttle a busy pilot; explicitly reviewed trusted-proxy configuration is future work.
Redis is disposable: restarting it resets short-term counters, not account/financial state.

## APIs and ownership

- GET /api/v1/auth/csrf; POST /api/v1/auth/register, /auth/login, /auth/logout.
- GET /api/v1/auth/me and /api/v1/account. The latter returns only the current user's
  balance, up to fifty recent ledger entries and fifty recent credit-funded analyses.
- GET /api/v1/credit-products; POST /api/v1/credit-analyses.
- GET /api/v1/credit-analyses/{UUID} and /result require ownership, returning 404 for
  other users. Legacy development analysis routes reject credit-funded analyses.
- There is no public user-ID wallet endpoint, admin panel or batch-generation API.

Frontend routes: /register, /login, /account, /redeem, /analyze, /history and the existing
/result/{UUID}?funding=credits. The query selects presentation only; ownership is enforced
by FastAPI. Local Next.js proxies only an allowlisted account surface to the configured API;
production Caddy routes /api directly. No external authentication or asset service is used.

## Pilot limitations

No email verification, password recovery, social login or self-service identity changes.
Keep credentials safe; there is no automated recovery guarantee. Support must verify
ownership independently before any future recovery tooling. Accounts do not authorize
production mock inference or direct-payment simulation. Public pilot launch, retention
rules, abuse-capacity tuning and support procedures require a separate review.
