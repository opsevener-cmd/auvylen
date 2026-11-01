# Native model and Owner preview: independent audit and hardening

2026-11-01. Branch `claude/native-preview-hardening` from PR #12 head `0756936`.

**Unchanged:** the London pilot release status (**NO-GO for service**), consumer scoring
(disabled), the native preview (disabled by default; dev/test, Owner-only), personal
models, Credits and live data. **Not done:** no new data was collected, nothing was spent,
no participant was contacted, no deployment or merge happened, and PR #11 was not
imported. The sealed 20-subject London test was **not** used for any choice here.

## 1. Prioritized audit

| # | Area | Finding | Action |
| --- | --- | --- | --- |
| P1 | Model selection | The ridge penalty is chosen from three values (.01, 1, 100) on one 20-subject validation split. With about 60 training images and 1024 standardized MobileNet features, α=.01 is close to interpolation. That makes the choice high-variance, and the winner (α=.01) is the least regularized option. | Added opt-in grouped-CV selection. A development-only study measured it (§3). The default is unchanged. |
| P1 | Evidence | 232,400 ratings come from 100 people. Every interval in the pilot report is driven by 20 test subjects, and both paired-vs-baseline intervals cross zero. | No accuracy claim. Selection diagnostics now report effective degrees of freedom and distinct training images, so overfitting is visible. |
| P2 | Preview runtime | Each prediction loaded and SHA-256-verified the checkpoint twice. | Fixed: one verified load per prediction. |
| P2 | Preview API | Every 3-second `GET job` poll ran a global `FOR UPDATE` scan of all preview jobs plus a filesystem walk. | Fixed: a poll expires only the requested job. The worker's periodic purge keeps the global sweep and orphan cleanup. |
| P2 | Preview API | Read-only `status` took a row lock on the Owner user, serializing against every mutation. | Fixed: no lock on that read path. |
| P2 | Preview UI | The run button used a nonexistent `btn-primary` class and rendered as plain text. An amber box bypassed the notice style. | Rebuilt on the design system. |
| P2 | Preview UI | One generic error covered every failure. A stale Owner sign-in (a common 403) gave no hint to sign in again. | Specific, bilingual messages for each status. The alert takes focus so it is not missed off-screen on mobile. |
| P2 | Preview UI | Reloading lost the request, so a running or completed job could not be found again before it expired. | Restored from `?job=`; the server re-checks ownership. Expired requests are dropped with a notice. |
| P2 | Preview UI | `status` returned the release gate's failures, but the UI discarded them. | Shown as plain-language reasons. Unknown codes are shown verbatim. |
| P3 | Preview | `canonical()` decodes twice: a bounded decode, then a lossless re-open. | Kept, because inference parity needs lossless pixels. The re-open is now limited to JPEG/PNG. |
| P3 | Preview | `ready()` re-hashes the checkpoint on every status call. | Kept. It is cheap at this size and it is the integrity check. |
| Blocker | Evaluation | No independent cohort exists. Consent and intended-service rights are unresolved. | Unchanged. Any accuracy claim needs a new, independent evaluation. |

## 2. Changes

- **`native_selection.py` (new).** Subject-grouped K-fold folds and an exact SVD ridge
  path: one SVD per fold evaluates a whole 15-point log-α grid. Ties go to the larger
  penalty.
- **`native.select_model(selection="grouped-cv")`, `native_train --selection grouped-cv`.**
  Opt-in. Encoder and α are chosen by repeated grouped CV over train∪validation subjects,
  then refit on that development set. The test set is evaluated once and never selects.
  The default `validation` protocol is byte-for-byte unchanged and now also reports
  `selection_protocol`, `effective_degrees_of_freedom` and `distinct_training_images`.
  `native_london_evaluate` refuses to replay a checkpoint that used a different protocol.
- **`native_dev_study.py` (new).** A development-only comparison. Sealed test subjects
  are removed by subject identifier *before* any rating is parsed. The study then runs
  nested, repeated grouped CV over the 80 development subjects. Output is aggregate only.
- **Preview runtime/API.** Single checkpoint load; targeted poll expiry; lock-free status.
- **Preview UI.** As in §1, plus a selected-photo preview, the removal deadline, and no
  prediction heading until a verified result exists. zh-CN entries cover every new string.

## 3. Development-only selection study (handcrafted encoder)

