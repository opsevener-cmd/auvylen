# Phase 4B core training implementation report — 2026-10-12

## Preservation and environment

Started from clean commit `8bc1d6274affb69232772c8a4532678614fcb83e` on
`codex/phase4b-custom-preferences`. GitHub metadata confirmed
`opsevener-cmd/auvylen` is **private** and writable. The remote Phase 4B branch was still
at `5dae3a8`. Explicitly fetched that branch, verified it was an ancestor of local HEAD,
fast-forward pushed `8bc1d62`, and confirmed the remote SHA matched. No force push,
remote-history rewrite or public visibility change occurred.

Work continued on the managed Debian 13 Linux cloud instance in `/workspace/auvylen`.
The managed environment reported provider `cloud`, connected/running, with enforced
restricted package-manager networking. An explicit Unix-socket Docker check confirmed
Linux daemon `f157bdf66ad2`. Windows/WSL and local computer services were not used.
The existing development environment has a 2-core / 8 GiB quota. No paid infrastructure,
GPU service, external inference API, domain or public deployment was created.

All previous source and migrations 0001–0005 are preserved. Existing datasets, ratings,
pairwise records, accounts, Credits, redemption and mock/research behavior remain intact.
The retained disposable HTTPS database was backed up to an ignored protected dump before
revision 0006 ran through the serialized migration gate. Its matching credentials and
volumes remain outside Git. Tests used generated in-memory synthetic images and isolated
PostgreSQL schemas, never real facial photographs committed to source.

## Completed core functionality

The existing website now supports genuine numerical-rating training, immutable annotation
snapshots, cached fixed visual features, versioned private JSON checkpoints, owner-selected
versions, real inference on previously unseen uploads, and retraining from additional or
edited labels. Training and prediction are existing durable research jobs run by the CPU
worker; requests return immediately. Progress, cancellation, leases, bounded retries and
fenced checkpoint publication are integrated.

Validation keeps supplied person/group IDs together, fits preprocessing only on training
images, and holds validation images out from model fitting. Each version reports counts,
MAE/RMSE, a mean-rating baseline, known/unknown identities, configuration and duration.
Prediction records model/version, raw/display score, rating scale, input image, timestamp
and processing latency. Research leaves Credits unchanged. No external-model predictions
serve as training labels.

Model archive/delete preserves original annotations. Source deletion/expiry denies model
use, erases checkpoint/snapshot data through worker cleanup, and removes related cached
embeddings when images are purged. Checkpoint corruption produces failed jobs rather than
fabricated scores. Private weights are never served to a browser.

The documented `rgb-grid-texture-v1` / `rating-ridge-v1` model is an **honest handcrafted
visual baseline**, not a pretrained facial network. It learns actual coefficients from
ratings and can predict unseen inputs, but facial generalization is unproven. Small-data,
background/lighting and unknown-identity limitations are shown in the website. Source and
bundled-library license review is recorded in `custom-preference-models.md`; no external
weights were installed. Research permission is distinct from commercial model permission
in the registry gate; production synthetic execution remains disabled.

## Executed verification

| Check | Result |
| --- | --- |
| Full backend/inference/infrastructure `uv run pytest --integration -q` | **144 passed**, no skips |
| Frontend `npm test` | **30 passed** |
| Development Playwright with explicit research mode | **4 passed** |
| HTTPS cloud Playwright | **3 passed** |
| Ruff lint and formatting | Passed |
| Mypy | Passed, 59 source files |
| ESLint and TypeScript | Passed |
| Host Next.js production build | Passed |
| API/worker and web production Docker builds | Passed |
| Host/cloud Alembic upgrade/check | Passed, no schema drift |
| Cloud six-service health and migration gate | Healthy; migration exited successfully |

New checks include actual learning from ratings and changing predictions when labels
change, unseen-value generalization on synthetic fixtures, grouped split separation,
training-only preprocessing, immutable snapshots, cancellation during extraction,
stale-worker artifact fencing and retry, checksum corruption, model/source deletion,
cross-owner denial, concurrent PostgreSQL idempotency/version allocation, and unchanged
Credits. Existing regressions run alongside all of these tests.

The website browser test uploads/rates ten images, trains version 1, uploads an unseen
image and predicts it, adds its rating, retrains version 2 and reloads both saved versions.
The HTTPS test recreates API/worker/web containers and produces **the identical raw
prediction from the same persisted checkpoint** afterward. It then retrains, preserves
both versions, and exercises source-data deletion/worker cleanup. Existing HTTPS
accounts/Credits/research and private-image restart/deletion flows also passed.

One browser run found a polling race: a completed job's state caused effect cleanup before
the ready model list refreshed. The fixed flow waits for the refreshed versions before
publishing the terminal UI state; the complete four-test run then passed. Repeated test
accounts also hit the normal per-IP registration ceiling. Browser configuration now uses
the existing shared-proxy policy used by the cloud stack, keeping all account limits and
rate limiting enabled. No limiter was disabled or production credential changed.

## Scope and remaining work

The requested numerical-rating end-to-end core is implemented and tested. These broader
master-instruction items remain:

- A reviewed pretrained feature extractor and facial-data accuracy studies; no accuracy
  claim follows from the synthetic tests or operational minimum of eight ratings.
- A separate pairwise ranking trainer. Existing pairwise annotation features are preserved
  and never converted silently into numerical ratings.
- Advanced independent ComboLoss/FPEM/FACLIP/SwinGFVQA-ca installation and comparisons.
  Missing/unreviewed external providers remain unavailable; their removal cannot affect
  first-party models, annotations or checkpoints.
- Licensed bulk dataset import, broader project management, larger-scale performance work,
  persistent production hosting and approved off-environment backups for important data.

No infrastructure or credential blocker remains for this tested core. No paid or public
hosting is assumed. Read `custom-preference-models.md` for usage, limits, provenance,
retention, API contracts and restoration procedure.

Repeated Docker builds under the managed VFS storage driver temporarily exhausted the
32 GiB workspace filesystem during final staging. Removing only unused build cache older
than ten minutes restored approximately 9.8 GiB free space. Source files, runtime images,
all database/image/model volumes, matching credentials and the protected backup were
preserved. The final image's HTTPS checkpoint/recreation test was rerun successfully.
No volume prune or data-volume deletion occurred.
