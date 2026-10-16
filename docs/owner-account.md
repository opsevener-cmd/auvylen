# Auvylen Owner identity: implementation and rollout

The reserved account identifier is `owner_god`. **No password is stored in source,
chat memory, migrations, env files or command arguments.** The password shared earlier
in chat must not be reused. Choose a fresh secret and store it in a password manager.

## Implemented here (Phase 1)

- New `users.role` persisted with server default `user`, preserving existing accounts,
  with a partial unique index preventing more than one `owner`.
- Public signup rejects `owner_god`. No website route can promote anyone to Owner.
- Private Codespaces terminal performs a one-time interactive, transactional bootstrap:

  ```sh
  python scripts/codespaces-preview.py owner-init
  ```

  It asks for a fresh password twice without echo, hashes it using Argon2id, creates an
  Owner wallet and research authorization, and refuses to replace an existing Owner or
  promote any account already holding that identifier. It is **not** run automatically.
- Owner signs in through the ordinary authenticated session flow (Secure/HttpOnly cookies,
  CSRF, throttling, expiry); the account page displays the role.
- Owner bypasses Credit **deductions** for existing non-production synthetic analyses,
  without forging an infinite wallet or refund; idempotency still applies.
- Owner is implicitly eligible for current authorized research models/datasets when
  the server is explicitly in research mode, with no repeated `grant` command.

## Deliberate restrictions

Owner is not a security bypass. All consent, image rights, ownership of private datasets,
retention, model/provider availability, authentication, CSRF and rate/size/resource ceilings
remain enforced. Production mock/scoring and real checkout cannot be magically enabled.
Regular accounts retain unchanged Credits accounting and isolation. This change does
**not** yet introduce a public administrative dashboard.

## Phase 2 (not implemented in this patch)

Build an Owner-only API and dashboard for account review, research grants, code/batch
administration, audit history and service status, then add reviewed higher Owner quotas
and first-class free access to future real scoring providers. Add owner password rotation,
recovery and optional MFA without hard-coded backdoors.

## Safe update path

Review/test the change, back up the private Codespace database and files, merge into
`codex/phase4b-custom-preferences`, and update the **same running Codespace**.
Run `python scripts/codespaces-preview.py setup` followed by `start` to rebuild
and migrate once the code has been fetched. Verify 3000 Private and health ready.
Only then run `python scripts/codespaces-preview.py owner-init` and sign in as Owner.
Never delete the Codespace or run `docker compose down -v` as an upgrade strategy.
