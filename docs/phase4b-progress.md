# Phase 4B cloud verification and first implementation increment

For immediate browser use: [private Codespaces preview](codespaces-private-preview.md).

Current pretrained-extractor milestone: [implementation and licensing](pretrained-representation.md) and [verification report](phase4b-representation-report.md). Historical results below remain unchanged.

Current continuation: [core training report](phase4b-training-report.md) and
[model workflow](custom-preference-models.md). The text below records the preserved first milestone.

Date: 2026-10-12. Scope: master instruction Steps 1–2, plus research lease/cancellation
prerequisites. **This is not completion of the custom model/training system.**

## Environment and baseline

Work ran on a newly started managed **remote cloud** instance, Debian GNU/Linux 13,
x86-64, kernel 6.18.44, in `/workspace/auvylen`. The managed environment provider
reported `cloud`, connected/running, published configuration revision 2. The executor
cgroup allows 2 CPU cores and 8 GiB RAM; initially about 30 GiB workspace disk was
available. This is temporary development compute, not a purchased or public server.
No Windows/WSL server, tunnel, model download or dataset transfer was used. Local
Windows processes/volumes cannot be inspected from here; the previous shutdown report
remains historical evidence, not a fresh local inspection.

The checkout arrived clean on `work`, at `5dae3a8` (Phase 4A recovery baseline), with
only `origin/codex/phase4a-cloud-ready` visible. Created the requested local branch
`codex/phase4b-custom-preferences` from that commit. No remote write or public deployment
was performed. Original migrations 0001–0004 and financial business logic are unchanged.
Cloud setup had restored development configuration and two healthy PostgreSQL/Redis
containers; this work restored dependencies again with the project setup script.
No production credentials or previous Windows data were transferred.

Baseline verification before feature implementation:

- Locked setup: `AUVYLEN_REMOTE_DEV=1 bash scripts/cloud-dev-setup.sh` passed with Node
  24.19.0, Python 3.14 and uv 0.12.23. Published workspace caches were usable.
- Alembic upgrade/check passed; API `/health` and `/ready` returned 200 with PostgreSQL
  and Redis both healthy.
- `uv run pytest --integration -q`: **117 passed**, no skips.
- Frontend unit tests: **27 passed**. Ruff, format, mypy, ESLint, TypeScript and
  production Next.js build passed.
- Both existing checkout and Credits/redemption browser regressions passed.

The command sandbox required approved access to the cloud Docker socket and network;
no environment switch was used. Playwright's CDN returned a policy denial. The installed
`/usr/bin/chromium` successfully ran browser tests through an explicit executable-path
option; no network-policy bypass or TLS verification disabling was used for downloads.

## Implemented behavior

### Private datasets and annotations

The existing site now links `/research` to `/research/preferences`. Users with an
operator-granted research access record and `RESEARCH_MODE=true` can:

- Create projects, create/rename datasets and record source, optional URL and license.
- Choose an immutable rating scale (default 1–10) and retention (1–90 days, default 30).
- Upload multiple JPEG/PNG files from the website, see authenticated thumbnails, and
  supply or edit a person/group identifier for later identity-grouped validation.
- Rate one image at a time, save/next, skip, navigate backward, edit ratings and resume
  from saved annotations. Uploads and skipped ratings are never numerical labels.
- Record left/right/equal/skip comparisons, avoid duplicate unordered pairs, and edit
  saved comparisons. Pairwise choices remain separate from numerical scores.
- Exclude images, archive/restore datasets, and delete images or entire datasets.

Additive migration `0005_preferences` creates projects, datasets, images, ratings and
pairwise comparisons. PostgreSQL stores metadata and annotations. The storage primitive
keeps private files in `PRIVATE_UPLOAD_ROOT/preferences/<owner UUID>/<artifact UUID>`.
Python and TypeScript contracts are maintained together. API routes are rooted at
`/api/v1/research/preferences`; no operator route is exposed to the browser.

### Ingestion, privacy and retention

Dataset creation and every upload require the `adult-authorized-v1` consent assertion:
all subjects are 18+, upload/annotation permission exists, and the recorded license permits
use. This is user attestation, **not an age or face detector**. Only synthetic test
images were used in verification. No external image API receives photographs.

