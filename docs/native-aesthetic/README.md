# Auvylen Native Rating v1 — original population-model research

2026-10-31. Separate draft implementation from `d2223bf`, independent of PR #11 and
its ComboLoss adapter. **No authorized human aesthetic training collection was available.**
No production rating model was trained, installed or enabled. The deliverable is a
working offline annotation/training/evaluation/checkpoint/provider pipeline, verified
with explicitly generated test fixtures, plus actual encoder CPU measurements.
It is not a ready-to-use aesthetic predictor.

## Continuity and original architecture

Phase 6 already implemented an original five-category vote-distribution model and
secure population inference. It remains intact, as do personal preference models.
This candidate addresses a different training contract: real human mean ratings on
an explicitly defined native **1–5** scale, without manufacturing vote distributions.

1. Frozen, already reviewed MobileNetV3-Small ImageNet encoder (1024 features).
2. Training-only standardization, followed by a ridge regression head and native
   `[1,5]` clipping. Objective: sum squared residuals plus alpha times squared weight
   norm; the intercept is unpenalized. Clipping is part of this model's definition,
   applied equally during validation, test and runtime. No 1–10 conversion or calibrated
   confidence interval is claimed.
3. Original Auvylen implementation of training, model selection, provenance and inference;
   established MobileNet architecture/weights are attributed, not claimed as an invention.
   There are no ComboLoss/FPEM/other attractiveness weights or pseudo-labels.

The small linear head is deliberate: limited initial data, inexpensive CPU fitting,
transparent baselines and no GPU requirement. Both primal and dual ridge solves use
whichever matrix is smaller. Fine-tuning a CNN, adding a multilayer head or trying larger
encoders should follow evidence of underfitting on a genuinely independent validation
collection. Complexity cannot compensate for missing labels.

## Data investigation and exact blockers

Primary sources checked on 2026-10-31:

