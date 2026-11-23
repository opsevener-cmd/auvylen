# Phase 7A peer review and focused integration fixes

2026-11-07. Review of Claude PR #16 (`9513a055`), on Codex PR #14 (`003d8a79`).
This review retains Claude's least-covered assignment and additive rater model as useful
co-design contributions. The changes below address reproduced failures, not styling.
No live data, participant collection, scoring activation or capacity increase occurred.

## Severity-ranked findings

| Severity | Finding and evidence | Resolution |
| --- | --- | --- |
| P1 | The weighted centering in ALS did not minimize its declared penalized least-squares objective for unequal rater counts. A fixed generated connected design disagreed with a direct augmented-design ridge solve by up to **0.215558** native points. | Residualize image intercepts and solve the rater contrast system. An independent dense-design reference now agrees within 1e-9. The moment correction uses the actual overlap matrix rather than `mean(noise/n_r)`. |
| P1 | A tiny ridge silently identified disconnected image/rater components, reporting an adjusted model even though between-component shifts are not identified by the observations. Residual degrees of freedom assumed connectivity. | Count graph components and residual rank. Return raw means with explicit fallback status for disconnected/saturated/ill-conditioned designs; cap the dense contrast calculation at 256 raters/3000 images. |
| P1 | `adjusted.csv` fitted offsets from **all** development labels, then matched the ordinary trainer's input schema. Choosing it for ordinary CV/test splitting couples labels across folds. A prose warning alone did not prevent accidental leakage. | Adjustment is an explicit export opt-in. `means.csv` remains raw/default. Candidate CSV has a `label_policy` column that the ordinary native loader rejects. Exported diagnostics bind raw annotations by SHA-256, record method/version, offsets, fallback status, components and residual degrees of freedom. Fold-local fitting is required before evaluation. |
| P1 | Embedding every source portrait in a 64 MiB in-memory ZIP imposed a lower effective limit than the image cap and created unnecessary browser copies. | New v2 snapshots contain metadata/labels and a hash-pinned private image inventory. The existing private operator CLI verifies live status/revision/expiry and copies images one at a time under the snapshot lock. Source corruption removes the partially created dataset. Legacy v1 snapshots remain readable; withdrawal revokes both formats. No cap was raised. |
| P2 | Mean half-panel size is not a valid Spearman-Brown inversion for heterogeneous panel sizes. Negative draw correlations were replaced by zero, and zero draws crashed. Image-only resampling omitted shared-rater and subject uncertainty. | Report observed split-half summaries. Suppress projections for unequal coverage, disconnected designs and uncertain/nonpositive agreement. Keep negative observations. Validate draw bounds; label intervals as descriptive conditional image resampling, not population confidence or individual-label intervals. |
| P2 | Rejected source files remained until retention, counting against capacity and permitting prolonged unnecessary storage. | Rejecting revokes access and clears ratings/source references immediately, with durable physical erasure retry. Removed sources cannot be re-approved. Pending erasures still consume the disk budget until drained. |
| P1 | Publishing a new consent version left old active assignments alive. After re-consent, a new rating could still be attributed to the old lease/consent. Client confirmations also survived a version refresh. | New consent publication cancels pending assignments; version changes reset the client confirmations and rating component. A regression verifies the replacement lease captures the new consent. |
| P2 | The assignment improvement had only a small sequential example, not >1000-image or independent-user concurrency evidence. | A 1001-logical-image fixture proves the least-covered final image is reachable. PostgreSQL tests cover independent concurrent users and duplicate requests, counting live reservations. Eligibility constraints can prevent perfectly global balance; the comment now says so. |

## Interpretation and retained limits

The corrected rater model estimates an additive image intercept plus a zero-mean
(unweighted over observed raters) rater effect with an empirical shrinkage penalty.
For incidence matrix C and image counts n_i, its contrast matrix is
`H = diag(n_r) - C.T diag(1/n_i) C`. Under the model, the noise contribution to the
unpenalized rater variance is `noise * trace(H+) / (R-1)`. This accounts for observed
overlap; it does **not** solve rater-by-image interactions, informative skipping,
selection bias, ordinal/clipping effects or arbitrary non-ignorable missingness.

A connected graph and positive residual degrees of freedom are necessary safeguards,
not proof that adjustment helps real raters. The simulations have known generated
truth; they are not evidence of human aesthetic accuracy. Shrinkage/adjusted-label
uncertainty is not estimated by the split-half diagnostic. Shared raters and multiple
portraits of one subject require crossed/clustered uncertainty analysis before any
confirmatory reliability claim. No method is promoted into model training here.

Three ratings remain only a technical export floor. The proposed 12/30 rater budgets
from London are population-specific planning hypotheses, not universal guarantees.
The default 30-primary-slot limit, 200-photo global budget, 4 MiB inbound cap, 64 MiB
snapshot cap, account protections, holdout custody and retention gates are unchanged.
A planned 2400-image cohort still needs explicit disk/backup/review-capacity approval
and attention to the native trainer's existing 256 MiB/3000-image limits. This review
does not silently authorize that collection or remove those constraints.

## Export handoff and privacy

New browser snapshots intentionally omit image bytes; use the established private CLI:

```sh
uv run python -m aevyra_api.studies.exports \
  --export-id <private-export-uuid> --output private-data/new-private-run
```

It rechecks live revocation, verifies the metadata archive and each portrait hash,
creates 0700 directories/0600 files, and fails if any source is missing, expired,
withdrawn, changed or no longer approved. Old v1 bundles are supported for compatibility.
Already downloaded data cannot be recalled; this is not machine unlearning. Keep a copy
register and recheck export status before every use. No holdout export path is added.

Current consent/export rights remain **non-commercial research only**. An opt-in or
first-party source is not a grant for a future consumer service. Repository visibility
remains public, so no private photos, ratings, study evidence or model artifacts belong
in source control or CI artifacts. Real collection remains disabled.

## Verification and coordination

The code is tested with generated images/ratings, isolated SQLite and fresh randomized
PostgreSQL schemas. Tests cover the numerical objective, sparse/disconnected designs,
heterogeneous coverage, source integrity, revoked snapshots, default raw labels,
explicit candidate opt-in, ignored candidate inputs in the ordinary trainer, rejection,
large logical assignment coverage and concurrent independent reservations. The
1001-image fixture inserts **logical test rows only**; it does not raise the production
image limit or ingest portraits.

PR #15 is reviewed independently and preserves its own branch/history. The safe
approval sequence remains #15 → development, #16 → #14, then update #14 against that
reviewed development state and apply the tested proxy resolution. The prospective
integration branch is a verification artifact, not authorization to merge any PR.
All actual merges, deployment, model activation and real participant collection require
Owner approval.


Generated performance probe (one CPU thread, 300 logical images, 60 raters, 1800 votes;
median of three runs with Python tracemalloc enabled): rater fit **0.0075 s** with
0.55 MB peak traced allocations; conditional diagnostics **4.16 s** with 1.15 MB.
These are generated-array/profiling measurements, not portrait-inference latency or
process peak RSS. The diagnostics cost reinforces why analysis is opt-in; ordinary
raw exports do not run it. New browser snapshot creation is regression-tested to
perform **zero portrait-byte reads**, rather than buffering the complete image corpus.