Limits: 4 MiB input image; 6 MiB encoded request; 4096 pixels per side; 16 megapixels;
single-frame JPEG/PNG only; two concurrent upload-processing slots per API process;
20 projects, 100 datasets, 500 images / 512 MiB derivative storage per owner; 10,000
pair records per dataset. Database user locks serialize quota checks, duplicate uploads,
ratings and pair updates. Upload rate limits also apply. Browser batches are limited to
20 files and processed sequentially; partially successful uploads remain visible on retry.

Original compressed bytes are never persisted. Pillow fully decodes, applies orientation,
converts to RGB, limits the stored image to 2048px, strips metadata and makes a 256px
thumbnail. SHA-256 records both original-byte and normalized-pixel hashes; identical
normalized content within a dataset reuses its existing image. This is exact-content
deduplication, not perceptual similarity or person identification.

Image reads require an authenticated owner, live research authorization and an unexpired,
undeleted dataset. Responses are `no-store`, `image/jpeg`, and `nosniff`. Plain authenticated
image requests bypass Next.js's public image optimizer. Private volumes are absent from
web/proxy containers. Origin and CSRF checks protect mutations.

Deletion/expiry immediately denies further reads. Owners retain deletion API rights after
research access revocation. The existing research worker checks retention every 60 seconds,
removes image and thumbnail files before removing DB references, and retries failures.
Dataset cleanup is bounded to 20 datasets per sweep. A separate sweep removes unreferenced
files older than one hour, under the same owner lock as uploads, to recover interrupted
writes. Fresh/in-flight and referenced files are preserved. Cleanup requires the worker
and its writable private-upload volume; while it is down, reads remain denied but physical
removal waits. Do not turn off research workers until pending deletion/expiry is drained.
Backups have their own separately managed retention and deletion obligations.

### Research queue and cloud portability

Existing durable queue behavior, retries, production mock prohibition and registry policy
remain. Workers renew owned, unexpired leases. Owner cancellation immediately fences
completion; it is represented using the existing `FAILED` status and the explicit reason
`Cancelled by owner`, preserving Phase 4A's status vocabulary. Renewing a stale, cancelled
or revoked lease fails. The UI has a cancel action for pending research jobs. Future
trainers must use the cooperative heartbeat check at bounded batch boundaries; no long
training implementation has been enabled by this increment.

The development same-origin proxy now explicitly permits research routes, preserves
binary image responses and query parameters, and bounds request bodies. Caddy allows a
6 MiB body only for the upload route while retaining its 1 MiB default. The worker's
private upload mount is writable solely to support retention/deletion.

Docker builds accept an optional BuildKit `proxy_ca` secret to trust the managed cloud
proxy without copying the CA into image layers. Strict TLS remains enabled. Runtime
migration files and the Node entrypoint are explicitly owned by their non-root users.
These ownership fixes were necessary because the published checkout restored restrictive
file permissions: the original image COPY operations made Alembic configuration and the
web entrypoint unreadable to runtime users.

### Dependency evidence

Added locked Pillow 12.3.0 for image decoding only. Its installed distribution includes
`pillow-12.3.0.dist-info/licenses/LICENSE`: Pillow/PIL use MIT-CMU terms, and bundled
libraries retain their individual notices in that file. Preserve the distribution's
license files when shipping. Upstream source: https://github.com/python-pillow/Pillow .
No model weights, extractor, facial dataset, or third-party research repository was
installed. Extractor code **and weight** licensing review is still required before
training work; Pillow is not a learned feature extractor.

## Verification of the increment

- `uv run pytest --integration -q`: **134 passed**, zero skipped. Includes the 117
  baseline tests plus dataset/annotation, invalid-image, consent, CSRF, ownership,
  revocation, expiry/deletion retry, orphan recovery, storage failure, PostgreSQL
  concurrency/restart, lease-renewal and cancellation tests.
- `npm test`: **30 passed**.
- Ruff lint/format, mypy (53 source files), ESLint and TypeScript passed.
- Host Next.js production build and both production Docker image builds passed.
- Development browser suite: **3 passed**, including the complete new upload/rating/pair/
  resume/archive/delete workflow and both legacy flows. Synthetic fixtures are generated
  in memory; no image fixture or real photograph is committed.
- HTTPS cloud browser suite: **2 passed**. Existing accounts/Credits/free research survive
  PostgreSQL/Redis/API/worker restarts. The new test sends a >1 MiB synthetic image
  through Caddy, recreates API/worker containers, verifies unchanged image bytes and
  saved ratings/group IDs, then confirms worker removal of both deleted image files.
