# ComboLoss — feasibility assessment (no integration)

Assessment only, 2026-10-27. Nothing was downloaded, installed, trained, enabled or
deployed. The `comboloss` provider slot remains *unavailable*, exactly as before.

## What it is

ComboLoss (Xu & Xiang, 2020, "ComboLoss for Facial Attractiveness Analysis with
Squeeze-and-Excitation Networks") fine-tunes a whole SE-ResNeXt-50 CNN on face
photographs. Its combined objective adds a classification term over discretised score
classes, a regression term on the score, and an expectation term. It is evaluated on
public facial-beauty benchmarks, chiefly SCUT-FBP5500. The official implementation
identity was verified in Phase 4A (<https://github.com/lucasxlu/ComboLoss>).

## Fit with Phase 6

| Aspect | Phase 6 Auvylen model | ComboLoss |
| --- | --- | --- |
| Learning | Linear head on frozen features; CDF loss on five-bin vote distributions | Full CNN fine-tuning; classification, regression and expectation losses |
| Output | Five-bin distribution, expected 1–10 score, calibrated range | Single score (dataset scale) plus class probabilities |
| CPU cost | ~0.03 ms head plus MobileNet extraction | SE-ResNeXt-50 forward pass, roughly 4 GFLOPs per 224 px face. Plausible on CPU only after ONNX export, at one image at a time |
| Preprocessing | Whole photograph | Benchmark faces are detected, cropped and aligned. Auvylen has no reviewed face detector, so whole photographs would be out of domain |

**Reuse that is sound.** ComboLoss fits the existing isolated `ModelProvider` plugin
contract as a research-only comparison engine, built in its own worker image. It can
reuse Phase 6's infrastructure:
- the pinned-manifest SHA-256 integrity checks;
- the registry research policy gate;
- the subject-independent test protocol;
- baselines, Spearman correlation and conformal calibration;
- fail-closed availability.

That would allow a fair side-by-side on the same held-out subjects once an authorized
dataset exists.

**Reuse that must not happen.**
- ComboLoss predictions are never labels for personal or Phase 6 models (Phase 4B master
  instruction).
- It is never merged into the first-party model's code.
- Its outputs are not presented as Auvylen's own score.

## Dependencies and licensing — unresolved blockers

1. **Code licence:** not verified in this session. A public repository is not permission.
2. **Weights:** checkpoint provenance and licence are unverified. The weights were trained
   on SCUT-FBP5500, whose release terms must be reviewed directly; academic benchmark
   datasets are commonly restricted to non-commercial research. Any commercial Analyze use
   would need explicit written rights.
3. **Runtime:** PyTorch and torchvision, plus an SE-ResNeXt definition, would go in a
   separate, locked worker image. Prefer a reviewed, pinned ONNX export, as was done for
   MobileNet, to keep the API image unchanged.
4. **Face detection and alignment:** this needs its own licence and provenance review,
   and must never be used to estimate age.
5. **Bias:** SCUT-FBP5500 has a narrow demographic and annotator population. Results
   would need the same limitation disclosures as Phase 6.

## Recommendation

ComboLoss is feasible later as an **optional, research-only comparison provider**, after
code, weight, dataset and face-detector licences are verified, and evaluated on the same
authorized subject-independent test set as the Phase 6 model. It is not suitable as a
commercial Analyze engine without commercial rights. It is not needed for, and must not
block, the first-party Phase 6 pipeline.