| Source | Images / annotations | Decision for this environment |
| --- | --- | --- |
| [SCUT-FBP5500 official release](https://github.com/HCIILAB/SCUT-FBP5500-Database-Release) | Images and aesthetic labels released for non-commercial research; sourced from several collections and the internet | Not cleared for this intended service or commercial release. No independently verified adult-only image/annotation authorization ledger was supplied. No download/training. |
| [Chicago Face Database official terms](https://www.chicagofaces.org/) | Photographs and subjective norms restricted to non-commercial scientific use; redistribution to cloud/file-hosting services restricted | Not appropriate to ingest into this cloud workspace under the published default terms. No download/training. |
| [FairFace official release](https://github.com/joojs/fairface) | CC BY 4.0 stated for data; demographic annotations, not aesthetic ratings | No aesthetic supervision. Dataset licence does not itself verify each source image's adult status, subject release or all intended-use rights. Do not turn demographic labels into aesthetic labels. |
| [FFHQ official release](https://github.com/NVlabs/ffhq-dataset) | Public portrait resource, not an authorized Auvylen aesthetic annotation collection | No cleared human aesthetic labels available here. Not selected or downloaded. |
| Existing private account datasets | Personal/private consent and ratings are for their owned research workflow | Never inspected, repurposed or pooled into a platform training collection. |

A research-only data licence can authorize uses within its scope; a separate written
permission is not automatically necessary when a licence already covers a use. Here,
the necessary combination of cloud use, adult consent, image rights and genuine rating
rights was not established. No claim is made that public availability resolves it.

Encoder rights are a separate question: existing reviewed timm MobileNetV3-Small
weights explicitly carry Apache-2.0 in their pinned configuration; code and conversion
notices are in [the representation review](../pretrained-representation.md). The ImageNet
training images are not re-licensed by that statement. Existing approval remains
non-commercial research only; this PR adds no commercial approval or new export.
Original head weights would derive from the approved collection and their own grant.

## Reproducible collection and training

All commands run offline in the isolated cloud development environment, with private
operator storage and no live account/database operation. Do not commit their inputs,
outputs, portraits, annotations, consent records or learned weights.

1. Prepare a private collection plan JSON matching `native_data.Collection`. Required
   top-level fields: `name`, `encoder_rights_review`, `annotator_population`,
   `rating_protocol_reference`, `synthetic` and `rights`. The `rights` map uses opaque
   source IDs; each record separately cites `image_license`, `annotation_license`,
   `subject_release`, `training_permission`, `derived_weight_permission` and `reviewer`,
   plus confirmed `adult_confirmed:true`, `research_allowed:true` and a commercial flag.
   These are evidence references requiring human review, not permissions created by code.
2. Raw CSV columns must be exactly
   `image,subject_id,rater_id,rating,rights_id,cohort`. Identifiers are pseudonymous.
   Raters must follow the documented common 1–5 anchors. Collect independently; never
   use model predictions, demographic attributes or synthetic distributions as labels.
3. Aggregate real votes, rejecting repeated rater/image votes and inconsistent subject
   or rights assignment:

   ```bash
   uv run python -m aevyra_inference.native_data \
     private-data/native/raw-votes.csv private-data/native/means.csv
   ```

   Output is `image,subject_id,rating,rating_count,rights_id,cohort`, preserving real
   arithmetic means/counts. At least three raters per photo are required; ten are
   recommended. An already aggregated authorized dataset may use this format directly,
   but its count/protocol evidence must be audited separately.
4. Train both encoders, with the exact existing reviewed graph installed privately:

   ```bash
   OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run python -m aevyra_inference.native_train \
     --labels private-data/native/means.csv --images private-data/native/images \
     --plan private-data/native/collection.json --encoder-root private-data/models/pretrained \
     --output private-data/native/candidate-v1 --seed 42
   ```

   Missing either encoder fails; there is no silent substitute. The output directory
   must be new. The command prints aggregate evaluation and a manifest hash; a failed
   release gate is reported explicitly and does not enable the provider.

The initial CPU budget is 3000 images, <=10 MiB each, <=256 MiB total encoded input,
and <=100,000 raw votes. Images are bounded single-frame JPEG/PNG, 224–4096px;
training rejects exact duplicate decoded pixels, including differently encoded copies.
Path traversal/symlinks outside the collection are refused. Human curation must also
resolve near-duplicates, repeated identities and source-family leakage; the software
cannot establish identity or adulthood from a face.

## Experimental protocol and release gates

- Stable subject-hash split: 60% train, 20% validation, 20% test. Every photograph of
  the same person must share an ID. No random per-image split. Dataset/label/code hashes
  and seed are recorded for repeatability; permanently seal the test collection before
  repeated experimentation. A new near-duplicate or identity audit may require new splits.
- Fixed train augmentation: clean, brightness ×0.85 and central 90% crop. Batched
  extraction prevents retaining all augmented images in RAM. Statistics and heads
  see only train subjects. Hyperparameters `[0.01,1,100]` and encoder choice are selected
  by validation MAE with deterministic tie-breaking. Test labels do not choose the winner.
- Held-out MAE, RMSE and Spearman are native-scale metrics. Comparators include train
  mean, train median and each encoder's validation-selected ridge model. Undefined
  correlation remains null. Subject-macro MAE supplements image-weighted metrics.
- Report test cohort metrics/counts using declared acquisition metadata; never infer
  sensitive traits from appearance. Underpowered groups are flagged by the release gate.
- Lighting, crop and small rotation probes report score drift and comparison against
  original labels. Those labels are **not new human ratings of the altered photographs**.
  Rotation tests in-plane sensitivity; it does not validate yaw/pitch robustness.
  Real pose/session photographs with genuine re-ratings and subject-separated assessment
  require an external `--pose-review` evidence reference before release.
- Current minimum engineering gates: >=30 test photos, >=10 test subjects, lower MAE
  than both constant baselines, Spearman >=0.3, populated cohorts with >=10 photos and
  >=5 subjects, recorded real-pose review, and mean perturbation drift <=0.3 native points.
  Synthetic data, non-finite or incomplete reports fail. These preliminary thresholds
  are not scientific certification or proof of commercial rights; preregister a stronger
  sample-size/uncertainty protocol before releasing a real model.

**Actual aesthetic MAE/RMSE/rank, robustness and imbalance results: unavailable.**
No authorized human-rated experiment ran. Generated-fixture tests verify mathematical
learning, train/test separation, complete pipeline execution and failure behavior;
they are not aesthetic experiments and their fitted weights/metrics are not published.

## Actual CPU measurements

[Raw encoder measurements and exact provenance](encoder-benchmarks.json), Linux x86_64,
2-core quota, 8 GiB memory limit, single-thread CPU execution, 30 warm repetitions on
one generated non-face JPEG. No aesthetic head was used and no score was generated.

| Encoder | Warm median decode/preprocess/extract | Warm p95 | Peak process RAM | Graph size |
| --- | ---: | ---: | ---: | ---: |
| MobileNetV3-Small | 4.00 ms | 4.35 ms | 97.8 MiB | 6,078,515 bytes |
| Handcrafted RGB/texture | 1.54 ms | 1.88 ms | 45.6 MiB | No learned graph |

MobileNet cold initialization measured 48.8 ms. These are generated-input feature
benchmarks, not portrait-service latency, end-to-end trained-model benchmarks or a
promise about Codespaces/network latency. Repeated features agree within 1e-8; the
existing export-equivalence review is unchanged. No new optimization or quantization
was introduced. Reproduce with `python -m aevyra_inference.native_benchmark --encoder
mobilenetv3-small-imagenet-onnx-v1 --root private-data/models/pretrained` (and the
handcrafted ID `rgb-grid-texture-v1`). A MobileNet ridge head would add 24,584 bytes,
but no human-trained head exists here and its latency is not presented as measured.

## Provider, security and integration

`NativeProvider` plugs into the existing catalog as `auvylen-native`, disabled by default.
Its private directory is `PRIVATE_MODEL_ROOT/auvylen-native`. Runtime requires the exact
`AUVYLEN_NATIVE_MANIFEST_SHA256` pin, a matching raw float64 head and the precise encoder
manifest. It rejects missing/corrupt/incompatible/unreleased checkpoints; no pickle or
runtime download is used. The engine emits native 1–5 scores and always refuses commercial
and production approval in metadata. Model files remain private, 0600, in a new 0700 folder.

This PR intentionally adds no user upload or training endpoint and does not enable the
unmerged PR #11 page. The existing authenticated upload, worker leases, ownership,
Origin/CSRF, Owner controls, private storage, Credits and backup paths are unchanged.
No user can submit a native-model image through the legacy payload-free job endpoint.
After a real model passes review, connect the selected native provider to the shared
single-image analysis transport and bilingual page, with the same authorization,
resource, retention and deletion protections. Do not route it through Phase 6's 1–10
presentation or the personal training workflow. CLI/internal provider readiness alone
is not a released user experience.

## Legally viable acquisition and release plan

Commission an opt-in adult collection instead of scraping public portraits. Proposed
pilot: 500 independent adults, two consented capture sessions/conditions each, ten
independent ratings per photo (10,000 genuine judgments). Collect variations of lighting,
crop and real pose across sessions; keep every person's sessions in one split. Recruit
across planned, self-reported acquisition cohorts and document annotator population and
sampling imbalances. Do not promise that numerical balance alone establishes fairness.

Obtain separate photographer image rights, participant adult/subject releases covering
this intended model-training use, annotator-label rights, and permission to retain/use
and distribute resulting weights as needed. Define permitted commercial use explicitly.
Keep signed evidence private, handle withdrawal prospectively via versioned collection
and retraining procedures, and document that published model weights cannot simply be
"unlearned" by deleting a JPEG. No external messages, paid collection or spending occurred.
Costs/timing need supplier quotes and an authorized collection plan.

Before release: audit rights/identity/near-duplicates; freeze protocol/test set; run
training and independent holdout evaluation with uncertainty bounds; conduct genuine
pose/lighting re-rating and cohort review; benchmark cold/warm full portrait inference
and peak RAM; review head/encoder rights separately; pin hashes; then integrate/test the
bilingual user flow, permission revocation, deletion, cancellation and worker recovery.
Obtain explicit release approval. Keep external encrypted backups and private forwarding.
No merge, deployment, schema migration or live-data operation is part of this PR.

## Verification recorded for this draft

- Offline backend suite: 198 passed, 29 integration/opt-in skips; skips are not claimed
  as integration passes. Four new native-model tests cover actual fitting on mathematical
  fixtures, test-label isolation, train-only augmentation dimensions, complete private
  training/checkpoint round-trip, synthetic release denial, hash tampering, immutable
  output, ingestion rights/path/duplicate checks and repeated-rater rejection.
- Existing real MobileNet extraction tests with the exact reviewed graph: 3 passed.
  These verify representation execution/determinism/changed-input behavior, not beauty.
- Frontend: 145 unit tests, ESLint, TypeScript and production build pass. The first type
  check found stale generated types from PR #11; regenerating route types on this separate
  base resolved it. No unrelated route or UI was imported.
- Ruff lint/format and strict mypy pass. Full GitHub CI outcomes are recorded in the PR.
- No real aesthetic weights or subjects/ratings were exported or committed. The only
  experimental report in source control is the explicitly scoped encoder benchmark JSON.
