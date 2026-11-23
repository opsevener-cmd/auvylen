# Independent scoring milestone and Phase 7A integration review

2026-11-07. This is a code-review/integration artifact, not a model release, deployment,
collection authorization or independent replication of the private human-data experiment.
Claude's work is retained as co-designed implementation: the native preview, feature-
distance idea, model comparison tools, balanced assignments and optional rater model.
The changes address demonstrated failures and qualify claims where evidence is limited.

## Reviewed refs and proposed coordination

| PR | Original head | Reviewed head | Code-merge recommendation |
| --- | --- | --- | --- |
| [#15](https://github.com/opsevener-cmd/auvylen/pull/15) | `32dd2baf` | `c4be6ea337943547c6c582f09e040cb4d4a23dfd` | GO with all scoring/research activation gates unchanged; this is not consumer/model validation. |
| [#16](https://github.com/opsevener-cmd/auvylen/pull/16) | `9513a055` | `9eb6f87010275c7e01ae0f88820fae236ddf4f18` | GO into #14, with raw means default and the documented v2 export handoff. |
| [#14](https://github.com/opsevener-cmd/auvylen/pull/14) | `003d8a79` | unchanged pending approval | NO-GO as-is; GO only after absorbing #16 and applying/retesting the prospective integration with #15. |

Development base remains `3df2ff1ecdd2ccf59650f53e431f1c2d85cd4d7c`. All three PRs remain
open/draft. Neither source PR has been merged into its target. The separate
`codex/scoring-phase7a-integration` branch combines the reviewed histories solely to
verify their prospective tree; it does not replace or automatically merge the three PRs.

Approval sequence:

1. Review/approve #15 → `codex/phase4b-custom-preferences`.
2. Review/approve #16 → `codex/phase7a-consented-studies` (#14).
3. Update #14 against the resulting development branch. Preserve both sets of proxy
   routes and the exact image-submit body-limit helper; preserve study download headers.
   Also keep the integration-only fixture/browser test commit from the verification branch.
4. Rerun the five checks and real-path browser cases on that exact updated head before
   considering #14 → development. New source changes invalidate the previously tested tree.

No merge, deployment, model activation, repository-visibility change, recruitment,
spending, new portrait ingestion or live-data mutation was performed.

## Severity-ranked material findings and fixes

| Severity | Finding | Focused resolution/evidence |
| --- | --- | --- |
| P1 | Legacy/unknown input profiles could produce a **new** unchecked score; a claimed `typical` verdict could disagree with distance. | New unchecked inference withholds its number, malformed known profiles fail closed, and both Python/Zod contracts check threshold order and verdict consistency. Historical scores remain readable with a warning. No thresholds or weights were retuned. |
| P1 | The rater ALS did not solve its declared ridge objective under unequal rater counts. | A fixed generated connected design differed from a direct ridge reference by up to **0.215558 points**. The residualized rater solve and overlap-aware moment correction now agree with an independent dense-design reference within 1e-9. |
| P1 | Disconnected/saturated rating designs were silently given offsets; moment degrees of freedom and correction ignored graph structure. | Explicit graph/rank diagnostics and raw-mean fallbacks. Bounded 256-rater contrast solve; no arbitrary confounding is presented as identified. |
| P1 | Full-development rater offsets fed a drop-in `adjusted.csv`, coupling labels across a later train/test split. | Adjustment is explicit opt-in. Raw `means.csv` remains default; candidate schema marks full-development fitting and the ordinary native loader refuses it. Diagnostics record method, raw-annotation hash, offsets and fallback status. Fold-local fitting is required for evaluation. |
| P1 | New consent publication left old active assignments alive. After re-consent, a new vote could retain the old consent version; browser checkboxes also survived a version refresh. | Publication cancels pending leases, new leases bind the new receipt, and the browser resets confirmations/rating state when the version changes. Real-browser and backend regressions pass. |
| P1 | Image-containing in-memory exports capped useful collection size and made unnecessary browser copies. | New v2 browser archives are metadata/labels only, with a private hash inventory. The existing operator CLI checks live revocation and materializes images one at a time. V1 compatibility, corruption, partial cleanup and withdrawal are tested. No limit was raised. |
| P2 | Broad prefix body limits expanded unrelated JSON mutations as well as uploads. | Only exact native-preview, aesthetic, personal-dataset and study image submission paths get 6 MiB framing allowance; adjacent mutations remain 1 MiB. The API still enforces 4 MiB image bytes. Built-proxy tests cover exactly 4 MiB, one extra byte, Origin/CSRF and unrelated paths. |
| P2 | Opening history reused a cached row, bypassing a fresh expiry/deletion check. | Opening now re-fetches the owned record; a deleted cached row cannot become a displayed result. Retention, earlier checkpoint attribution and private cache headers are tested. Already downloaded copies cannot be recalled. |
| P2 | Unequal coverage was inverted using mean half-panel size, negative correlations became zero, and image bootstrap intervals could look population-wide. | Retain negative observed agreement; suppress unsupported projections for heterogeneous/disconnected/uncertain cases; label intervals as descriptive conditional image resampling, not rater/subject/population or label confidence bounds. |
| P2 | Rejected sources remained up to retention and occupied active capacity. | Immediate access revocation and durable physical erasure; removed files cannot be re-approved. Pending erasures retain their disk reservation. |
| P2 | Research scripts trusted a `development.csv` filename; undefined new experiment rank summaries were not handled. | Precomputed runners validate the immutable subject registry before numeric labels/images/embeddings are consumed. Undefined rank stays null, not zero. |
| P2 | The release roadmap proposed calibrating and checking uncertainty on the same external holdout, and overstated encoder/data conclusions. | Separate development calibration, freeze before external testing; qualify encoder/rater-budget conclusions and approximate aggregate parity. No candidate promoted. |

Detailed scope and mathematics: [native review qualifications](native-aesthetic/scoring-milestone/README.md)
and [Phase 7A co-design review](phase7a/peer-review.md).

## Research challenge and limits

The committed development reports are arithmetically consistent with MobileNet MAE
0.55263 vs train-mean 0.65792 (difference about -0.10529). Their intervals are descriptive
resampling of fixed OOF errors over overlapping repeated folds. They omit retraining,
selection and rater uncertainty and are not independent consumer validation. No reliable
gain is not a demonstration that larger encoders are inferior or equivalent.

The ONNX/PyTorch aggregate MAE differs by about 4.98e-7, and mean repeat-level rank by
2.25e-4: close agreement, not an exact per-input equivalence demonstration. The learning
curve averages fold correlations, while the main comparison uses whole-repeat OOF
correlations; repeat-averaged prediction rank is another estimand. The report now says so.

The reported 0.25 rater statistic and 12/30 budgets describe one face/rater population
under its missingness assumptions. Subpanels share observations with the full consensus.
They are planning hypotheses, not universal sufficiency guarantees. Adjustment additionally
assumes additive/exchangeable rater effects and ignorable missingness; it cannot repair
informative skipping, preference interactions or cohort confounding automatically.

The `warn >1.85` / `withhold >2.82` values remain experimental feature-distance heuristics.
They are **not face detection**, adulthood checks, fairness evidence or reliable input-
suitability probabilities. A non-face with similar features may pass, and valid portraits
with different pose, lighting, skin tone or camera may fail. No measured false-accept/
reject rates or subgroup uncertainty support consumer use. The guard applies to the Owner
preview; future consumer entry points require their own reviewed enforcement and evaluation.

This fresh environment contains no approved London portraits/ratings, pinned checkpoint
or reviewed encoder graph. The reviewer did **not** rerun genuine human-model inference,
the 80-subject experiment or the six real-weight tests. No new data was acquired to fill
that gap; sealed London 20 labels were not accessed or used for tuning. Claude's genuine-
inference observations are retained as attributed evidence, not claimed as independently
reproduced here. A request for the existing approved artifact location remains separate
from any permission to collect new data.

## Verification

On the prospective combined tree:

- Backend/integration: **298 passed, 6 reviewed-weight opt-in skips**; migrations and
  metadata checks use fresh SQLite and randomized PostgreSQL schemas.
- Built Next.js → real FastAPI Codespaces/proxy checks: **5 passed**, including the native
  queue/lifecycle, exact upload boundaries, ownership, CSRF/Origin and no-store headers.
- Frontend: **153 unit tests**, ESLint, TypeScript and default production build pass.
- Native UI contract browser suite: **16 passed**.
- Real browser → built proxy → API study/native transport suite: **3 passed** (bilingual
  collection/export/removal, new-version consent reset, native queue/withholding/history/
  deletion and ordinary-user denial). Browser fetches are not replaced in these tests.
- Ruff, format and strict mypy pass (99 source files).

The native real-browser transport test deliberately substitutes only the child execution
with a **withheld-result fixture**, clearly labelled `NO MODEL INFERENCE`. It publishes no
attractiveness number. Its server requires both isolated-fixture flags, provisions only a
fresh in-memory SQLite database, and is excluded from production Docker builds. It is a
regression for routing/auth/storage/queue/contracts/UI, not genuine checkpoint inference.

Both reviewed source heads have all five green GitHub Actions jobs:
[#15 run](https://github.com/opsevener-cmd/auvylen/actions/runs/42366140046),
[#16 run](https://github.com/opsevener-cmd/auvylen/actions/runs/42366405814).
The verification branch runs those same five jobs on its own exact pushed head; use that
run's result, not a source-head success, when judging the prospective integration.

New browser snapshot creation is tested to read zero portrait bytes. A generated 300-image,
60-rater/1800-vote, one-thread probe under tracemalloc measured rater fit at 0.0075 s and
conditional diagnostics at 4.16 s (median of three); peak traced allocations 0.55/1.15 MB.
These are generated-array costs, not human-model accuracy, portrait-inference latency or
process peak RSS. Keeping diagnostics optional avoids that cost on normal raw exports.

## Shortest responsible path to a scoring beta

1. Restore the **already approved** private encoder/checkpoint and development-only
   assets in an authorized environment. Re-run real-weight tests and genuine portrait
   inference through the built browser/API/worker path, recording pins and latency.
2. Validate input suitability on approved development-only portraits and non-person
   fixtures, including false acceptance, pose/lighting/device failures and uncertainty.
   Review a real single-face detector if needed; do not mistake distance for detection
   or infer age/protected traits from appearance.
3. Seek approval for intended-use rights, final consent, recruitment/budget, processors,
   identity/independence checks, secure custody, deletion/backup/restore and capacity.
   The current first-party consent/export policy is **non-commercial research only**;
   first-party opt-in does not itself grant consumer-service rights. The repo remains public.
4. Run a bounded approved pilot; choose rater/cohort sizes from measured precision rather
   than assuming 12/30 or 400/200 are sufficient. The 200-active-photo limit and 256 MiB/
   3000-image native loader limits still constrain larger plans. No cap was casually lifted.
5. Freeze the candidate and separate development calibration before a separately custodied,
   preregistered external holdout evaluation with baselines, uncertainty and real repeat
   captures. Then seek explicit authorization for a limited adult self-photo beta.

**Consumer scoring and real participant collection: NO-GO.** Existing accounts, Credits,
personal models, datasets, checkpoints, backup procedures and private port protections
remain intact. Nothing was deployed or activated. Preserve a verified external encrypted
backup before any later approved live migration or rollout.
