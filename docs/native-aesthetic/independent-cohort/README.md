# Independent evaluation plan and private native preview

Continues draft PR #12 from `ba59e842`. **NO-GO for consumer scoring. GO for a
reviewed private Owner feasibility preview only.** No merge or deployment performed.

## What improved, and what did not

There is now a real authenticated single-portrait research path at
`/research/native-preview`, backed by the existing durable queue, native learned
head and reviewed MobileNet encoder. It requires no personal dataset or personal
training. It is a separate laboratory capability, disabled by default and forbidden
in staging, production or public-pilot configuration. NativeProvider/NativeEngine
consumer release checks are unchanged. No ComboLoss/FPEM code or weights, duplicate
provider, Credits charging, new database table or migration is introduced. PR #11
remains independent; its binary-upload/privacy/job patterns were reviewed rather
than cherry-picking that branch or its model implementation.

**No larger authorized collection has arrived. No new model was trained or tuned.**
The London 20-person test remains closed to development. The previous published
aggregate estimates below are repeated for interpretation, not new evaluation:

| Fixed London candidate (native 1–7) | MAE | RMSE | Spearman |
| --- | ---: | ---: | ---: |
| Validation-selected MobileNet ridge | .510 | .640 | .367 |
| Validation-selected handcrafted ridge | .489 | .621 | .283 |
| Train mean | .572 | .652 | undefined |
| Train median | .563 | .637 | undefined |

MobileNet's MAE CI .346–.681, rank CI −.163–.747, and paired MAE vs mean CI
−.222–.095 do not establish reliable improvement. Its RMSE is worse than the median
baseline's. The handcrafted model was not promoted based on test MAE. The original
[full report](../london-pilot/README.md) includes subgroup sample counts, including
zero east_asian test subjects and other underpowered cohorts. Frontal neutral
portraits and synthetic photographic perturbations do not validate real pose or
lighting generalization. No individual uncertainty interval is invented by the UI.

[Acquisition decision and rights matrix](acquisition.md): prepare 400 development
and 200 independently collected/custodied external subjects, four real captures
and 30 genuine ratings per image. These are proposed targets. No recruitment,
contact, contract acceptance or expenditure has been authorized or performed.
The [consent/rating/removal draft](participant-procedure.md) specifies separate
image, annotation, subject, cloud, derived-weight and intended-service grants.

[Prospective protocol](protocol.json) SHA-256:
`50ddbdc53f51c4a10d8582c161e85bed9055e13c5f527032aaa8b0f99844d0fe`.
**This freezes a plan, not a populated external holdout.** The custodian must seal
actual subjects, image/label/rights hashes and partitions before any fitting on the
new collection. Neither existing test subjects nor their alternate photographs
qualify as new independent holdout people. Do not upload external-holdout images
to the preview during development. Developer preview access cannot technically
prove independent recruitment; custody and consent registries are necessary.

## Genuine research preview verification

[Machine-readable timing evidence](preview-verification.json). Opt-in isolated
SQLite/API tests used the existing hash-pinned human-trained London checkpoint and
**one development portrait**, selected from its training partition for engineering
verification. No old test portrait, labels or aggregate test outcome was used to
choose or improve a model. The photograph, individual prediction, model head and
encoder remain private and excluded from Git.

Verified: fresh Owner login → CSRF-protected binary upload → lossless metadata-free
private image → durable leased CPU subprocess → schema-checked native 1–7 result →
image removal → explicit result deletion. The prediction matched direct original-
portrait inference exactly (difference **0**). Product NativeProvider still reports
`validation_gate_failed`; default strict checkpoint loading still refuses release.

One CPU observation, not a latency distribution: upload acceptance **375 ms**,
worker plus authenticated result read **348 ms**, upload-to-verified-read **723 ms**;
child model load/decode/encoder/head **110 ms**, child process high-water RSS
**211.5 MiB**. Includes cold subprocess and repeated integrity checks; no artificial
queue wait/network latency was added. TestClient runs in-process, so these are
**not** Internet/browser upload timings. RSS is Linux `ru_maxrss`, not a measured
whole-service aggregate. The preceding offline warm median **28.5 ms** excludes
these API/process costs. No ONNX conversion, approximation or encoder change was
made. Repeat the opt-in test for representative latency distributions before deployment.

Reproduce locally with reviewed private files (paths are placeholders, no download):

