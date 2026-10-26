# Phase 6 — original aesthetic scoring system (6A–6C)

Prepared on 2026-10-26 in a disposable remote Linux container from `1806972` on
`codex/phase4b-custom-preferences` (PR #4 merge). No live Codespace, Owner account, private
photograph, dataset or backup was accessed. Nothing was deployed or merged.

## Outcome

- **6A, core algorithm:** the specified distribution model (linear head → softmax over five
  ratings → expected rating → 1–10 display) is implemented in the inference package. It
  includes exact CDF-loss gradients, subject-independent train/validation/test splits,
  training-only normalization, Spearman/Pearson correlation, mean and mean-distribution
  baselines, split-conformal calibration and immutable SHA-256-pinned checkpoints. Details:
  [aesthetic scoring](aesthetic-scoring.md).
- **6B, website integration:** an asynchronous, owner-scoped API on the existing durable
  PostgreSQL job queue and worker. Private images are deleted after scoring. Migration
  `0009` adds the request table. The bilingual `/research/aesthetic` page shows the 1–10 score,
  the five-category distribution, model and calibration versions, the calibrated range,
  predicted annotator spread, a model card with baselines, and limitations.
- **No authorized human-rated dataset exists**, so no genuine checkpoint was trained and
  user-facing scoring is **disabled by default and fails closed** (503, *unavailable*). No
  real-photo accuracy claim is made. The only checkpoints in this work come from generated
  data. They are refused by the release gate unless a development/test-only setting is on,
  and every result is labelled synthetic.

Preserved unchanged: the synthetic `/analyze` implementation and mock engine, accounts,
Credits (research never mutates them), Owner administration and entitlements, personal
preference datasets and models, the MobileNet extractor and its checksum, the Codespaces
Origin/CSRF policy, and all existing routes and identifiers.

## Verification (this container)

| Check | Result |
| --- | --- |
| `uv run pytest` | 183 passed, 28 skipped (integration/pretrained opt-ins) |
| `uv run pytest --integration` (PostgreSQL 18-compatible local server + Redis) | 207 passed, 4 skipped (reviewed MobileNet weights not installed) |
| Alembic upgrade → `0009`, downgrade to `0008`, upgrade, `alembic check` | Passed; no pending operations |
| `ruff check`, `ruff format --check`, strict `mypy` (75 files) | Passed |
| `npm test` / `lint` / `typecheck` / `build` | 133 passed / clean / clean / built (`/research/aesthetic`) |
| Playwright (Chromium), `E2E_RESEARCH=true`, no checkpoint | 7 passed, 1 skipped; includes the bilingual *unavailable* state |
| Playwright with the synthetic test checkpoint | Upload → worker → score, distribution, calibration version, Chinese/English, delete: passed |

New automated tests:

- **Mathematics:** finite-difference gradients for the loss (logits) and the full
  objective (W, b, weight decay); the loss formula; softmax stability; S5/S10 endpoints;
  rating spread; ties-aware Spearman; the conformal rank.
- **Training:** subject-disjoint deterministic splits; normalization from training rows
  only; modifying every test feature and label leaves the fitted head bit-identical;
  learnable generated data beats both baselines; input refusals (fewer than 60 images,
  fewer than 15 subjects, no variation, mismatched dimensions).
- **Checkpoints:** round trip, read-only files, no overwrite, path traversal, wrong pin,
  weight bit-flip, extractor-manifest change rejected even when re-pinned, release gate
  failing on synthetic or noise-only models.
- **Training command:** publishes from vote counts; refuses mean-only labels, traversal,
  too few votes and invalid plans.
- **API/security:** 401/403/CSRF; 503 with no job or file when unavailable; consent, format,
  size, aspect and blank checks before storage; idempotent retries; other users get 404;
  deletion clears results; image deleted after success, failure and tamper; revoked access;
  no Credit transactions; settings forbid synthetic checkpoints in staging/production.
- **Web:** wire-schema rejection of malformed scores and distributions; fixed reason
  vocabulary; exact proxy allowlist for the new routes; translation-key coverage.

CPU (generated data, 1 BLAS thread, 4-vCPU container;
[raw measurements](phase6/cpu-benchmark.json)): head inference **0.03 ms/image**;
handcrafted extraction 4.9 ms/image; training 600×1024 in 0.09 s, 5,000×1024 in 5.5 s at
~56 MiB peak traced allocations. MobileNet extraction cost is unchanged from
[Phase 4B](phase4b-representation-report.md).

Screenshots show generated test data only. The synthetic-model warnings are visible:
[English desktop](phase6/aesthetic-en-desktop.webp) · [Chinese mobile](phase6/aesthetic-zh-mobile.webp).

## Not verified here / blockers

- **Authorized training data.** A dataset with per-image human vote distributions,
  subject identifiers, adult-only subjects and a licence covering this research must be
  reviewed and approved (see `docs/evaluation/adult-face-workflow.md`). Until then real
  scoring stays off.
- **MobileNet-backed execution** was not run: the reviewed weights are not installed in
  this container. The four opt-in `--pretrained` tests skip, and that skip is not a pass.
  The synthetic checkpoint uses the built-in handcrafted extractor.
- **Automated single-face detection** is not implemented. It needs a separately reviewed
  detector (code and weight licences). Adulthood is never inferred from appearance.
- **Commercial use** (Auvylen Analyze for paying users) is not enabled. It needs licence
  evidence for the dataset, the extractor and the photographs.
- The `cloud-research` Docker Compose CI job was not run locally; it runs on the PR.
  CI uses Node 24; this container ran Node 22.

## Safe rollout

No deployment is performed. After review, merging adds migration `0009` (a new table only).
Back up before running the explicitly authorized migration gate. Leave
`AESTHETIC_SCORING_ENABLED=false` until a validated checkpoint is pinned, following the
[operator procedure](aesthetic-scoring.md#operator-procedure-remote-linux-environment-only).
