# Phase 7A — consented portrait and independent rating studies

This is a collection workflow, **not a new scoring model or a consumer release**.
It adds `/research/studies` to the merged development baseline `3df2ff1` without
changing accounts, Credits, existing datasets, checkpoints, model providers or release gates.
No real participant was enrolled, contacted or photographed for this implementation.
The browser evidence uses disposable accounts and generated colour/noise images only.

## Repository and privacy audit

The GitHub connection reported `opsevener-cmd/auvylen` as **PUBLIC** on 2026-11-07,
contrary to historical project descriptions. Its default branch was
`codex/phase4a-cloud-ready`; development uses `codex/phase4b-custom-preferences`.
Visibility and default branch were not changed. Treat code, PRs, Actions logs and any
committed evidence as publicly readable. Resolve the intended repository visibility
before real collection; never put invitations, consent evidence, participant contacts,
real photographs, exports, database backups or model weights in Git/Actions artifacts.

The tracked environment-file history contains the four `.example` templates only.
Existing ignores exclude uploads, datasets, private-data, credentials, backups, weights,
archives and generic image files; narrow existing exceptions are public generated artwork
and reviewed fixture screenshots. This is a scoped source/history inspection, **not**
a certification that every historical secret has been excluded. Existing encrypted
backup scripts include the complete private uploads/models volumes; they remain unchanged.

