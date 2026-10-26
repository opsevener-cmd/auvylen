# Auvylen aesthetic scoring model — Phase 6

Status (2026-10-26): **code complete, user-facing scoring disabled.** No authorized
human-rated dataset is available, so no genuine checkpoint exists. With the default
configuration, `/research/aesthetic` reports *unavailable*, submissions return 503, and no
score is ever simulated. Tests use a checkpoint trained on **generated** data. The API accepts
it only in development/test, and every result from it is labelled synthetic.

The score estimates how the training annotators would rate a photograph. It reflects
their statistical preferences, not objective beauty. This model is separate from personal
preference models (Studio) and from the synthetic `/analyze` mock, which is unchanged.

## Pipeline

```text
Photograph ─► private upload (consent + suitability) ─► durable research job (PostgreSQL)
   ─► worker: frozen extractor x ∈ R^d ─► z = xW + b ─► p = softmax(z) (5 bins)
   ─► S5 = Σ k·p_k ─► S10 = 1 + 9/4 (S5 − 1) ─► fenced result ─► image deleted ─► result page
```

| Component | Location |
| --- | --- |
| Mathematics, training, metrics, calibration | `services/inference/src/aevyra_inference/aesthetic.py` |
| Checkpoints, integrity, release gate, engine | `services/inference/src/aevyra_inference/aesthetic_checkpoint.py` |
| Operator training command | `services/inference/src/aevyra_inference/aesthetic_train.py` |
| Requests, retention, worker execution | `services/api/src/aevyra_api/aesthetic/` |
| HTTP API | `services/api/src/aevyra_api/routes/aesthetic.py` (`/api/v1/research/aesthetic`) |
| Migration | `services/api/migrations/versions/0009_aesthetic_analyses.py` |
| Wire contracts | `packages/contracts/src/aevyra_contracts/aesthetic.py`, `packages/contracts/src/index.ts` |
| Bilingual page | `apps/web/src/components/aesthetic-analysis.tsx` (`/research/aesthetic`) |

## Mathematics

The loss is the squared distance between cumulative distributions:
`L = (1/5) Σ_k (Σ_{i≤k} (p_i − q_i))²`, averaged over images. Training minimises
`L + (λ/2)‖W‖²` with Adam (β = 0.9/0.999). `objective()` returns exact gradients:
`dL/dp_i` is a reversed cumulative sum of the CDF differences, propagated through the
softmax Jacobian. Tests check these gradients against central finite differences for both
the logits and `(W, b)`, including weight decay.

`q` must be a real vote distribution. `normalize_votes` rejects negative, non-finite or
empty rows. The training command accepts only integer counts in `votes_1..votes_5` and
refuses mean-score-only label files. It never constructs a distribution from a mean.

## Training protocol

- Subjects are hashed with the seed and sorted. 20% of subjects form the **test** set,
  the next 20% the **validation** set, and the rest **training**. All images of one person
  stay in one split. At least 15 subjects and 60 labelled images are required, and
  training ratings must vary.
- Feature means and scales come **only from training subjects**. A test perturbs every
  test row and confirms the fitted head is bit-for-bit identical.
- Early stopping uses validation loss. Calibration uses validation subjects. The test set
  is evaluated once, after model selection and calibration are fixed.
- Identical image bytes under two label rows are refused, because they would leak across
  splits.

### Reported metrics (held-out test subjects)

CDF distribution loss; MAE, RMSE, **Spearman** and Pearson correlation of the expected
rating; display-scale MAE. Two simple baselines: the training-mean rating (MAE/RMSE) and
the training-mean distribution (loss). Also reported: how closely the predicted annotator
spread matches the observed spread, subject and image counts, and the exact split indices.

### Spread versus uncertainty

These are reported separately and must not be confused:

- **Rating spread** (`rating_spread_10`): the standard deviation of the predicted
  distribution. It shows how much *annotators* are predicted to disagree about the photo.
- **Calibrated range** (`interval_low/high`): a split-conformal 90% radius on display-scale
  absolute error, computed from validation subjects with the `(n + 1)` correction. It
  estimates the *model's own* error. Test-set coverage of this range is reported. The
  validation set also chose the early-stopping epoch, so coverage is approximate; the
  release gate therefore requires test coverage within 10 points of the target.

## Checkpoints and integrity

`<PRIVATE_MODEL_ROOT>/aesthetic/<version>/` holds `manifest.json` and `head.f64`, which is
raw little-endian float64 (mean, scale, W, b). Loading never parses pickle or zip files.

- Directories and files are created exclusively and made read-only. An existing version
  can never be overwritten; a new version needs a new name.
