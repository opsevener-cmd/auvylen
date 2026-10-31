# Pretrained model integration — independent implementation, 2026-10-31

Status: **implemented but disabled; not a validated or deployable scoring release**.
This replaces the earlier feasibility-only position with an optional ComboLoss adapter,
private upload/queue/worker execution, deletion/retention, bilingual native-scale UI and
an offline reference/CPU benchmark command. No weights, datasets or private portraits
are committed. Personal preference models and Phase 6 calibration are unchanged.

## Provenance and rights audit

Official sources inspected outside the repository:

- ComboLoss `2543efff58b287cb7b0ca4f7665d36855e8c62d9`:
  https://github.com/lucasxlu/ComboLoss . MIT code (LucasX, 2019); full notice included
  with the adapter. Official checkpoint is linked separately from README to Google Drive
  (`1O9T41BJglXBWlm6nJCuHIGzl3iSDvBdc`). No checkpoint-specific permission for this
  service was established. A public download is not proof of commercial permission.
- SCUT-FBP5500 official release:
  https://github.com/HCIILAB/SCUT-FBP5500-Database-Release . Its notice expressly permits
  only non-commercial research; the disclaimer also specifies academic research.
  It describes internet-sourced faces and ratings from 60 volunteers on a 1–5 scale.
  Whether the proposed product's private research service falls within those terms,
  and permission for the separately distributed derived weights, remain unresolved.
- FPEM `c2965425247d7bf8b764d27e4483a06fc7a061e5`:
  https://github.com/Estella-LH/FPEM . MIT code (Estella-LH, 2025), but that alone does
  not establish rights for checkpoints, LiveBeauty, CLIP, SwinFace and face-recognition
  components. Official configuration combines FACLIP/SwinGFVQA features with several
  input sizes; requirements pin Python-era CUDA torch 1.13.1, torchvision 0.14.1,
  timm 0.5.4, facenet-pytorch, CLIP Git dependency and protobuf 3.19.0. It is not a
  drop-in lightweight CPU portrait predictor. No second provider was enabled.

The user confirmed no checkpoint hash or weight permission evidence is available.
No inference using uncertain weights was performed. Checkpoint identity, actual reference
predictions, dependency compatibility and CPU inference latency/RSS are **not verified**.
No published benchmark number is represented as a measurement on this machine.
No synthetic output, random-weight score, ensemble or retraining substitutes for this.
Independently implementing published ideas is distinct from permission to reuse artifacts;
blending checkpoints does not establish rights to their component weights.

## Architecture and fidelity

`plugins/comboloss` is a separately installable/removable Python distribution using the
existing `auvylen.model_providers` entry point. It is excluded from default dependencies.
Missing installation, dependencies, checkpoint, pinned integrity or rights makes it
unavailable. No startup/runtime downloads occur. PyTorch/torchvision/pytorchcv pins in
its metadata are candidate runtime pins pending actual-weight equivalence testing.

The adapter matches official `models/nets.py`: pytorchcv `seresnext50_32x4d` features,
2048-feature regression branch and five-class branch. It constructs the backbone with
`pretrained=False` because the full checkpoint supplies its weights; no silent ImageNet
substitution occurs. CPU-only state-dict loading uses `weights_only=True`, strict keys
and supports the upstream all-`module.` prefix. Checkpoint maximum: 160 MiB.

Official inference preprocessing: PIL Resize(224), CenterCrop(224), ToTensor,
ImageNet mean `[.485,.456,.406]` and std `[.229,.224,.225]`. The regression branch is
returned; classification logits are not treated as calibrated probabilities. Native
annotator scale is 1–5; regression may extrapolate. No clamping, 1–10 conversion,
face alignment, age estimation or error calibration is added. Current library default
resizing equivalence must be checked against actual upstream predictions before release.

HTTP input is canonicalized to EXIF-oriented, metadata-free RGB PNG with original RGB
pixels preserved (unlike the existing JPEG derivative). Reference comparisons must use
that identical canonical input. JPEG/PNG decoding reuses existing 4-MiB, 4096px,
16-megapixel and decompression limits; shorter edge must be >=224px. Canonical storage
has an additional 10-MiB ceiling. Whole/cropped-face domain differences remain material.

## Security and operational review

