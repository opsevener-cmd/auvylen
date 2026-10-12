# Phase 4A production and research boundary

Cloud-first recovery policy: Windows is not a hosting or training machine. Project
containers have been stopped without removing volumes. Only reviewed source belongs
in the future private remote; real env files, CSV codes, photos and checkpoints remain
excluded. Phase 4B image ingestion must add ownership, consent, safe decoding and
retention controls before activation. No production deployment is performed here.

Cloud-specific safeguards: only Caddy publishes 80/443; uploads and model checkpoints
are private volumes never mounted into web/proxy. Public uploads and downloads remain
absent. Non-root workers consume durable PostgreSQL jobs; research authorization is a
CLI-managed record, not a request parameter. Jobs/results require account ownership and
CSRF/Origin protection. Mock execution remains disabled in production, and the cloud
override disables legacy mock checkout in staging too. Training and optional models
remain unavailable rather than substituting fake scores.

Migration startup requires explicit APPLY_MIGRATIONS review and successful upgrade/drift
check. Back up before upgrades and stop existing applications first. See [Phase 4A](phase4a.md)
and [backup/restore](cloud-backups.md). No public deployment or Windows host requirement exists.
Redis AOF preserves rate limits; PostgreSQL remains authoritative for jobs and Credits.
Client IP forwarding is not trusted: cloud limits use aggregate proxy ceilings plus
tighter account limits. Distributed trusted client-IP enforcement remains a future review.

The application brand is Auvylen. Renaming labels does not change security gates, provider
policy or persisted identities. The existing environment names remain accepted unchanged;
production mock checkout remains disabled. See [rename audit](brand-rename.md).

- Only Caddy publishes TCP 80/443. PostgreSQL and Redis share an internal data network;
  web has no access to that network. API/web ports and Caddy's admin API are unpublished.
- HTTPS is automatic for a configured public domain. Caddy limits request bodies to 1 MB,
  removes Server, and supplies safe framing/content/referrer headers. No uploads exist.
- Caddy sets forwarding headers using its direct client connection. Uvicorn deliberately
  ignores proxy headers today; no business logic trusts client addresses/scheme. A later
  feature needing them must define trusted proxy addresses explicitly. No wildcard trust.
- API debug is always off. Production disables docs/OpenAPI, legacy mock commercial routes and the
  mock simulation endpoint. Frontend also refuses commercial calls and hides checkout.
  Mock inference remains production-disabled by the registry. Real payments do not exist.
- APP_ENV is explicit in deployment. API rejects weak/example database passwords, missing
  service URLs, wildcard CORS and DEBUG logging. The required redemption pepper is never
  defaulted outside tests. Exact browser origins are required for account mutation CSRF
  checks even on a same-origin deployment. Only mock is a payment provider; it cannot move funds.
- Secrets are injected at runtime. Build context excludes env files, dependencies, test
  artifacts and Git data. API runtime contains installed packages and migrations, not uv,
  pytest, Ruff or mypy. Web runtime contains Next standalone output/static assets, not the
  full build workspace. API/web run non-root, drop capabilities, and prohibit privilege gain.
- Database/cache images use their official startup privilege management. Caddy needs to
  bind low ports and write certificate volumes; its official container runs as root with
  no-new-privileges. Host access remains a privileged trust boundary.
- API logs have timestamp, level, service, generated request ID and relevant order/analysis
  IDs. Request bodies, headers, URLs and exception text are omitted. Uvicorn access logging
  is disabled and its exception formatter omits tracebacks/messages. Web failures use safe
  JSON events with timestamps/service/error classes. Caddy access logging is not enabled to avoid collecting sensitive paths;
  operational proxy logs remain on stderr. Docker logs rotate at 10 MB × 3 files/service.
- Redis is disposable, has no public port and no financial state. Internal network isolation
  is the current protection, not a claim that unauthenticated Redis is safe on shared networks.
- First-party pilot accounts use Argon2id and hashed opaque server-side sessions with expiry,
  logout and disabled-account checks. Cookies are HttpOnly/SameSite with Secure enforced on
  staging/production. Every account mutation requires exact Origin and HMAC-bound CSRF.
  Redis login/redemption limits fail closed. Proxied IP limits conservatively share the
  proxy's address; trusted forwarding headers require a future explicit review.
- Account-owned analyses and histories enforce ownership; legacy development routes reject
  credit-funded analyses. The database blocks financial-history mutation; wallet/code locks
  and durable unique keys prevent double redemption, overspending and double refunds.
- HMAC code lookups preserve no plaintext unused codes in PostgreSQL. exports/ is excluded
  from Git and Docker; protect CSVs and separately back up the pepper. Never log passwords,
  session tokens, full redemption codes or pepper. Validation errors omit rejected input.
- Staging must remain private because legacy unauthenticated mock checkout is still enabled.
  Accounts do not permit production synthetic inference or mock payments. No real provider
  or facial model is connected. Recovery/retention/support and public launch remain limited.
- Backup/restore and reviewed migrations are required operational safeguards. A single VPS
  has no high availability or PITR. Public DNS/ACME issuance must be validated on the actual VPS.

See deployment.md for maintenance, rollback, local TLS and exact commands. Never expose a
Docker socket to application containers or publish development Compose to the internet.
