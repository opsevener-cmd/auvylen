# London Set: genuine human-rated feasibility result

2026-11-01. Continues draft PR #12. **GO: private research feasibility. NO-GO: service release.**
An actual first-party model was trained and evaluated. No public model, UI, deployment,
participant recruitment or private account-data reuse was enabled.

## Acquisition decision and rights

Select the **Face Research Lab London Set**, DeBruine & Jones (2017), Version 5,
[DOI 10.6084/m9.figshare.5047666.v5](https://doi.org/10.6084/m9.figshare.5047666.v5).
The authors' [neutral image-set release](https://github.com/debruine/webmorphR.stim)
identifies adult subjects, CC BY 4.0, and signed consent for lab/web research.
The authors' [rating-data documentation](https://github.com/debruine/demopsydata/blob/1b5d2a179edd873162a54dec11faff2163afe6c0/R/data.R)
links the genuine human ratings to that same London release.

| Right / evidence | Pilot decision | Service decision |
| --- | --- | --- |
| Photograph copyright | Author-distributed CC BY 4.0 neutral set; attribution retained | Copyright permission alone does not settle participant privacy/publicity rights |
| Annotation/database rights | London ratings included in the CC BY release; author-distributed original CSV | Retain attribution; do not infer broader consent from a software licence |
| Subject permissions | Authors report signed adult-subject consent for lab/web studies; use is a closed research study | No evidence here that subjects endorsed this consumer/commercial face-scoring service |
| Learned weights | Internal research adaptations using cleared study inputs; kept private | No public weight release or commercial approval claimed |
| Encoder | Existing reviewed MobileNet Apache-2.0 configuration/graph, unchanged | Existing research-only application policy remains; no new commercial approval |

CC BY 4.0 permits reproduction/adaptation under its conditions and has no academic-only
copyright restriction. It does not itself grant privacy/publicity rights; see
[legal code section 2(b)](https://creativecommons.org/licenses/by/4.0/legalcode.en).
The separate published research consent supports this closed feasibility study.
We deliberately do not turn this assessment into permission for a public consumer service.
No author/participant was contacted, no terms gate was accepted on someone else's behalf,
and no payment was made. Figshare direct retrieval was unavailable through the browsing
interface; data were obtained from the same authors' official GitHub distributions,
not an unofficial mirror. No network-policy bypass was used.

Other reviewed options: [MEBeauty's official maintainer terms](https://huggingface.co/datasets/dr-irina-lebedeva/MEBeauty-Facial-Beauty-Prediction/blob/main/LICENSE)
restrict academic use, exclude photograph rights and prohibit commercial use/redistribution;
SCUT-FBP5500 is non-commercial research; Chicago Face Database restricts cloud redistribution;
FairFace has no aesthetic supervision. None was substituted into this experiment.
This corrects the earlier draft's incomplete dataset search: an existing research pilot
was possible, although intended-service clearance is still incomplete.

## Fixed study and actual data

[Protocol fixed before fitting](protocol.md). Official image inventory: 102 adult neutral
frontal portraits. Use **100 subjects with reported ages 18–54**; two with missing age
were excluded instead of estimating age from a face. Use only **2,324 existing rater
records with reported age >=18**, out of the source 2,513. Each eligible image has 2,324
real ratings: **232,400 judgments used**, with no model-generated labels.

Keep the source's native **1–7 relative-to-average attractiveness scale**. There is no
1–5 or 1–10 conversion. Mean-label standard error median is 0.029 native points,
conditional on these rater records. These targets describe that rater pool, not objective
beauty, a person's worth or a representative global population.

Seed 42 subject-hash partitions: **60 train / 20 validation / 20 test**. One neutral
photo per person; no subject appears across partitions. Normalization and brightness/crop
augmentation use training subjects only. Compare both encoders at ridge alpha .01, 1, 100;
validation MAE fixes the winner. No hyperparameter, seed or architecture was changed after
reading test outcomes. Reproduction used the original validation-selected alpha for each
encoder and produced **byte-identical winning head weights**.

## Genuine held-out results — native 1–7

| Fixed candidate | MAE | RMSE | Spearman | Selected alpha |
| --- | ---: | ---: | ---: | ---: |
| MobileNetV3-Small + Auvylen ridge (validation winner) | 0.510 | 0.640 | 0.367 | 0.01 |
| Handcrafted + Auvylen ridge | 0.489 | 0.621 | 0.283 | 100 |
| Train mean | 0.572 | 0.652 | Undefined (constant) | — |
| Train median | 0.563 | 0.637 | Undefined (constant) | — |

The handcrafted model has lower test MAE; **it was not promoted using the test set**.
MobileNet's RMSE is slightly worse than the median baseline. These are small-sample
feasibility findings, not evidence that one architecture is reliably superior.

Subject-cluster percentile bootstrap, 2,000 draws, seed 20261101, 95% intervals:

| Metric | MobileNet | Handcrafted |
| --- | --- | --- |
| MAE | 0.346–0.681 | 0.326–0.654 |
| RMSE | 0.471–0.788 | 0.427–0.785 |
| Spearman | −0.163–0.747 | −0.163–0.669 |
| Paired MAE difference vs train mean (negative is better) | −0.222–0.095 | −0.243–0.068 |

Both rank intervals cross zero and both paired MAE-difference intervals cross zero.
Uncertainty is conditional on this fixed fitted model and rater pool; it does not include
all population, model-selection, annotator or dataset-shift uncertainty. The same raters
scored multiple faces. Intervals are performance intervals, **not calibrated individual-score
ranges**. No p-value or universal aesthetic-validity claim is made.

Held-out, self-reported groups (no demographic inference): female 11 / male 9;
white 14 / black 4 / west_asian 2; age 18–29: 14 / age 30+: 6. There are **zero**
held-out east_asian subjects and zero subjects in the source mixed category. All
train/validation/test counts (including zeroes) are recorded in `subgroup_partition_counts`
in evaluation.json. Original source category spellings are retained. No split seed was
redrawn to repair coverage after seeing outcomes. Group metrics/intervals
are in [evaluation.json](evaluation.json); performance is suppressed for n<5. The counts
are too small for reliable subgroup comparisons or fairness claims. Lighting/crop/rotation
sensitivity probes are in [provenance.json](provenance.json). Their labels are original
ratings, not fresh human ratings of the altered pictures. In-plane rotation is not real
pose validation. This single studio/city/capture-era sample does not establish performance
on casual uploads, other backgrounds, older adults or new rater populations.

## CPU-verified saved checkpoint and portrait inference

A separate process verified manifest/head/encoder hashes, loaded the saved human-trained
checkpoint and performed complete JPEG decoding → preprocessing → MobileNet → learned
head prediction on the first sealed holdout portrait. Its individual prediction is saved
only in private `private-data/native-london-pilot/inspection.json`, never in this report.
Thirty repeats had zero prediction drift; reloading the saved head also had zero difference.

- Model initialization: 47.2 ms; first portrait CPU decode/encoder/head: 47.6 ms.
- Warm portrait CPU median: **28.5 ms**, p95 **32.7 ms**.
- Peak process RAM: **117.7 MiB** on the 2-core / 8-GiB environment, one execution thread.
- Learned head: **24,584 bytes**; reviewed encoder: **6,078,515 bytes**.
- [Exact measurements](portrait-benchmark.json); [hashes/provenance](provenance.json).

These include real portrait decoding and the learned head, unlike the earlier generated-pixel
encoder benchmark. They exclude HTTP upload, queue wait and filesystem image-read latency;
no service-endpoint benchmark is claimed. Research inspection is deliberately a separate,
unregistered offline tool. It does not bypass any product ModelProvider gate or enable
an unreleased model in the application.

## Go / no-go and PR coordination

**NO-GO for service/model release.** Existing gates fail for fewer than 30 test images
(20 images/20 subjects), absent genuine pose review, and underpowered cohorts. Uncertain
baseline improvement and rank correlation reinforce that decision. The field name
`insufficient_test_subjects` covers the image-count threshold too; the 20 test subjects
exceed the separate minimum of ten. No gate was relaxed for this pilot.

Keep native disabled and PR #12 draft. Do not integrate scoring into the bilingual
single-photo page yet. PR #11 remains independent, unmerged and blocked; none of its
ComboLoss package/routes/weights is imported or activated. No duplicate provider was
created: this extends `auvylen-native` and the existing native training path only.
Checkpoint v2 preserves declared 1–7 bounds; v1 1–5 checkpoints still load unchanged.
The native product engine continues requiring all release checks, correct pins and policy.

Next evidence: independent consented captures with real lighting/pose changes, larger
sealed holdouts and adequate subgroup samples, plus explicit intended-service consent
and commercial rights review. [Ready-to-review opt-in consent/rating/removal procedures](opt-in-procedures.md)
are prepared for a later authorized pilot. No participants are being collected now.

## Reproduction and private retention

1. Obtain the two **official author repositories** with `--filter=blob:none --no-checkout`.
   Pin image source `fa8b78fda2d659bb74ce62fcd99c4407551d2a77` and annotation source
   `1b5d2a179edd873162a54dec11faff2163afe6c0`. Do not execute repository code.
2. Into a new private 0700 directory, copy only author `inst/neutral_front/[0-9][0-9][0-9]_03.jpg`
   files to `images/`, and annotation repo `inst/extdata/london_faces_info.csv` to
   `source-info.csv`, `inst/extdata/london_faces_ratings.csv` to `source-ratings.csv`.
   Files must be 0600. Use `git show COMMIT:path` to acquire pinned blobs. Do not print photos
   or rows. The importer verifies exact source hashes and the eligible image inventory.
3. `uv run python -m aevyra_inference.native_london private-data/native-london-pilot` prepares
   genuine means, a separate rights plan and private metadata. It refuses overwritten outputs.
4. Run `native_train` with that root's `means.csv`, `images`, `collection.json`, reviewed
   `private-data/models/pretrained`, a **new** output directory and seed 42, as in the parent
   README. Exported checkpoint v2 records 1–7; do not set a production pin or copy it into
   an active model slot. Repeat with `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1`.
5. `native_london_evaluate --root ROOT --checkpoint MODEL --encoder-root ENCODERS
   --manifest-sha256 SHA` replays the fixed heads, verifies winner byte equality and reports
   aggregate bootstraps without selecting from test results. Fresh inspection-selection
   output is required; no result is overwritten.
6. `native_inspect --checkpoint MODEL --encoder-root ENCODERS --image APPROVED_HOLDOUT
   --output PRIVATE_NEW_JSON --manifest-sha256 SHA` performs offline research inference.
   It rejects synthetic training data; its stdout contains timing only, individual output
   stays 0600. This command does not expose an HTTP route or relax product loading.

Use modules with prefix `uv run python -m aevyra_inference.`. Raw data/weights/individual
outputs stay gitignored; only aggregate evaluation is committed. The fitted implementation
hash is retained; subsequent compatibility/validation hardening can change source bytes,
but exact-protocol learned-weight reproduction was verified. Preserve attribution and
upstream notices. No image/label is redistributed with the application.

Review or remove these new private research copies within 30 days of the pilot. Raw source
CSVs include unused fields which never enter training/reports; restrict access and erase
unneeded source metadata after audit acceptance. Handle author/participant removal notices
by stopping use, retiring affected checkpoints, deleting copies/derivatives and applying the
backup retention process; never silently restore a withdrawn image from a pinned old cache.
These procedures concern this pilot namespace only, not existing user photos or models.
No removal request or live-data deletion was performed during this work.

## Regression verification

Local backend regression: 203 passed, 29 integration/opt-in skips; targeted native,
compatibility and provider controls: 12 passed. Native v1 files without the new scale
field retain 1–5 behavior; seven-point heads retain values above five and cannot be
written against a five-point manifest. Source pins reject relabelled inputs; bootstrap
controls check determinism, grouping and non-finite rejection. Frontend 145 tests,
ESLint, route type generation, TypeScript and production build pass. Ruff formatting,
lint and strict mypy pass. GitHub CI outcomes are recorded in the PR.

[Gate verification](gate-verification.json) confirms that even a correct manifest pin
leaves this human-trained checkpoint unavailable to the product provider, and that
strict product loading refuses it. The individual research output is mode 0600. No
application enable-list, Codespaces setting, session, Owner permission, Credit entry,
user dataset, existing checkpoint or database schema was changed.
