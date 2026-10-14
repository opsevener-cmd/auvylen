# Personal rating models — Phase 4B core

Current pretrained-extractor milestone: [implementation and licensing](pretrained-representation.md) and [verification report](phase4b-representation-report.md). Historical results below remain unchanged.

Updated 2026-10-12. The existing Auvylen website now supports the complete numerical-rating
training and prediction workflow. This is a genuine **CPU visual baseline**, not a
pretrained facial attractiveness network. It learns from the owner's saved numerical
ratings. Pairwise annotations remain separate; pairwise model training and advanced
external-model comparisons are later work.

## Website workflow

1. Sign in with operator-granted research access while `RESEARCH_MODE=true`.
2. Open Research → Personal preference datasets. Create a project/dataset or use an
   existing one. Upload only authorized photographs of adults using the existing
   consent, provenance, size and retention controls.
3. Add at least **8 numerical ratings across 5 independent subject/content groups**.
   Give all photographs of the same person the same person/group identifier. Skipped
   ratings, excluded images and pairwise choices are not numerical training labels.
4. Select regularization, seed and validation fraction, then **Train new version**.
   The durable worker extracts/caches visual features, fits a model and writes a private
   checkpoint. The website shows progress, cancellation and validation results.
5. Upload a new photograph, choose a saved model version and photograph, then
   **Predict personal rating**. Prediction does not create a user annotation.
6. Add/edit ratings and train again. Each request produces a new numbered version;
   previous checkpoints and their annotation snapshots remain unchanged.

The site supports version selection, archive/restore and explicit model deletion.
Pending jobs resume in the interface after reload. Archive/delete of a model does not
change original user ratings or pairwise records. Research training/prediction never
spends Credits. Existing synthetic/commercial flows retain their previous behavior.

## Implemented learning and validation

The first-party extractor `rgb-grid-texture-v1` computes 230 fixed visual features:
8×8 spatial RGB averages, 4×4 pooled gradients and color moments. Its code uses the
locked Pillow and NumPy packages, with no external pretrained weights or inference API.
It is general image feature extraction; it does not detect faces, age or identity.
Consent is the existing adult/authorization attestation, not automated age verification.

`rating-ridge-v1` fits ridge regression on user ratings. Feature means, scales and the
intercept are fitted using **training images only**. The numerical solve uses the dual
form, bounded by the 500-image account quota. No large neural network or GPU is required.

The split is deterministic for the immutable snapshot, seed and validation fraction.
Supplied subject IDs stay together; unknown identities use normalized-content groups.
Repeated content within a dataset is already deduplicated by the ingestion subsystem.
At least four images must remain in training, and training ratings must vary. Group
fractions are approximate image fractions because groups are indivisible. Validation
images are excluded from both fitting and fitted preprocessing. Published checkpoints
are the evaluated training-split model, not a refit on held-out images.

Each version records:

- Labeled, training and validation image counts and their private IDs.
- Training/validation group counts, known subject groups and unknown-identity images.
- Display-score validation MAE and RMSE, raw validation MAE, and the training-mean
  baseline's validation MAE on the identical holdout.
- Seed, regularization, validation fraction, extractor/implementation versions and
  training duration (feature extraction through measured validation).
- An immutable consent/annotation snapshot and its SHA-256 digest.

Predictions preserve model ID/version, image ID, raw score, display score, rating scale,
timestamp, processing duration and whether the image appeared in the annotation snapshot.
Raw outputs are unbounded regression predictions; display outputs are clipped to the
owner's dataset scale. No population percentile or objective-beauty claim is made.

**Limits:** color/background/lighting may dominate this handcrafted representation.
Eight images is an operational minimum, not evidence of accuracy. Small holdouts can
be unstable or worse than the mean-rating baseline. Unknown subject identities can
cause identity leakage; there is no automatic identity recognition. Repeated tuning
against the same holdout can overfit it. Synthetic regression tests demonstrate that
learning/inference work, not accuracy on facial photographs. A reviewed pretrained
extractor can be added later with a new version; it must independently satisfy source
and weight licensing requirements.

## Jobs, snapshots and artifacts

Additive Alembic revision `0006_custom_models` follows the preserved revisions 0001–0005.
It creates custom model versions and cached image embeddings, and adds payload/progress/
phase fields to existing research jobs. Accounts, financial tables and credit mutations
are unchanged. No schema creation occurs in API startup.

Train and prediction endpoints return a durable job immediately (HTTP 202); all feature
extraction, fitting and image scoring run outside HTTP requests in the existing CPU worker.
Owner locks serialize quotas, idempotency and version allocation. Existing pending/daily
job quotas apply jointly to mock, train and prediction jobs. Up to 100 undeleted model
versions may exist per owner. NumPy/OpenBLAS uses one thread in the runtime image.