The implementation reuses cookie authentication, central account access policy, recent
staff authentication, exact Origin enforcement (including the PR #3 Codespaces pattern),
CSRF, private artifact storage, upload decoding/semaphores and the existing research
worker. New additive Alembic revision `0011_collection_studies` creates collection-only
tables. No live database or Codespace migration was executed.

## Workflow that is implemented

1. **Owner creates a fixture study first.** Choose an immutable development or holdout
   partition. A holdout requires an existing, independent, non-Owner custodian account.
   Collection is never enabled automatically. Accounts are never enrolled automatically.
2. **Publish versioned bilingual consent.** Specify purpose, photo rights, annotation
   rights, cloud processors/locations, research training/derived weights, risks, retention,
   removal contact and the review reference. The supplied sample is editable and is not
   legal advice or approval. SHA-256 binds the exact texts, contact, review reference,
   study UUID, partition, fixture policy, retention and version. Consent, acceptance
   receipts and private study audit records are immutable in the database.
3. **Issue a private invitation.** Only its peppered HMAC is stored. The plaintext is
   returned once, can be hidden, and never belongs in URLs, audit records or public posts.
   This application sends no invitations or recruitment messages. For a holdout, its
   custodian must first read and accept the consent. Then the Owner opens collection.
4. **Adults voluntarily join one role** after signing in and confirming adulthood,
   understanding, voluntariness and the stated research permissions. Fixture studies
   require an additional explicit fixture confirmation. A changed consent version pauses
   collection and requires a fresh acceptance before any new upload/rating work.
5. **Staff verifies participation before collection.** Participants provide their receipt
   code through an approved private procedure. Staff checks adulthood, source rights,
   independence and consent outside this application, and enters an opaque proof reference.
   Never upload identity documents or record names, email addresses or identity numbers
   in that reference. Reuse the same reference for the same person across studies.
   A global HMAC uniqueness guard rejects reused proofs on different accounts. References
   cannot later be reassigned silently. Manual verification is essential: account
   deduplication alone does not prove that two accounts are different humans.
6. **Contributors upload only their own authorized adult portraits.** JPEG/PNG, 4 MiB,
   maximum dimension 4096 and minimum short side 224. A metadata-free derivative is
   stored under a random UUID with private filesystem permissions. Actual XHR transport
   progress is separate from waiting for server processing and confirmed saving. The
   same request can be retried safely; decoded-pixel duplicate detection spans studies.
   Staff manually approves consent, rights and technical suitability before assignment.
   Age must never be inferred from facial appearance. Pose and lighting are declared,
   not machine-inferred. No ethnicity, identity or protected trait is inferred.
7. **Independent raters receive randomized private assignments.** No model output or
   other person's label is shown. Native integers 1–7 use the existing relative-to-average
   subjective scale, with 4 as average. Raters can skip. Their own photos are excluded.
   A person has one active assignment, one primary vote per image and at most one blind
   repeat per image. There is a 15-minute lease and a two-second post-display minimum
   before saving. This is a weak attention heuristic, not proof of human attention.
   A blind repeat after each five primary votes measures consistency; repeats never
   count as independent labels or enter exports. Quality summaries require manual
   review; unusual aesthetic opinions are not automatically excluded.
8. **Owner closes development collection and exports a stable private snapshot.** Only
   approved, active contributors and at least three approved independent primary raters
   per photo are eligible. The archive has native `means.csv`, raw `annotations.csv`,
   `collection.json`, exact consent policies, and a SHA-256 manifest. Pseudonymous global
   person IDs keep the same subject grouped across development studies. Login IDs,
   account UUIDs, private invitation codes and identity proofs are not exported.
9. **Withdrawal and deletion remain available when collection is off or sealed.** A
   participant can withdraw all their study roles, delete source derivatives and ratings,
   cancel assignments, and revoke exports. Individual portrait deletion also removes its
   ratings. The account, wallet and unrelated private datasets/models remain untouched.
   A durable erasure outbox revokes database access first and retries failed filesystem
   cleanup through the worker. The UI reports pending cleanup honestly. Minimal consent,
   pseudonymous immutable partition/identity HMAC, tombstones and audit evidence remain
   for accountability and leakage prevention, as disclosed before consent.

## Holdout isolation and its limits

Development/holdout assignment applies globally to contributors, raters and custodians,
including after withdrawal; the database prevents changing it. An independent custodian,
not the Owner role, manages holdout participants, portraits, quality records and study
audit. The Owner sees study governance, counts and seal digests only. Participant actions
are recorded in a separate pseudonymous study audit, not the Owner's account audit.
Private files use separate development, holdout and export namespaces. Every image
request checks authorization and expiry and uses `private, no-store`.

Holdout export is hard denied, including to the Owner and the operator export CLI. Only
its custodian can seal a closed holdout with eligible human ratings. The seal binds
subject/rater pseudonyms, photo and label identifiers, normalized-pixel and stored-byte
hashes, capture details, consent IDs and revision. Once sealed it cannot reopen, change
consent or be resealed under the same study. Removal or retention invalidates the seal
without restoring editability. Start a separately governed study if replacement is needed.

This is **application-level isolation**, not a boundary against a root/database operator
or colluding human participants. A genuinely external evaluation also requires an
independent custodian, protected infrastructure/keys, preregistered intended analyses,
and an external record of the seal before experimentation. This phase deliberately has
no holdout-label download or external evaluation executor. The native trainer's internal
train/validation/test splits over development exports are development diagnostics,
not the independent external test. No study labels were used to tune existing models.

## Export and native training handoff

Exports expire after 24 hours. Any data, membership, consent or relevant state change
revokes prior snapshots. Files are digest verified when served. The download endpoint
and metadata are private Owner-only and do not use shared caching. ZIP creation is
bounded at 64 MiB, serialized per Owner by existing account locking and stores no weights.

For an **approved private operator environment only**, immediately before each use:

```sh
# Uses configured private DB/storage to reject stale, expired or revoked exports.
# Creates a NEW directory with mode 0700; extracted files use 0600.
uv run python -m aevyra_api.studies.exports \
  --export-id <private-export-uuid> --output private-data/study-run-unique
```

`means.csv` uses `images/<uuid>.jpg`; point the native trainer's `--images` argument to
`private-data/study-run-unique` (the archive root, **not** its `images` subdirectory),
`--labels` to its `means.csv`, and `--plan` to its `collection.json`. See
[the native training protocol](../native-aesthetic/README.md). Fixture exports remain
`synthetic=true`; they are not real portrait evidence or release candidates. Real
collections and weights are non-commercial; encoder rights require a separate review.
Three raters per photo is a collection minimum, not a meaningful model release sample.

Already downloaded files and in-flight responses cannot be recalled. Offline native
training cannot enforce live revocation by itself. Operators must register every copy,
recheck live export status before every training/evaluation use, remove revoked copies
and record derived model lineage. No existing model is silently retrained or deleted.
Withdrawal from a trained collection requires a documented operator decision about
retraining/unlearning and removal of affected releases; this phase does not promise
machine unlearning. Do not publish collected data or derived weights.

## Resource limits, retention and operations

Defaults: 30 studies, 1000 role memberships per study, 200 active photographs **globally**,
6 active photographs per contributor membership, 30 primary rating slots per image,
4 MiB inbound files, two concurrent decodes, 64 MiB archives, 15-minute assignments,
30-day portrait retention (immutable per study, API allows 1–90 days), 24-hour exports.
PostgreSQL row/advisory locks serialize assignments, identity checks and global image
budget checks; database unique indexes remain the final duplicate fence. No new runtime
or frontend dependency and no external analytics/image request was added. Portrait review
renders twelve images initially, revokes Blob URLs and has explicit pagination controls.
There is no rating polling or model initialization in the collection path.

The existing supervised research worker purges expired portraits/exports and retries
physical erasure every minute, even after the collection flag is turned off. It reconciles
orphan files from interrupted writes after an hour. Keep the worker running while any
study data exists. Monitor `study_erasure_retry` and `collection_garbage`; unresolved
outbox entries are an operational incident, not successful physical deletion. Storage
access is revoked immediately even during worker outages, but physical cleanup depends
on the worker and a functioning filesystem. A configured retention period is an upper
bound for access; purge timing has a worker interval/outage lag.

Backups may retain deleted bytes. Before real collection, approve backup retention,
key custody, deletion-on-restore replay and a removal register. Restore into isolation,
replay withdrawal/tombstone/outbox state before serving, and never resurrect old exports
or a stale sealed holdout. These are release prerequisites, not implemented crypto-erasure.

## Activation and rollout gates

Both `STUDY_COLLECTION_ENABLED` and `STUDY_REAL_COLLECTION_ENABLED` default to false.
Fixture collection additionally requires `RESEARCH_MODE=true` and `PUBLIC_PILOT=false`.
Real collection also requires staging/production, secure cookies and a nonempty
`STUDY_COLLECTION_REVIEW_REFERENCE`. Configuration asserts review happened; it does not
create legal permission. No tracked deployment configuration enables either flag.
All consumer scoring/provider/payment gates are unchanged.

Before any later authorized rollout: resolve repository visibility, preserve and verify
an external encrypted backup using [the established procedure](../cloud-backups.md),
review migration 0011, apply it only during an approved maintenance window, verify the
worker/outbox and existing login/Credits/personal-model regressions, then run fixtures
before proposing real collection. Downgrade refuses if study evidence exists; use a
verified backup or forward fix instead of destroying consent history. No rollout,
merge, recruitment, real data ingestion, spending or public deployment is authorized
by this PR.

**Release decision: GO for draft review and isolated authorized fixture evaluation;
NO-GO for real participant collection or consumer scoring.** Real collection needs an
approved adult/independence verification process, final bilingual consent and annotation
rights, processor/location assessment, secure custody and invitation procedures, working
removal contact, backup/deletion procedures, an independently recorded holdout protocol,
and explicit authorization. Demographic coverage is not claimed or inferred; optional
self-reported demographic collection needs a separate consent/minimization review.

## Verification

See [the verification report](verification.md) and the isolated browser test configuration
`apps/web/playwright.studies.config.ts`. Its mandatory fixture server guards require
`APP_ENV=test` and `AUVYLEN_TEST_FIXTURES=ISOLATED_SQLITE_ONLY`; it supplies a fresh in-memory
SQLite engine directly to Alembic and never connects to DATABASE_URL or provisions a
live Owner. Public fixture passwords are used only in that temporary database. The
script is excluded from production Docker context. Browser traces/video are off so
future accidental participant captures do not become automatic artifacts.
