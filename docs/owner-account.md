# Owner account and administration

The reserved login is `owner_god`. The database role, never the login string or a
browser value, authorizes the Owner. No Owner is automatically created in a deployment.
Choose a new secret in the private Codespaces terminal; never reuse a password disclosed
in chat. This implementation extends draft PR #1 on `codex/owner-god-provisioning`.
Deployment and merging require the owner's approval; development does neither.

## Identity and recovery

After the approved incremental deployment below, run in the **existing private Codespace**:

```sh
python scripts/codespaces-preview.py owner-init
```

The command requires a terminal, asks for a new 12–128 character password twice without
echo, and transactionally creates the Owner, wallet, research authorization and audit
record. Passwords are Argon2id (64 MiB, three iterations, one lane); only hashes persist.
Do not pass passwords as arguments or environment variables. Store the chosen password
in your password manager. Sign in normally at `/login`, then follow **Owner dashboard**
from `/account` to `/owner`.

A unique partial index permits one Owner. Public registration reserves the canonical
identifier. Constraints restrict roles and the Owner login. Database triggers reject role
reassignment, Owner renaming, disabling and deletion. Bootstrap refuses an existing Owner
or occupied reserved identifier; it never resets, promotes, or replaces an account.
Repeated starts, migrations and deployments do not initialize credentials.

For routine password rotation:

```sh
python scripts/codespaces-preview.py owner-rotate
```

Enter the current password and a different new password twice. All existing Owner sessions
are revoked atomically. If the password is lost, a person with verified control of the
private Codespace and its existing database credentials can explicitly run:

```sh
python scripts/codespaces-preview.py owner-recover
```

This requires typing `RECOVER usr_...` for the existing Owner identifier displayed by the
command, then entering a new password twice. Recovery is audited and revokes every session.
There is no HTTP recovery endpoint, universal secret, known password, or recovery token.
Terminal/database access is the recovery trust boundary; a `CODESPACES` variable alone
confers no database access. Protect GitHub/Codespaces access with MFA. Browser MFA/passkeys
are not implemented. The command currently targets Codespaces; future production-host
terminal provisioning must get an explicit reviewed operator entry point.

## Product entitlements and operational limits

`aevyra_api.entitlements` centralizes `is_owner`, `require_owner`, `product_access`,
`credit_cost` and `research_limits`. New permitted paid features must use this policy:

```python
allowed = product_access(database_user, standard_allowed=ordinary_entitlement)
cost = credit_cost(database_user, configured_cost)
```

Load the user from trusted server-side database/session state. Separately verify provider
implementation, availability, licenses, configuration, consent, retention and private-data
ownership. Explicit administrative actions use `require_owner`, not `product_access`.
There is no future model-name allowlist for Owner entitlements. The provider registry's
review/install policy remains independent; entitlement does not install or license a model.

Owner product usage costs zero Credits without subscriptions or redemption. The wallet
is a real finite ledger balance, normally zero. Every free analysis has an immutable
`free_analysis_grants` record with product, policy version, account, analysis and timestamp.
The analysis's durable request key and recorded product enforce idempotency. Failure never
creates a refund without a matching actual debit. Paid ordinary-user ledger paths and
legacy payment flows remain intact. Current account scoring is explicitly synthetic and
unavailable in production for everyone. Real custom training and prediction remain private,
non-commercial research, independent of removable GitHub plugins. No unavailable provider
is made operational by this change. Owner implicitly receives research entitlement, but
`RESEARCH_MODE` must still be enabled.

Default resource budgets:

| Resource | Standard account | Owner setting / default |
| --- | --- | --- |
| Projects | 20 | `OWNER_MAX_PROJECTS=100` |
| Datasets | 100 | `OWNER_MAX_DATASETS=300` |
| Stored images | 500 | `OWNER_MAX_IMAGES=1000` |
| Normalized images + thumbnails | 512 MiB | `OWNER_STORAGE_MIB=2048` |
| Pairs per dataset | 10,000 | `OWNER_MAX_PAIRS=50000` |
| Retained model versions | 100 | `OWNER_MAX_MODELS=300` |
| Pending + running jobs per account | 2 | `OWNER_MAX_PENDING=4` |
| Jobs per rolling 24 hours | 50 | `OWNER_DAILY_LIMIT=200` |
| Concurrent live jobs across workers | 1 globally | `RESEARCH_MAX_RUNNING=1` (hard maximum 2) |
| Rated images per training version | 500 | **500 retained** |