80 development subjects, one image each; the 20 sealed test subjects were excluded
before parsing. Outer: subject-grouped 5-fold × 5 repeats. Both protocols use the
original train-only augmentation and are scored on identical held-out people. Full
output: [`dev-selection-study/handcrafted-development-cv.json`](dev-selection-study/handcrafted-development-cv.json).

| Protocol | MAE | RMSE | Spearman |
| --- | --- | --- | --- |
| A: original (one split, 3 penalties) | 0.641 | 0.803 | 0.378 |
| B: grouped CV, 15-point grid | 0.624 | 0.765 | 0.326 |
| Train-mean baseline | 0.658 | 0.816 | n/a |

Paired subject-cluster bootstrap (2,000 draws; negative favours the first protocol named):

| Comparison | Mean | 95% interval |
| --- | --- | --- |
| B − A | −0.017 | −0.054 to 0.015 |
| B − mean | −0.034 | −0.102 to 0.036 |
| A − mean | −0.017 | −0.101 to 0.067 |

- **Selected penalties.** A chose α=100 in 20 of 25 folds and α=.01 in 2. B chose
  between 10 and 3,162.
- **Interpretation.** B is modestly better on error, but slightly worse on rank, and
  every interval crosses zero. That is not enough to change the default or to claim an
  improvement. It is shipped as an opt-in, tested protocol for the next genuinely
  independent cohort.
- **Fit time.** B takes about 1.9 s for all 25 outer folds, versus 0.09 s for A. Feature
  extraction dominates either way, at about 53 s.

**MobileNet was not studied.** Rebuilding the reviewed ONNX graph needs the PyTorch
toolchain, and `download.pytorch.org` is blocked by this environment's network policy.
No substitute or unverified graph was used. The study is a single CLI command
(`python -m aevyra_inference.native_dev_study --encoder mobilenetv3-small-imagenet-onnx-v1 …`)
wherever the reviewed weights are installed.

The London images and ratings were obtained privately for this study, exactly per the PR
#12 reproduction steps (pinned commits, verified hashes). They were held in gitignored
0700/0600 storage and deleted afterwards. None are committed.

## 4. Verification

| Check | Result |
| --- | --- |
| `uv run pytest` | 226 passed, 30 skipped (opt-in) |
| `uv run pytest --integration` (local PostgreSQL 16 + Redis), as CI runs it | 246 passed, 6 skipped. The skips all need reviewed MobileNet weights (`--pretrained`). Login-proxy job: 4 passed |
| `alembic upgrade head`, `alembic check` | At head (`0010`); no pending operations. No schema change on this branch |
| Ruff lint/format, strict mypy | Clean |
| `npm test` / lint / typecheck / build | 147 passed / clean / clean / built |
| Playwright `playwright.native-preview.config.ts` | 5 passed: 2 existing, 3 new (restore, expiry, stale sign-in) |
| Default Playwright full-stack suite | **Not run here.** This branch changes only the native preview page and the native-preview branch of error mapping, both covered above. CI runs the full suite |

New backend tests:
- the polled job expires while unpolled jobs wait for the worker's sweep, and a poll
  never calls the global purge;
- status does not lock;
- a prediction loads the checkpoint once;
- grouped-CV selection: ridge path = `fit_head`, grouping, tie-breaks, test-label
  invariance, sealed-row exclusion, end-to-end write/load.

## 5. Screenshots

All screenshots use UI contract fixtures; they contain no photographs and no model output.
- [Before: reloading a completed request (PR #12)](preview-ui/before-result-reload-en-desktop.webp)
- [After: restored result with release reasons, desktop](preview-ui/native-preview-result-en-desktop.webp)
- [After: Chinese, mobile](preview-ui/native-preview-result-zh-mobile.webp)
- [Stale Owner sign-in, mobile](preview-ui/native-preview-fresh-signin-en-mobile.webp)
- Disabled state: [desktop](preview-ui/native-preview-disabled-en-desktop.webp) ·
  [Chinese mobile](preview-ui/native-preview-disabled-zh-mobile.webp)

## 6. Remaining blockers and recommendations

1. An independent cohort with resolved consent and service rights is the only route to an
   accuracy claim. Pre-register `grouped-cv` versus `validation-3` before looking at it.
2. Run the development study with MobileNet where the reviewed weights exist. That is where
   the α=.01 interpolation risk applies.
3. The single-split default can pick α=.01 on 20 validation people. If the next cohort is
   also small, prefer the grouped-CV protocol, decided in advance.
4. Pose, cohort and robustness reviews (the release-gate reasons now shown in the UI) are
   still open.