Workers renew leases every five seconds or sooner for shorter leases and maintain their
health heartbeat during execution. Progress writes and batch boundaries recheck ownership,
authorization and cancellation. Checkpoint publication and job completion happen in one
fenced DB transaction after verifying a live lease and live source images. Cancelled,
expired or superseded workers cannot publish checkpoints. Failed/abandoned file writes
are cleaned immediately where possible, with orphan recovery after one hour. Existing
bounded retry behavior remains; retries reuse the same allocated model version.

A JSON checkpoint contains finite coefficients, feature means/scales, format/extractor
versions, rating bounds and snapshot digest. It uses **no pickle or executable model
serialization**. Private immutable storage returns an artifact ID and SHA-256; inference
checks the digest and checkpoint schema before execution. There is no browser checkpoint
or weight-download endpoint. PostgreSQL retains configuration, snapshots, version history,
metrics, embeddings and jobs; files belong in `PRIVATE_MODEL_ROOT/custom/<owner>/<artifact>`.
The private model volume remains writable only in workers, read-only in API, and absent
from web/proxy containers.

Cached embeddings are keyed by image/extractor version and checked against a source-file
SHA-256. They are removed by database cascade when the source image is physically purged.
The descriptor cache remains independent of third-party model plugins.

## Consent, access, deletion and policy

Model APIs require the existing authenticated owner, Origin/CSRF checks for mutations,
research mode and a live operator grant. Cross-owner model and image requests fail.
Training snapshots contain only eligible live images/ratings owned through their dataset.
Labels are frozen at submission; later edits are used only by subsequent model versions.

Deleting or expiring a source dataset, or deleting an image in a model's snapshot,
immediately makes that model unusable. The worker removes its checkpoint, clears the
copied annotation snapshot and related job payload/results, and preserves only version
metadata/aggregate metrics. Explicit model deletion also cancels related pending work.
Archive blocks new predictions until restoration. Model deletion remains possible for
an authenticated owner after research access revocation. Physical cleanup requires the
worker; while it is down the APIs still deny use. Backup retention is managed separately.

Exclusion affects subsequent training; an existing immutable model is unchanged unless
source data is actually deleted/expired. Images with missing person IDs trigger an explicit
validation limitation. Selecting/uploading/predicting an image never assigns a rating.

Training and inference use the common registry policy gate with purpose `research`.
The first-party baseline is approved for reviewed research execution and explicitly
**not approved for commercial scoring**. The registry's default purpose remains commercial;
production mock execution still fails for either purpose. This separates reviewed
implementation permissions from potential restrictions in a user's dataset license.
The purpose is chosen by the worker, not by user request fields. Nothing here deploys a site.

## Dependency and provenance review

The fixed descriptor/regression implementation is first-party Auvylen code in
`services/inference/src/aevyra_inference/preference.py`. Checkpoints are fitted locally in
remote cloud workers from the owner's authorized annotations. No research repository,
private facial dataset, real photograph or external weight file is included in Git.

Reviewed locked distributions:

- **NumPy 2.5.4:** BSD-3-Clause main license in its installed
  `numpy-2.5.4.dist-info/licenses/LICENSE.txt`; source https://github.com/numpy/numpy .
  The wheel also retains OpenBLAS BSD-3-Clause, LAPACK BSD-3-Clause-Open-MPI and GCC runtime
  GPL-3.0-or-later WITH GCC-exception-3.1 notices. Those bundled notices remain in the image.
- **Pillow 12.3.0:** MIT-CMU Pillow/PIL license and individual bundled-library notices in
  `pillow-12.3.0.dist-info/licenses/LICENSE`; source https://github.com/python-pillow/Pillow .
  Distribution license files are preserved; runtime images install normal wheels.
- **Pretrained weights:** none. There is no implicit weight-license assumption.

## HTTP contracts and operations

Within `/api/v1/research/preferences`:

| Route | Behavior |
| --- | --- |
| `GET /models` | Owner's version metadata, state, configuration, limitations and metrics |
| `POST /train` | Dataset ID, idempotency key, alpha/seed/validation fraction → training job |
| `POST /predict` | Owned model ID, dataset/image IDs, idempotency key → prediction job |
| `POST /models/{id}/edit` | Archive/restore a completed version |
| `POST /models/{id}/delete` | Deny use and schedule checkpoint/snapshot cleanup |

Existing `/api/v1/research/jobs/{id}` and cancellation endpoints expose status/progress
and saved results. Python/TypeScript contracts and the same-origin route allowlist include
these APIs; private results are `no-store`. Ordinary users need no scripts/model server.

Run explicit migrations/check before the updated API/worker. Existing cloud Compose
volumes, grants and private storage configuration apply. Back up PostgreSQL, private
uploads and private models consistently following `cloud-backups.md`, and preserve matching
credentials outside Git. Restore all three stores, migrate/check, run retention cleanup,
and only then serve user data. A temporary Codex environment is development compute,
not a permanent host or the only backup for important personal models.

See `phase4b-training-report.md` for executed verification, GitHub preservation and results.
