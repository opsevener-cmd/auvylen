# Independent Codex review — PR #13 into PR #12 only

2026-11-01. Reviewed original head `6c9f5965a9d8e358382f01171b537e7e1c315d59`
against exact base `0756936e13946011750e1cbd2ec45106fc264a0d`, including every changed
source/test/document, screenshot provenance and relevant authorization/queue/checkpoint code.

**Original head: NO-GO until the focused fixes below. After those fixes and green
CI: GO for merging #13 into #12 only.** Leave the PR draft pending Owner approval.
Consumer/service scoring remains **NO-GO**. Nothing here authorizes merging,
deployment, participant contact, collection, payment or live-data modification.

## Findings (line references point to the original reviewed commit)

1. **P1 — Experiment seed can admit sealed test subjects.**
   [`native_dev_study.py:126`](https://github.com/opsevener-cmd/auvylen/blob/6c9f5965a9d8e358382f01171b537e7e1c315d59/services/inference/src/aevyra_inference/native_dev_study.py#L126)
   passes the configurable experiment seed into the exclusion split at line 47.
   A generated 100-person sentinel reproduction with seed 77 admitted **13 of the
   original seed-42 sealed 20** into development. This demonstrates a code path,
   **not evidence that Claude's default-seed reported experiment leaked**.
   Exclusion also moved if the input subject universe changed. Fixed: immutable
   holdout seed 42, pinned original adult-subject-registry digest, independent CV
   seed, recorded seeds/development digest, and tests rejecting subsets/replacements
   and changed holdout seeds before numeric target ingestion.

2. **P2 — Expiry during polling strands the form; restore can race a new request.**
   [`native-preview.tsx:87`](https://github.com/opsevener-cmd/auvylen/blob/6c9f5965a9d8e358382f01171b537e7e1c315d59/apps/web/src/components/native-preview.tsx#L87).
   Polling's 404 only set an error; the old pending job kept inputs locked. A slow
   restored-job GET could arrive after a new submit and overwrite its UI state.
   Fixed: shared clearing for expired/deleted requests and initial-request locking
   until status/restoration settle. Tests exercise an actual delayed restore and
   expiry on the second GET, not merely initial missing-job responses.

3. **P2 — A new portrait can retain the old portrait's score and URL.**
   [`native-preview.tsx:94`](https://github.com/opsevener-cmd/auvylen/blob/6c9f5965a9d8e358382f01171b537e7e1c315d59/apps/web/src/components/native-preview.tsx#L94)
   no longer cleared the previous job when selecting a new file. The old number
   could appear beside the new selected portrait until upload completed. Fixed:
   selecting a new file clears that result and its restoration URL. Also gate score
   rendering on COMPLETED and display the result's own manifest pin: restoring an
   old result must not attribute it to a newly configured active checkpoint.
   Browser tests cover all these boundaries without real photographs/predictions.

4. **P2 — Selection inputs can silently drop rows or mislabel a training protocol.**
   [`native_selection.py:91`](https://github.com/opsevener-cmd/auvylen/blob/6c9f5965a9d8e358382f01171b537e7e1c315d59/services/inference/src/aevyra_inference/native_selection.py#L91)
   indexes features with the supplied subject list without verifying equal lengths;
   a shorter subject list silently excludes data. In Python calls,
   [`native_train.py:67`](https://github.com/opsevener-cmd/auvylen/blob/6c9f5965a9d8e358382f01171b537e7e1c315d59/services/inference/src/aevyra_inference/native_train.py#L67)
   coerced unknown selection strings to validation while reporting a grouped policy.
   CLI choices already prevented that particular typo. Fixed: explicit aligned,
   finite, nonblank input/grid/scale checks, and rejection of unknown protocols
   before data access. No optimization rule or fitted head was changed.

5. **P2 — Uncertainty and effective-DF interpretation need qualification.**
   [`native_dev_study.py:93`](https://github.com/opsevener-cmd/auvylen/blob/6c9f5965a9d8e358382f01171b537e7e1c315d59/services/inference/src/aevyra_inference/native_dev_study.py#L93)
   resamples already fitted OOF errors. Overlapping outer training sets make those
   errors dependent; the quantiles omit refitting, split/selection and rater
   variability. They cannot establish frequentist 95% coverage or a probability
   of superiority. Protocol A also refits all outer-training subjects, unlike the
   frozen original pilot head; it compares selectors, not original deployed heads.
   Clarified documentation/aggregate metadata without altering reported values.
   [`native.py:68`](https://github.com/opsevener-cmd/auvylen/blob/6c9f5965a9d8e358382f01171b537e7e1c315d59/services/inference/src/aevyra_inference/native.py#L68)
   omitted the unpenalized intercept from total linear-design DF. Added its one DF
   and a hat-matrix reference test; report augmented design-row counts explicitly.
   This is **unclipped design DF**, not independent-person DF when labels are tiled
   across augmentations. Neither this diagnostic nor its correction changes weights.

## Verified concerns that are not bugs / remaining statistical limits

- Exact SVD ridge weights match the existing primal/dual sum-SSE ridge objective.
  Fold standardization fits only training rows; each person's augmented views stay
  in training folds and held-out predictions use clean features. No automatic
  normalization by sample count was introduced. Tie-breaking rounds CV MAE to
  12 decimal places and prefers larger alpha; documentation now says that precisely.
- The once-only preview load returns head and manifest from the same verified load,
  preserving native-scale, human-data and pinned rights checks. API/worker readiness
  checks deliberately still revalidate capability/integrity before publication.
- Targeted poll expiry holds the existing Owner/job locks in the queue's order;
  deletion/expiry fences leases and removes artifacts. Global/orphan cleanup still
  runs in the worker. Lock-free status still checks Owner role. No CSRF, Origin,
  private-image, Credits, schema, deployment-mode or consumer gate was weakened.
- The new replay guard refuses grouped-CV checkpoints **before** loading London
  labels; a regression test verifies this. Original saved heads/scale/version remain
  compatible. Added diagnostics/provenance can change newly written manifest bytes;
  claims of byte identity refer to head weights/predictions, not whole new manifests.
- CSV filtering encounters raw source fields but never parses/uses excluded numeric
  targets. Sentinel tests make those targets unparseable. No held-out labels or
  old test outcomes were used for tuning or any review fix.
- CV selection currently averages image MAE within folds and then averages folds.
  Repeated portraits with unequal counts can therefore receive unequal influence;
  the current study has one portrait per subject. Pre-register the target weighting
  before using the method on an unbalanced future cohort. The grouped-CV selection
  minimum is optimistic as a performance estimate; use nested outer CV/independent
  evaluation. Neither grouped CV nor these fixes proves generalization.
- Screenshot numbers are explicitly UI contract fixtures, not genuine model outputs.
  No original private portrait or individual real prediction is present in the diff.

## Independent verification

- Reproduced the **80-development-subject handcrafted study**, with the sealed 20
  excluded before target parsing. All reported MAE/RMSE/rank and paired resampling
  summaries match exactly (maximum absolute difference **0.0**). No new checkpoint
  was saved, no existing model was modified, and no sealed test experiment was run.
- Real reviewed MobileNet + native checkpoint verified through isolated authenticated
  upload, CPU subprocess, result validation and deletion: **13 preview tests passed**.
  This uses an existing authorized development portrait; it is integration evidence,
  not an independent accuracy result. Hosted CI's pretrained skips cannot replace it.
- Frontend **147 tests**, lint/type-check/production build passed. Native-preview
  production Chromium suite **10 passed**, including delayed restoration, mid-poll
  expiry, photo/result separation, result pin attribution, bilingual flow and
  rejecting scores on QUEUED/FAILED bodies. Browser responses are contract fixtures.
- Python Ruff/format/mypy passed; backend regression and all five final GitHub jobs
  are recorded in the PR checks. Reproduction data and weights remain private.

Consumer decision remains **NO-GO**: no independently consented external cohort,
insufficient intended-service rights, no independent pose/demographic validation,
and inconclusive baseline improvement. A GO to combine these two research branches
is not authorization to enable the preview, public scoring, merge or deploy.