Settings are bounded, not unlimited. Configure them in the existing managed service
configuration/terminal environment consistently for API and worker, then restart services.
Do not increase concurrency on a 2 CPU / 8 GB preview without capacity testing. The global
claim cap uses a PostgreSQL advisory transaction lock and unexpired job leases across
worker replicas. Existing retries, cancellation, lease fencing, batch size eight and
single-thread CPU extraction remain. Owner can store multiple datasets beyond 500 images,
but must keep each training request at or below 500 rated images. File/decode/request
limits, 1–90 day dataset retention, exact-Origin CSRF, login throttling and storage privacy
are unchanged. The higher storage quota is a ceiling, not reserved disk capacity.

## Dashboard and APIs

`/owner` verifies the ordinary session against the API before rendering. Every
`/api/v1/owner/*` endpoint independently verifies database-backed Owner authorization.
Mutations additionally require exact Origin, CSRF, bounded input, an idempotency key and a
non-sensitive audit reason. A login within `OWNER_FRESH_AUTH_SECONDS` (default 600,
maximum 900) is required under the transaction's Owner lock. **Confirm fresh authentication**
on the dashboard performs the existing normal password login with its existing throttles
and rotates the browser session. This does not extend the configured session expiry silently.

- **Overview:** account/grant/data/model counts, ledger totals, job totals and provider usage,
  installed extractor/provider status, database/Redis checks, worker heartbeat/active leases,
  filesystem free/total bytes, API peak RSS and host load. Shared filesystem capacity and
  API-only memory are labelled; unavailable observations remain unavailable.
- **Users & Credits:** paginated searchable active/disabled lists, disable/restore, research
  grant/revoke, finite balances, paginated immutable ledger history and balance reconciliation.
  Disable revokes sessions and fences queued/running research work. Restore never restores
  old sessions or cancelled work. Owner controls are rejected by the backend even if forged.
- **Promotional Credits:** positive bounded grants reuse wallet locks and `append_credit`.
  A transaction commits the ledger entry and audit record together. Replays return the
  original result; changed parameters with a reused key conflict. No balance overwrite or
  ledger deletion endpoint exists. Discrepancies are visible, not automatically “repaired”.
- **Redemption:** create up to 100 codes per batch with Credits and expiry settings, inspect
  counts/status, disable batches. The initial authenticated, fresh, CSRF-protected response
  is the only plaintext export. Download to protected storage and clear it from the page.
  Codes remain in that page's memory until cleared/unloaded; no browser storage is used.
  Only HMAC lookup digests and masked suffixes persist server-side. Retrying a committed
  creation returns a conflict, never secrets again. If delivery is uncertain, inspect and
  disable the batch before creating another. Disabling uses the existing redemption lock.
- **Research operations:** paginated job IDs/provider/kind/status/progress/attempts/times.
  No payload, prediction result, source image, subject annotation or private checkpoint is
  disclosed. Administrative access never implies ownership of another user's research.
- **Audit trail:** paginated actor, action, target, result and non-sensitive metadata.
  Success mutations and one-time provisioning are transactional. PostgreSQL rejects audit
  UPDATE/DELETE/TRUNCATE. Free usage records are also append-only. Failed HTTP admin
  requests are recorded separately with status and validated target IDs, without bodies.
  Failure logging is bounded to 100/minute to prevent audit flooding; overflow/dependency
  failure produces a safe warning, and does not enable a rejected operation. Existing
  terminal grant/batch/research tools also identify deployment-terminal control in audit
  records (null account actor, never an invented browser identity). Historical ledger and
  batch records remain their own existing evidence; they are not rewritten as new events.