- The operator pins `AESTHETIC_MANIFEST_SHA256`. The manifest pins the weight SHA-256,
  byte size, dimension and the **exact** extractor manifest (`extractors.manifest(id)`).
  Any change to the extractor's version, preprocessing or weights invalidates the checkpoint.
- Files are size-bounded, symlinks rejected, values checked finite and scales positive.
- The worker re-verifies everything at execution time. It refuses a job submitted under a
  different manifest than the one now pinned (409; resubmit).

### Release gate (minimum engineering checks; not scientific approval)

`release_failures()` must return nothing: a non-synthetic dataset; at least 10 test
subjects and 30 test images; better than both baselines on MAE and distribution loss;
Spearman ≥ 0.3; a calibrated range whose test coverage is within 10 points of 90%. Status
reasons are a fixed vocabulary: `disabled`, `checkpoint_not_configured`,
`checkpoint_missing`, `checkpoint_integrity_failure`, `validation_gate_failed`,
`extractor_unavailable`, `ready`.

Engine metadata is always `commercial_allowed=false`, `research_allowed=true`. Execution uses
`EngineRegistry` with `purpose="research"`. Commercial use would need separate licence evidence
for the dataset, the extractor weights and the photographs. A flag is not that evidence.

## Privacy, authorization and safety

- Requires `RESEARCH_MODE` plus the existing research entitlement (`entitlements.py`).
  Research jobs never touch Credits. All mutations require a session, exact Origin and CSRF.
- Authorization and model availability are checked **before** the upload body is read.
  Binary JPEG/PNG only, at most 4 MiB, decoded with the existing bounded sanitiser (EXIF and
  metadata removed). The upload slots are shared with Studio uploads.
- Attestations are required and recorded (`adult-single-subject-authorized-v1`): exactly
  one adult subject, permission/rights, and understanding of what the score means.
  **Adulthood is never inferred from appearance, and no automated face detection exists
  yet.** Technical suitability checks reject images under 224 px on the short side, aspect
  ratios above 3:1, and blank images.
- The private image lives under `PRIVATE_UPLOAD_ROOT/aesthetic`, which is never served.
  It is deleted as soon as its job is final; a lost lease leaves it for the retry. The
  worker purge also removes images older than 24 hours, deleted or expired analyses
  (results kept 90 days, and the result is cleared from the job), and orphaned files.
- Analyses are owner-scoped (other users get 404). Owners can delete them even after
  research access is revoked. Revoked access fails queued jobs.
- Logs record event names and error classes only.

## Operator procedure (remote Linux environment only)

1. Obtain a dataset of adult subjects with **per-image human vote counts** on a 5-point
   scale and subject identifiers. Review its terms, the photograph rights and research
   permission, following `docs/evaluation/adult-face-workflow.md`. Public availability is
   not permission. Do not download restricted datasets or bypass registration. Nothing
   here approves any specific dataset.
2. Write a private plan JSON matching `DatasetEvidence`: `name`, `license`, `terms_url`,
   `authorization_reference`, `reviewer`, `annotator_population`,
   `adult_subjects_confirmed: true`, `rating_scale`, `commercial_use_permitted`,
   `synthetic: false`.
3. Install the reviewed MobileNet weights (`docs/pretrained-representation.md`), then:

   ```bash
   uv run python -m aevyra_inference.aesthetic_train \
     --labels PRIVATE/labels.csv --images PRIVATE/images --plan PRIVATE/plan.json \
     --model-version aesthetic-v1 --model-root /var/lib/auvylen/models
   ```

   The command prints `manifest_sha256`, test metrics and the release-gate result. It never
   prints paths, subject identifiers or votes.
4. Review the metrics and limitations with the user. Only if the gate passed and the user
   approves, back up the database and model volume, then set `AESTHETIC_SCORING_ENABLED=true`,
   `AESTHETIC_MODEL_VERSION` and `AESTHETIC_MANIFEST_SHA256`. The settings refuse to enable
   scoring without both pins. `AESTHETIC_ALLOW_SYNTHETIC_TEST_CHECKPOINT` is rejected in
   staging and production.
5. To roll back, unset `AESTHETIC_SCORING_ENABLED`. Checkpoints are immutable; never edit
   one in place.

## Known limitations

- Without a reviewed detector there is no automated single-face check; the user's
  attestation is the basis for both "adult" and "single subject". This is shown with every
  result.
- A linear head over frozen ImageNet features is a deliberately simple, auditable first
  version. Its accuracy is unknown until it is evaluated on an authorized dataset. Scores
  inherit the biases of the annotators, the dataset demographics and photographic conditions.
- The conformal range is marginal (average over test people), not a per-image guarantee.
