# Native scoring milestone, model research and public-release roadmap

2026-11-07. Branch `claude/native-scoring-milestone`, from the development branch
`codex/phase4b-custom-preferences` (`3df2ff1`). Consumer scoring stays **disabled**. Nothing
was merged, deployed, spent or collected. No participant was contacted. No sealed London test
subject was used to choose anything.

## 1. What works now

The Owner native preview now works **end to end through the real website**, with real
inference: Owner sign-in → upload → durable queue → worker subprocess (reviewed MobileNet +
native ridge head) → verified result → history → deletion. It ran against a disposable
PostgreSQL database, the real Next.js production build, the API and the worker, all local.

Before this branch it could not work through the website. The browser tests replaced API
responses inside the page, and the API tests called the backend directly, so neither ever
went through the Next.js proxy where both defects sat:

| Defect (development branch) | Effect | Fix |
| --- | --- | --- |
| Proxy allow-list had no `research/native-preview` route | Every preview request from the browser returned 404 | Same rule Codex added on the Phase 7A branch, now with a policy test |
| Proxy capped request bodies at 1 MiB outside personal research | Preview and aesthetic uploads over 1 MiB (most phone photos) failed with 413 | Limit moved into the tested policy module (`requestBodyLimit`) |
| The head scores any input | First real run scored a **generated non-face pattern 4.51** | Pinned input check; scores withheld for inputs unlike the training portraits |

Also added:
- **History and version tracking.** `GET /jobs` lists the Owner's retained previews, newest
  first. Each shows the checkpoint that produced it, marked current or earlier model.
