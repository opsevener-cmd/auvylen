# Phase 6 recovery and independent review — 2026-10-27

The supplied SHA256SUMS verifies both original recovery files:

- Bundle: `2ac37375f3faeb29e095a1859d40f18abbd79e6166b63593721d49b9229c3fcf`
- Patch: `9f4a8aaf1abb72626b5127d73432e932afa5dda11c25f4b06219d729a6edb858`

Git verified the bundle prerequisite `18069720def42ce033cbc6b6465d2825be36c4ae`.
Imported commit `f2e6ed7e89b45d0d9cc26cce9e492329d1bac6f7` retains Claude's authorship,
parent and all 40 changed files. There were no deleted files. The patch was not applied.
Review corrections are separate descendant commits, not a replacement implementation.
Recovery artifacts and model artifacts are not committed to the repository.

## Review findings and corrections

1. **Calibration reused model-selection subjects.** Early stopping and conformal
   residuals previously used the same validation images. Half of the original
   validation subjects now form a separate calibration cohort. Maximum residuals
   per person avoid treating correlated photos as independent observations. Tests
   prove calibration labels cannot alter the fitted head and all four cohorts are
   disjoint. The release gate rejects the old reused-validation calibration method;
   old checkpoint bytes remain loadable for inspection. Retraining must publish a
   new immutable version.
2. **Non-finite metrics could pass numeric comparisons.** The release gate now
   refuses NaN, infinity and booleans rather than accepting their comparison behavior.
3. **Retention depended on worker cleanup.** Expired results are now hidden from
   reads/listing immediately, even while cleanup is offline. Their owner can still
   request deletion. A regression verifies this without invoking the purge worker.
4. **Duplicate-image detection only compared encoded bytes.** Offline training now
   checks decoded RGB pixels and dimensions after EXIF orientation, so PNG metadata
   cannot disguise duplicates across subject groups. It still cannot establish that
   different photographs depict the same person: trustworthy subject labels remain
   required. Untrusted I/O exception text is no longer printed by the training CLI.
5. **Selection could change during an active upload.** The new analysis picker and
   consent controls are disabled while submission is in flight.

The CDF objective, softmax-chain gradients and regularization gradients agree with
finite differences. Training-only normalization, held-out test perturbation, tied
Spearman ranks, baselines, checkpoint digests and exact extractor compatibility are
covered. Existing account/Owner/Credits/personal-model regressions are retained.
The new feature does not spend Credits or modify personal datasets/models. API
submission enforces sessions, research entitlement, CSRF/Origin, bounded consented
uploads and private storage. The durable queue fences stale completions and removes
images after success/failure; retention cleanup recovers stale/orphan files.

## Real weights and CPU measurement

Installed the exact reviewed CPU export toolchain and verified both the original
MobileNet source checkpoint and exported ONNX graph. Graph SHA-256:
`164c481657afe9d36e08ff58693df24e511b5bf1a07de9b9389dfc468eedd2a6`.
Only ignored private workspace storage contains weights. No alternate graph or
unreviewed extractor was substituted.

`verify-aesthetic-mobilenet.py` exercises 96 generated PNGs -> actual CPU MobileNet
features (96×1024) -> aesthetic fitting -> immutable checkpoint round trip ->
image inference. Median timings were **5.00 ms warm**, **31.50 ms cold** (including
manifest/head verification and ONNX session creation); p95 **6.94/41.81 ms**.
Batch extraction took **0.705 seconds**. See [raw results](phase6/mobilenet-verification.json).
These measure the compute path, excluding HTTP/queue/database latency. They are not
live Codespaces measurements. Generated pixels and simulated categorical votes
verify engineering only; they do not validate human aesthetic scoring. The head
was not enabled in the application. The opt-in automated pretrained regression
repeats this combined path, and backend CI installs the exact reviewed weights.

Cross-runner diagnostics found identical graph structure and source tensors but
floating-point differences in folded convolution tensors. MKL execution branches
produce different bytes: COMPATIBLE/SSE4_2/AVX2 exports differ from the pin, while
AVX512 reproduces it locally. CI pins the Debian 13/Python 3.14.8 export container
and MKL AVX512 branch, with a writable Torch cache for its non-root UID. Every
export still must match the original full graph SHA before installation. Unsupported
hardware must fail rather than install different weights. Existing personal-model
extractor compatibility and the reviewed hash are unchanged.

## Verification

Local results: **216 backend/integration/pretrained tests passed with no skips**;
**133 frontend tests passed**, lint/format/type checks and production build passed.
Browser checks: **7 passed / 1 mutually exclusive checkpoint test skipped** without
an installed scoring checkpoint, then **1 passed / 1 unavailable-state test skipped**
with the explicitly synthetic checkpoint. Together these exercise both modes.
The first overlapping browser/backend run timed out waiting for an account; the
complete browser run passed with exclusive use of test services.

Final PR CI results are recorded in the PR description. Checks include
all backend/integration/pretrained regressions, Python lint/format/mypy, frontend
unit/lint/type/build, unavailable-state bilingual browser behavior and a separate
explicitly synthetic worker scoring/deletion flow. Migration 0009 was exercised
with upgrade 0008 -> 0009 -> downgrade 0008 -> upgrade 0009 and schema comparison
in a newly created disposable PostgreSQL database, not an existing user database.

## Limits and rollout

Real scoring stays disabled. Authorized adult-only photographs, genuine per-image
human vote distributions, trustworthy subject identifiers and an approved checkpoint
remain unavailable. Neither synthetic labels nor ImageNet weights establish aesthetic
accuracy. No automatic face/age inference, real payment integration or public launch
is included. Test-set release thresholds are engineering safeguards, not independent
external validation; repeated tuning against the same test cohort requires a new
external cohort before a scientific accuracy claim.

No live Codespace, private photo, Owner account, dataset or backup was accessed.
Do not merge or deploy automatically. After user review, preserve and verify an
external encrypted backup using the existing procedure. Update the existing private
Codespace without resetting accounts, volumes or credentials, and run migration
0009 only through the established authorized migration gate. It adds only the new
analysis table. Keep `AESTHETIC_SCORING_ENABLED=false`; a validated human-data
checkpoint and explicit approval are required before pinning/enabling real scoring.