- All six cloud application services reached healthy state; the serialized migration
  gate exited successfully. Container and host Alembic checks found no schema drift.
- Deployment-configuration regression subset: **17 passed** after runtime ownership fixes.
  The final internal proxy fix was also exercised by both passing HTTPS tests.

The first full dataset suite run caught a missing upload preflight helper during editing;
the corrected full run passed. Container verification additionally found and corrected
both non-root file ownership failures described above, plus proxy routing of internal
Compose traffic. Explicit internal-service `NO_PROXY` entries and a direct container-local
Caddy health probe fix that issue while preserving external proxy configuration. These were real failures, not skips.

## What is not implemented

The principal goal remains unfinished. There is **no real custom model yet** and no claim
of predictive accuracy. The following master-instruction work remains:

1. Review/choose extractor source and pretrained-weight licenses, install on cloud CPU,
   extract/cache versioned embeddings, and add model execution through the registry gate.
2. Immutable training snapshots; genuine regularized rating regression and separate
   pairwise ranking; reproducible person-grouped train/validation splits and measured
   MAE/accuracy, counts, duration and limitations.
3. Durable training configuration/progress, cooperative cancellation inside actual training,
   retriable/fenced checkpoint publication, model versions, active selection, retraining,
   archive/delete and checkpoint retention tied to dataset/image deletion policy.
4. Score unseen images with owned trained models; versioned raw/display outputs, latency
   and provenance; website prediction/model-management screens.
5. Independently install/review ComboLoss, FPEM, FACLIP and SwinGFVQA-ca adapters/weights,
   and show independent comparisons without averaging incompatible scales. All providers
   remain unavailable for real predictions. Custom datasets/labels have no dependency on
   these plugins and never learn from their predictions.
6. A modular licensed dataset-import mechanism, project rename/delete management and
   larger-scale performance testing. No automatic external dataset download exists.

No infrastructure or credential blocker prevents the next small CPU custom-model
increment in this cloud workspace. Model/weight licensing and installation are uncompleted
engineering work, not a verified external outage. There is no purchased persistent host,
GPU, public site, or approved public deployment.

## Operations, backups and next session

Use the existing operator grant command, research worker, migrations and environment
variables. For host development, set `PRIVATE_UPLOAD_ROOT` to an ignored writable directory
such as `/workspace/auvylen/private-data/uploads`, set `RESEARCH_MODE=true` for API/worker,
and run the worker alongside the API. Ordinary users perform dataset operations in the
website. Host test URLs are cloud loopback, not URLs reachable on the Windows browser.

Back up PostgreSQL (projects/annotations/consent/jobs and existing accounts/ledger), private
uploads, and future model artifacts separately but consistently, following
`docs/cloud-backups.md`. Preserve matching credentials outside Git. Restore databases
before serving images, run migrations/check, mount private volumes only in API/worker,
and run pending retention cleanup before enabling access. Ephemeral workspace state is
not an adequate backup for essential personal datasets.

The existing 2 vCPU / 4 GiB / 60 GiB foundation estimate remains an estimate; this session
used a 2-core / 8 GiB cloud quota for builds/tests. Initial model training memory, duration
and GPU requirements are **unmeasured**; no GPU is needed for this dataset increment.
Images use compressed normalized copies plus thumbnails, with a 512 MiB per-owner quota
before backup copies. Embedding and checkpoint sizing must follow extractor selection.
No production capacity or accuracy claim is justified by these synthetic tests.

After successful verification, the disposable six-service HTTPS stack and the baseline
API process started by this session were stopped to release cloud resources. All volumes
and their matching ignored test credentials remain; no `down -v`, prune or real-data
deletion was performed. The pre-existing development PostgreSQL/Redis services were left
untouched. Pending deletions of synthetic development-browser images were drained with
the implemented cleanup service.

A final idle snapshot of the six application containers used approximately 286 MiB in
aggregate reported memory (API 86, web 73, worker 67, PostgreSQL 35, Redis 6, Caddy 18 MiB).
This excludes build peaks, Docker/runtime overhead and any future ML work; it is not
a production capacity guarantee.

## Owner administration (separate review branch)

`codex/owner-god-provisioning` extends PR #1 with persistent Owner identity, centralized
free-product entitlement, bounded research quotas, administration and audit history.
See [Owner operations](owner-account.md) and [verification](owner-verification.md).
The Phase 4B learning engines and private artifacts are preserved. This branch is not
automatically merged or deployed into the existing private Codespace.