```sh
AUVYLEN_PREVIEW_VERIFY_ROOT=/private/candidate \
AUVYLEN_PREVIEW_VERIFY_IMAGE=/private/authorized-development-portrait.jpg \
AUVYLEN_PREVIEW_VERIFY_ENCODER_ROOT=/private/models/pretrained \
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
uv run pytest services/api/tests/test_native_preview.py --pretrained -q
```

Do not point test settings at the live database. The fixture builds/migrates only
temporary SQLite, provisions an ephemeral test Owner and never reads existing
accounts. `AUVYLEN_PREVIEW_VERIFY_EVIDENCE` optionally writes aggregate timings;
keep individual outputs/photos out of reports. Standard CI does not have these
private weights, so its opt-in skip is not a reproduced real-inference result.

## Browser and security evidence

Production-build Chromium checks pass in English/Chinese, desktop/mobile: disabled
state, no score when unavailable, real XHR binary body, CSRF header, consent,
language change preserving selected file/confirmation, queued state, disabled double
submission and deletion/cancellation. Browser API responses are explicitly **UI
contract fixtures**, independent of the real model integration test above.
Screenshots show the truthful default-disabled UI with no portraits or predictions:

- [English desktop](native-preview-disabled-en-desktop.webp)
- [Chinese mobile](native-preview-disabled-zh-mobile.webp)

Regression checks cover signed-out/ordinary account denial, stale Owner sign-in,
CSRF, missing/corrupt checkpoint availability, file/metadata limits, idempotency,
cross-account access, failed/expired jobs, orphan cleanup, review changes before
publication, out-of-scale/consumer/synthetic output rejection and deletion fencing.
Existing Codespaces forwarding/Origin/session enforcement is unchanged. Generic
research job endpoints cannot bypass the preview namespace's permission or expiry.
There is no public/private-photo cache, image-serving URL or photo in the browser
screenshots. Upload consent explicitly excludes training and public display.

Retention: images removed when jobs finish, maximum one hour while the worker
runs; results expire after 24 hours. Purge runs every worker minute, on submission
and before result reads. Crashed-transaction orphan files are also bounded by the
image cap. A worker outage delays physical cleanup; do not operate this preview
without supervision/cleanup monitoring. Deletion immediately fences publication;
an already executing child may continue until the 60-second wall timeout. CPU
limit 30s, address-space limit 4 GiB, one thread, existing global queue cap. File
mode 0600, owner directory 0700; metadata is stripped without lossy recompression.
No existing dataset, personal model, Owner account, wallet, backup or port changed.

## Safe research operation and release checklist

This PR enables nothing by default. After review, use an **isolated private
research development/test instance**, never edit the live Codespace during testing:

1. Preserve/verify an external encrypted backup before any later live rollout.
2. Install the reviewed encoder and human-trained head privately; verify manifest,
   head and encoder hashes and separate research rights. Never download or import
   ComboLoss weights. Do not add the native model to consumer enable lists.
3. Configure the same values in the isolated API and worker:
   `RESEARCH_MODE=true`, `NATIVE_PREVIEW_ENABLED=true`,
   `NATIVE_PREVIEW_CHECKPOINT=/private/candidate`,
   `NATIVE_PREVIEW_MANIFEST_SHA256=<reviewed pin>`,
   `NATIVE_PREVIEW_REVIEW_REFERENCE=<recorded closed-study rights review>`,
   and existing private model/upload roots. Only `APP_ENV=development` or `test`
   is accepted; public pilot is prohibited. No Compose deployment flags are changed.
4. Start the existing worker, sign in freshly as the test instance's Owner, verify
   status/provenance, upload an authorized development portrait, check native 1–7
   result, deletion and timed cleanup. Verify consumer provider remains unavailable.
5. Turn the preview switch off to withdraw execution capability. Keep the worker
   cleanup running; confirm final private artifacts are gone. No database reset.
6. Acquire separately authorized independent data and freeze external custody;
   lock candidates via development/validation only; then execute one external
   evaluation with baseline differences, uncertainty and real-capture/subgroup
   counts. Obtain intended-use rights review and explicit release authorization.

**Current release decision: NO-GO.** Unmet: larger consented data, actual independent
holdout seal/evaluation, credible baseline advantage and subgroup/pose/lighting
coverage, plus intended-service rights. A working upload path cannot resolve those
scientific/legal blockers. No automatic merge, deployment or consumer activation.