- New `/api/v1/research/pretrained/comboloss` requires authenticated research entitlement,
  Origin/CSRF, explicit adult/single-subject/consent attestations, rate/admission limits.
  It reuses user locks, idempotency and the existing durable CPU queue/resource caps.
- UUID-owned private files use the existing immutable 0600/0700 artifact store. There is
  no image-serving endpoint. Model weights never enter the web container or browser.
- Worker rechecks availability, image hash and pinned manifest identity. A child process
  isolates heavy imports and has a 90-second wall timeout, 60-second CPU limit,
  4-GiB address-space cap and single-thread settings. Failed work produces no score.
  Completion uses existing heartbeat, authorization and lease fencing.
- Final/failed/deleted images are purged; stale images/results expire after 24 hours.
  Existing GET/list views hide expired results even when worker cleanup is offline.
  Physical deletion requires a healthy worker; monitor cleanup/heartbeat and the private
  volume. Crash-before-commit orphan files are swept after 24 hours.
- Owned deletion fences running work and clears its result. It remains available after
  research revocation. Existing Origin/Codespaces logic is unchanged.
- All routes inherit private `no-store` middleware. Credits, payments, Owner privileges,
  personal models and existing photo/data retention are untouched. No schema change.
- Deployment environments are explicitly blocked; commercial policy is always false.
  This PR does not enable scoring or deploy anything.

## Installation and release checklist (operator review required)

1. Obtain and record rights covering the intended research service for code, weights
   and data; commercial release requires separate commercial evidence. Inspect the
   official checkpoint offline and compute its SHA-256. Do not commit it.
2. Install the adapter in an isolated, bounded worker environment; API discovery also
   needs the adapter/dependency availability checks. Do not add it to default production
   dependencies. Resolve and lock the candidate runtime and review transitive licenses.
3. Place immutable files at `PRIVATE_MODEL_ROOT/comboloss/{checkpoint.pth,manifest.json}`.
   Manifest fields: `source_commit` (pinned above), `checkpoint_sha256`, `native_scale:[1,5]`,
   `reference_verified:true`, and `rights:{reviewer,code_license,weights_permission,
   dataset_permission,research_service_allowed:true}`. Permission fields are review
   references, not a grant generated by software. Never set them without evidence.
4. Reproduce official inference on >=3 authorized, identical canonical inputs; verify
   strict checkpoint loading and preprocessing, and record independent expected scores.
   Only mark `reference_verified` after that review. Then run
   `python -m auvylen_comboloss.verify ROOT REFERENCES.json` to repeat comparisons and
   measure cold load, warm decode/preprocess/forward and peak RSS. Harness tolerance is
   1e-5; do not relax without an explained numerical audit. Reference file format is
   documented in that module. No benchmark results are supplied because weights are blocked.
5. Pin the reviewed manifest's exact SHA-256 with `COMBOLOSS_MANIFEST_SHA256` in both API
   and worker; use `ENABLED_MODEL_PROVIDERS=["comboloss"]` and existing private research
   entitlement. The manifest is rehashed before each load; checkpoint hash is rechecked.
   Test revocation, cancellation, worker death/reclaim, timeout, corrupt files and cleanup
   under real runtime load before enabling any service. No ONNX export before equivalence.
6. Staging/production remain blocked in code pending a further release review. Preserve
   external encrypted backups, private forwarding and established Codespace procedures.
   Remove the plugin/enable-list entry to disable it without touching personal models.

Review evidence: backend/frontend tests and browser checks are recorded in the PR.
Fixture tests verify safety and transport, not human aesthetic validity. Genuine inference,
reference comparisons and CPU model benchmarks are open blockers, not passing tests.

## Local verification evidence

- Backend regression: 197 passed, 29 environment/opt-in skips. Isolated security/transport
  cases: 3 passed, including missing weights, review/integrity failure, RGB preservation,
  permission denial, no-Credits queue submission, worker failure and private-image deletion.
- Frontend: 145 unit tests, lint, TypeScript and production build passed.
- Production Chromium checks: [English desktop](pretrained-en.webp),
  [Chinese mobile](pretrained-zh-CN.webp). Unavailable model disables upload/prediction,
  renders no score, and fits the viewport. A bilingual persistence regression is added.
- Real pretrained model inference, actual-weight preprocessing parity, numerical reference
  comparison and CPU model benchmarking were not run and must not be inferred from the
  fixture tests. Existing opt-in real-model tests are not a ComboLoss validation.
