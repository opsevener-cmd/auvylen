# Phase 7B — resumable frozen-encoder research (development data only)

Status: pipeline ready; **London processing on Colab/Drive awaits Owner confirmation** of §1.
No model is promoted, enabled or deployed by this directory. Checkpoints stay research-only.

## 1. London rights for Colab/Drive processing (verified 2026-11-09, needs confirmation)

| Item | Evidence (pinned commits) | Conclusion |
| --- | --- | --- |
| Portraits | `debruine/webmorphR.stim@fa8b78fd`: `LICENSE.md` = CC BY 4.0. README: all individuals gave signed consent for images to be "used in lab-based and web-based studies in their original or altered forms" | Copying/processing on cloud infrastructure for this closed research study fits the licence and the stated consent. Attribution kept. |
| Ratings | `debruine/demopsydata@1b5d2a17`: `DESCRIPTION` = `License: MIT + LICENCE` (holders DeBruine & Jones). `R/data.R` documents 2,513 raters, 1–7 scale, same London set | Processing permitted with notice retained. |
| Not established | Rights for a consumer service, publicity/personality rights for service use, any Google-specific consent | Unchanged: research only. |

**Proposed storage arrangement**
- Raw portraits and ratings are fetched inside each Colab session from the authors' pinned
  commits, hash-verified by `native_london.prepare`, and kept on the VM's ephemeral disk only.
- The 20 sealed subjects are dropped (`development_table`) and their files deleted before any
  image is opened. Only the 80 development subjects are embedded.
- Persistent storage: one private, unshared folder in the Owner's Google Drive
  (`MyDrive/Auvylen-Phase7B`). It holds derived embeddings (derived personal data), the
  append-only ledger and aggregate results. No raw portraits or ratings go to Drive.
- Retention: delete the London embeddings when Phase 7C closes. Nothing goes to Git except
  code and aggregate results.

This is an engineering reading of the licences, not legal advice.

## 2. Encoder licences, accessibility and CPU deployment (public weights, generated input)

Measured on a 4-vCPU box with ONNX Runtime 1.20, opset 17. Revisions are pinned.

| Encoder | Licence | Gated | Dim | ONNX | CPU 1 / 4 threads | ONNX vs PyTorch | Service candidate |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| DINOv2-small `ed25f3a3` | Apache-2.0 | no | 384 | 84 MB | 140 / 106 ms | 1.8e-5 | yes |
| DINOv2-base `f9e44c81` | Apache-2.0 | no | 768 | 331 MB | 505 / 289 ms | 1.3e-5 | yes |
| SigLIP-base `7fd15f06` | Apache-2.0 | no | 768 | 355 MB | 360 / 198 ms | 6.7e-6 | yes |
| OpenAI CLIP B/16 `57c21647` | MIT code; model card: "any deployed use case … is currently out of scope" | no | 512 | 329 MB | 349 / 118 ms | 4.8e-6 | **no — research comparison only**; weights only as pickle |
| MobileNetV3-Small (reference) `76b303ec` | Apache-2.0 | no | 1024 | 6 MB | ~30 ms | reviewed | current pilot |

Raw output: [encoder-deployment-check.jsonl](encoder-deployment-check.jsonl). Phase 7C must
recheck memory: the worker caps address space at 4 GiB; the export process peaked near 2 GB.

## 3. Pipeline (`auvylen7b`)

- `store.py`: atomic writes (temporary file, fsync, rename), content-addressed units, an
  append-only `ledger.jsonl` and paths sandboxed to the store root.
- `data.py`: London development loader (above) and a generated `synthetic` smoke set, flagged
  `synthetic=True` everywhere.
- `encoders.py`: pinned registry and per-(encoder, view) embedding shards. A rerun after a
  disconnect skips finished shards. Views: clean, mirror, and the pilot's lighting and crop
  augmentations.
- `heads.py`: the pilot ridge rule, plus a **rating-distribution head**: soft-label multinomial
  regression on real per-rater 1–7 histograms. Its score is the expected rating; its spread
  estimates rater disagreement.
- `evaluate.py`: paired subject-grouped CV with the same outer seeds as the earlier CPU
  research, and the **pre-registered decision rule** (in the module docstring, committed
  before any London run).
- `colab/phase7b.ipynb`: GPU check, Drive mount, pinned-commit checkout, synthetic smoke test,
  London run (blocked until confirmed).

Tests (generated data only): `research/phase7b/tests`.

## 4. What this cannot show

Eighty development subjects give low statistical power. A promoted candidate is a
development result. The previously evaluated 20-subject London test is **not** a fresh
external holdout and is not used here. Independent validation needs new, independently
custodied people (Phase 7C and later).