Passwords, session tokens, raw redemption codes, private images and checkpoints are absent
from list/read APIs and audit metadata. Audit reasons are operator text: never put secrets
in them. TLS/Secure/HttpOnly/SameSite cookies, expiry and per-user data isolation are retained.
Database superusers can change schema/disable triggers; application-level append-only guards
are not an external tamper-proof archive. PostgreSQL credentials remain highly privileged.

## Approved deployment into the existing Codespace

Do these steps **only after reviewing and approving PR #1 and its tests**. Do not rebuild
or recreate the devcontainer, delete volumes, expose ports or buy infrastructure.

1. In the existing Codespace terminal, check `git status --short`. Preserve any local work;
   do not reset or discard it. Note the current commit with `git rev-parse HEAD`.
2. Create and protect a consistent encrypted backup with the existing controller:

   ```sh
   python scripts/codespaces-preview.py backup
   ```

   Save the encrypted archive, SHA-256 file and passphrase in separately protected,
   already-approved storage outside the disposable Codespace. The archive includes the
   PostgreSQL dump, original pepper/credentials, uploads and model checkpoints. Verify a
   recovery copy using [the existing backup/restore procedure](codespaces-private-preview.md).
   A copy stored only inside the Codespace is not a recovery backup. Backup briefly stops
   and resumes application writers; do this in your chosen maintenance window.
3. Review and merge the approved PR in GitHub into `codex/phase4b-custom-preferences`.
   The implementation task does not merge or deploy it. Then, in the **same Codespace**:

   ```sh
   git branch --show-current
   git fetch origin codex/phase4b-custom-preferences
   git log --oneline HEAD..FETCH_HEAD
   ```

   Confirm the checkout is the intended Phase 4B branch, clean, and the fetched commits
   are the reviewed merge. If it diverged, stop and reconcile without force/reset.
4. Stop only application processes, fast-forward, restore locked dependencies, run the
   serialized incremental migration gate and rebuild the Next.js production application:

   ```sh
   python scripts/codespaces-preview.py stop
   git merge --ff-only FETCH_HEAD
   python scripts/codespaces-preview.py setup
   python scripts/codespaces-preview.py start
   python scripts/codespaces-preview.py status
   curl --fail --silent http://127.0.0.1:8000/ready
   curl --fail --silent http://127.0.0.1:3000/health
   ```

   `setup` runs `0007_owner_role`, `0008_owner_administration`, then `alembic check` through
   the existing authorized migration gate. No database reset, image rebuild or model
   re-export is required when the verified MobileNet graph already exists. `status` must
   show API, Web and Worker RUNNING; check worker heartbeat after opening the dashboard.
5. Keep port **3000 Private** in GitHub's Ports tab. Use its existing HTTPS browser URL.
   PostgreSQL, Redis and API remain unforwarded. No Windows service is involved.
6. Run `owner-init` interactively as described above, choose a new password, then log in
   as `owner_god`. If already provisioned, init refuses; use ordinary login or explicit
   rotation/recovery. Confirm the Owner badge/free entitlement and `/owner` overview.
7. Verify an ordinary account still has its balance and records; inspect ledger reconciliation.
   Confirm existing datasets/models and MobileNet availability. Use authorized synthetic
   fixtures for a training/prediction smoke test. Do not create a real grant or code batch
   just to test without an intended recipient/use.

### Migration failure and recovery

Both migrations are additive for the PostgreSQL deployment. Existing password hashes,
sessions, ledger rows, dataset annotations and checkpoint references are preserved. `0008`
backfills funding records only for the narrow free-analysis path that PR #1 implemented.
Ordinary missing debits remain errors. A failed PostgreSQL migration rolls back; the
application stays stopped if setup fails. Inspect the safe error and private runtime logs,
fix the cause and rerun setup. Do not serve partially migrated code.

Downgrade refuses once Owner identity or new immutable history exists. Prefer a reviewed
forward fix. A full rollback requires a verified pre-upgrade database **and matching private
artifacts/pepper** in a controlled recovery procedure; it discards post-backup writes and
requires separate explicit approval. Do not blindly run an older checkout against the new
Owner security semantics or delete volumes to recover. Normal start/stop/resume preserves
identity and data. Take another encrypted backup after successful provisioning.

See [verification evidence and limitations](owner-verification.md).