- **Interpretation.** The result explains the relative 1–7 scale and the checkpoint's own
  recorded held-out error ("On 20 people the model never saw, predictions differed from the
  raters' average by 0.51 points; always guessing the training average differed by 0.57").
  This is aggregate context, not an interval for one portrait.
- **Faster results.** Results are polled every second instead of every three, and the stale
  "waiting" message is cleared.

Real-run measurements (one local machine, CPU, through browser and proxy):

| Input | Size | Upload → verified result | Input check |
| --- | ---: | ---: | --- |
| London training-partition portrait | 0.44 MB | 2.5 s | typical, scored |
| Same portrait rotated 90° | 1.1 MB | 1.6 s | unusual, scored with a caution |
| Generated pattern | 5 KB | 2.2 s | outside, **no number** |

Model inference itself is about 130 ms (subprocess `duration_ms`); polling and the queue
account for the rest. These are single observations, not a latency distribution.

Screenshots (generated patterns only, no person or real prediction):
- [Before the input check: a pattern scored 4.51](before-input-check-pattern-scored-en-desktop.webp)
- [After: no score, desktop](input-check-no-score-en-desktop.webp)
- [After: no score, Chinese mobile](input-check-no-score-zh-mobile.webp)

### Input check

`native_input.py`. Distance = RMS of the image's features standardized by the head's own
training statistics. Thresholds come from the clean training portraits only and are stored in
the manifest report, so the checkpoint pin covers them. Above 1.1 × the training maximum the
input is *unusual* (scored, with a caution). Above max(3 × training median, 1.25 × caution
threshold) it is *outside* (no number; the contract enforces this). Older checkpoints without a
profile report *unchecked*. Retraining with the profile produced **byte-identical weights**.

Development calibration (MobileNet; training and validation portraits; no test subjects):

| Inputs | Distance |
| --- | --- |
| Training portraits (60) / validation portraits (20) | 0.72–1.69 / 0.71–1.49 |
| Mirrored / grayscale portraits | 0.82–1.04 / 1.30–1.64 (typical) |
| Portraits rotated 90° | 1.89–2.39 (unusual) |
| Background crops, tiny face in frame, noise, flat colour, patterns | ≥ 3.41 (outside) |

This is a coarse guard, not a face, age or identity detector. It does not show that a
typical-looking input is predicted well.

### Reproducing the working preview (private environment only)

1. Acquire the London sources by the pinned procedure in
   [london-pilot/README.md](../london-pilot/README.md), run `native_london`, then
   `native_train` with `--images ROOT/images`.
2. **Reviewed encoder.** `download.pytorch.org` was blocked here, and PyPI publishes only the
   CUDA-bundled build of the same PyTorch version, while the export script pins the `+cpu`
   builds. An uncommitted copy without that version guard was run. The script's own final
   check passed: the graph is **byte-identical** to the reviewed export
   (`164c4816…eedd2a6`), and `install-pretrained-extractor.py` verified it again. The source
   checkpoint matched its pinned SHA-256 (`266a294c…`). No unverified graph was used.
   Operators should still prefer the reviewed `+cpu` toolchain where reachable.
3. Configure the preview (`APP_ENV=development`, `RESEARCH_MODE=true`,
   `NATIVE_PREVIEW_*`) as in [independent-cohort/README.md](../independent-cohort/README.md),
   start the API, worker and web, and sign in freshly as the Owner.

With the weights installed, **all six reviewed-weight tests that CI skips passed here**,
including the real preview inference API test.

## 2. Model research (development data only)

Method: paired, repeated (×5), subject-grouped 5-fold CV over the **80 development
subjects**. Codex's immutable exclusion removes the 20 sealed seed-42 test subjects before
any rating is parsed. Intervals are descriptive resampling of fixed out-of-fold errors, not
coverage guarantees. Aggregate outputs are in [model-research/](../model-research/); code is
in `native_experiments.py` and `scripts/research/encoder-candidates/`.

**1. MobileNet is genuinely better than guessing; the handcrafted encoder is not.**
MobileNet + ridge (current pilot rule): MAE 0.553, RMSE 0.684, Spearman 0.58, against a
train-mean MAE of 0.658. The paired difference is −0.105 (−0.19 to −0.02). The handcrafted
encoder's interval crosses zero, and it is 0.09 worse than MobileNet. Its lower error on the
20-person London test was noise; the validation-based choice of MobileNet was right.

**2. Head and selection tweaks do not help:**

| Variant | Change vs MobileNet, original rule |
| --- | --- |
| Grouped-CV α selection (my earlier opt-in) | −0.004 MAE (−0.035 to +0.025); worse rank |
| Mirror augmentation + mirror averaging | +0.000 |
| Handcrafted + MobileNet fusion | −0.020 (−0.046 to +0.005) |

**3. Larger lawful encoders do not help at n=80.** Apache-2.0 timm ImageNet checkpoints
from GitHub releases were checked against the hash prefixes in their filenames. The same
PyTorch pipeline reproduced the production ONNX MobileNet result exactly:

| Encoder (best selector) | Parameters | MAE change |
| --- | ---: | --- |
| ConvNeXt-Nano | 15.0 M | −0.041 (−0.103 to +0.019) |
| MobileNetV3-Large | 4.2 M | −0.022 (−0.084 to +0.039) |
| EfficientNet-B0 | 4.0 M | −0.015 |
| EfficientNet-B3 | 10.7 M | −0.009 |

**4. Data is the bottleneck.** Training on subsets of each fold:

| Training subjects | 16 | 24 | 32 | 48 | 64 |
| --- | ---: | ---: | ---: | ---: | ---: |
| MAE | 0.644 | 0.628 | 0.594 | 0.576 | 0.553 |
| Spearman | 0.35 | 0.39 | 0.45 | 0.48 | 0.55 |

That is roughly −0.045 MAE per doubling, with no plateau. Extrapolating to 400 people would
be speculation; the curve only says more people still help.

**5. Labels need many raters.** On the real development faces, single-rater ICC is
**0.25**:

| Raters per photo | 3 | 5 | 8 | 12 | 20 | 30 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Correlation with 2,324-rater consensus | 0.71 | 0.80 | 0.86 | 0.90 | 0.93 | 0.95 |
| Label error vs consensus | 0.64 | 0.49 | 0.39 | 0.31 | 0.24 | 0.20 |

Phase 7A's export minimum of 3 raters yields labels noisier than the model's own error.

**Decision.** No candidate is promoted; the default training protocol is unchanged. Further
architecture work is low value until there are more people. The next model gain comes from
more consented people with enough raters each. Re-run these comparisons, preregistered, once
a cohort of about 400 exists. That is where ConvNeXt-Nano, fusion and stronger encoders could
plausibly separate.

## 3. Shortest credible path to a public scoring MVP

Datasets reviewed in the repository (London CC BY, SCUT-FBP5500, MEBeauty, Chicago Face
Database) permit research at most. **None grants rights for a consumer scoring service.**
The public model must therefore be trained on first-party consented data, or on data licensed
from its owners for that purpose. The data, not the model, is the critical path.

| Stage | Exit criterion | Status |
| --- | --- | --- |
| 0. Research preview | Real Owner preview with input check and version tracking | **Done here** (London, research only) |
| 1. Authorization | Owner approves budget, recruitment, consent text, processors; repo visibility made private | Owner decision |
| 2. Development cohort | ≥ 400 consented adults, 1–4 captures each, **≥ 12 independent raters per photo** | Phase 7A pipeline exists; collection NO-GO until stage 1 |
| 3. Model candidate | Preregistered dev-only comparison (current head, ConvNeXt-Nano, fusion); retrain with input profile | Tools ready (`native_experiments`) |
| 4. External holdout | ≥ 200 independently custodied people, **≥ 30 raters per photo**, sealed before fitting | Phase 7A custody design exists |
| 5. Single evaluation | Preregistered once-only evaluation against release gates | — |
| 6. Limited public beta | Self-portrait only, adults, deletion after scoring, conservative presentation | Requires all gates below |

### Release gates (all required; set before seeing holdout data)

**Scientific**
- S1. External holdout of ≥ 200 independent people, sealed by the custodian before any
  fitting and evaluated once.
- S2. Paired MAE improvement over the train-mean baseline with an interval excluding zero,
  plus a preregistered absolute target (proposal: MAE ≤ 0.50, Spearman ≥ 0.50 on the native
  scale).
- S3. Subgroup review on self-reported, consented attributes. Minimum ≥ 30 people per
  reported group; no group's MAE worse than the overall MAE by more than a preregistered
  margin. Never infer protected traits.
- S4. Robustness on real repeat captures (pose, lighting, device), not synthetic
  perturbations: within-person drift ≤ 0.3 native points.
- S5. Displayed uncertainty calibrated on the holdout (for example conformal intervals with
  verified coverage). The input check validated on real out-of-scope uploads.

**Licensing and rights**
- L1. Training images, labels and derived weights covered by consent for the intended
  service, including any commercial use; London-trained weights never serve the public.
- L2. Encoder licences reviewed for service use: Apache-2.0 code and weights, plus counsel's
  view on ImageNet-1k training-data terms.
- L3. Attribution and notices shipped; no third-party model or labels used as supervision.

**Privacy and safety**
- P1. Adults only, by attestation and policy; age is never inferred from a face. MVP scores
  only the uploader's own portrait.
- P2. Image deleted immediately after scoring; results short-lived and user-deletable; no
  public sharing, ranking or leaderboard.
- P3. Legal and data-protection review (DPIA) of facial analysis for the target
  jurisdictions; processors and locations disclosed.
- P4. Wording and design reviewed for body-image harm: relative subjective scale, no "beauty"
  claims, visible uncertainty, opt-out.
- P5. Repository made private before real data. GitHub currently reports it as **public**.

**Operational**
- O1. Linux host deployment, supervised worker, monitoring, verified encrypted backups and
  restore drills.
- O2. Checkpoint pin, rollback and lineage from consented export to model, including a
  retraining policy on withdrawal.
- O3. Latency target measured from real clients (local single runs: 1.6–2.5 s).
- O4. Removal requests, incident response and abuse rate limits operating.

## 4. Retained, redesigned, rejected

**Retained:**
- Codex's checkpoint and rights gating, release-failure gate, sealed-holdout exclusion and
  preview security model.
- The validation-selected MobileNet ridge head: the development evidence supports it.

**Redesigned:**
- Proxy routing and upload limits (now tested).
- Preview result presentation, history and version tracking.
- An input check is now part of every newly trained checkpoint.

**Rejected on evidence, kept as opt-in research only:**
- My own grouped-CV selector.
- Mirror augmentation.
- Encoder fusion.
- Larger encoders at the current data size.

**For Codex to challenge:**
- The input-check thresholds were set on development portraits and generated inputs.
- The 12/30 rater recommendations rest on one rater population.
- The proposed S2 targets.

## 5. Verification

See the PR description for the full suite results.
