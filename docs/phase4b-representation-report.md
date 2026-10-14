# Phase 4B pretrained representation milestone — 2026-10-14

## Outcome and preservation

Continued from `b37d2b8fdd6625bfc93c4e7731c5b7c396576f89` on
`codex/phase4b-custom-preferences`. The local and explicitly fetched remote branch
matched at the start; GitHub confirmed `opsevener-cmd/auvylen` remains private.
The new first-party preference engine supports frozen **MobileNetV3-Small ImageNet
embeddings**, genuine user-rating regression, identical grouped baseline comparisons,
versioned private checkpoints, cached retraining and unseen-image predictions in the
existing website. The old handcrafted extractor remains the default and fully usable.

No schema migration or rewrite of old checkpoints/annotations/jobs was needed. All
Phase 4A account, Credits, redemption, payment architecture and research infrastructure
remain. Research scoring/training never spends Credits. A golden test derived directly
from `b37d2b8` reproduces the original checkpoint bytes and prediction exactly. New model
versions have their own extractor ID/manifest; removing pretrained weights makes only
those versions unavailable. External scoring plugins remain independently removable.

## Licensing and actual model

The exact source is timm 1.0.30 `mobilenetv3_small_100.lamb_in1k`, with **Apache-2.0
source code and explicitly declared Apache-2.0 checkpoint licensing**. Source checkpoint
SHA-256 is `266a294cbf3d119000a760bf5664a4d80a9674d0616b5cc0836b093d20c38249`
(10,256,237 bytes). The exported graph SHA-256 is
`164c481657afe9d36e08ff58693df24e511b5bf1a07de9b9389dfc468eedd2a6`
(6,078,515 bytes). Source/license/modification notices are retained.

Runtime: ONNX Runtime 1.31.0 **MIT**, NumPy 2.5.4 **BSD-3-Clause**, Pillow 12.3.0
**MIT-CMU**. Export only: PyTorch 2.10.0+cpu and TorchVision 0.25.0+cpu
**BSD-3-Clause**, ONNX 1.22.0 **Apache-2.0**. Installed distributions retain their
additional bundled-library notices. Exact evidence, pinned links, configuration,
preprocessing, hashes and operator instructions are in
[pretrained-representation.md](pretrained-representation.md).

The ImageNet classifier is removed; the model returns 1,024 penultimate activations.
Two independent exports produced identical bytes. Comparison with upstream timm
preprocessing/PyTorch on a generated rectangular image had maximum absolute activation
difference **7.87e-6**, within 1e-4 tolerance. Production inference uses the small ONNX
graph and CPU runtime; it does not install PyTorch/timm or deserialize Python objects.

## Measured resources and comparison

Execution was entirely in managed remote Debian 13 Linux containers, 2 CPU cores and
8 GiB cgroup RAM, with a 32 GiB workspace and VFS Docker storage. The environment was
recreated during work; private artifacts and source survived. No Windows services,
purchased infrastructure, GPU or public deployment was used.

Final sequential component benchmarks used 500 generated 256px texture images with
arbitrary simulated numerical ratings, 250 supplied groups, seed 42, alpha 10 and
an 80/20 grouped split (400 training images, 100 validation images). These are resource
and correctness fixtures, **not real faces or accuracy evidence**.

| Measurement | Handcrafted baseline | MobileNetV3-Small |
| --- | ---: | ---: |
| 500-image feature extraction | 0.415 s | 1.537 s |
| Extraction throughput | 1,204 images/s | 325 images/s |
| Single-image extraction median / p95 | 0.760 / 0.928 ms | 2.486 / 2.830 ms |
| Ridge fitting + validation | 0.0159 s | 0.0204 s |
| Peak benchmark process RSS | 62.2 MiB | 170.0 MiB |
| 500 embeddings serialized as JSON | 2.31 MB | 10.10 MB |
| Personal rating checkpoint in this fixture | 13.4 KB | 60.1 KB |

MobileNet runtime initialization measured 0.217 seconds in the 500-image process; a
separate 1,000-image process initialized in 0.068 seconds. Warm-cache/scheduling effects
matter; these are small development measurements, not latency guarantees. Component
extraction timing excludes network/queue/UI overhead. Full worker prediction timings
are recorded separately by the HTTPS recreation test: **60.3 / 132.3 ms** for MobileNet
and **21.9 / 34.2 ms** for the handcrafted model, before / after container recreation
and forced embedding recomputation. Both raw predictions were exactly identical. These
are two samples per extractor and exclude queue wait and browser polling.

In real PostgreSQL/private storage/worker capacity tests with 500 generated color images:

| Measurement | Handcrafted job | MobileNet + matched handcrafted comparison |
| --- | ---: | ---: |
| Ingest + annotate 500 images | 14.14 s | 13.92 s |
| First durable training job | 9.13 s | 12.37 s |
| Cached retraining job | 8.02 s | 7.02 s |
| Reused embeddings | 500 | 1,000 (500 for each extractor) |

Earlier runs on the preceding cloud instance measured lower job times (MobileNet 7.56 s
first / 4.65 s cached), demonstrating ordinary development-host variance. Private image
bytes for this tiny color fixture totaled 769,257 bytes; real photographs can be much
larger and remain subject to the 512 MiB owner quota. JSON embedding sizes exclude DB
indexes, row overhead, compression, snapshots and backups. ONNX Runtime's installed
distribution occupies approximately 64.5 MB; the shared NumPy/Pillow distributions
approximately 56.4/19.7 MB. Operator-only export tooling was approximately 1 GiB plus
package caches. Build/container overhead is separate and much larger with VFS storage.

On the same synthetic holdout:

| Predictor | MAE | RMSE |
| --- | ---: | ---: |
| Training-mean predictor | 2.6224 | 2.9330 |
| Handcrafted ridge | 3.1238 | 3.9207 |
| MobileNet ridge | 3.1799 | 3.9133 |

The mean predictor was better here; MobileNet did not improve MAE over the handcrafted
baseline. Arbitrary ratings on synthetic textures cannot establish facial preference
accuracy, positive or negative. The website computes the corresponding comparison from
each owner's actual eligible annotations using identical identity-grouped holdouts,
training-only normalization and the same alpha. No accuracy improvement is claimed.

The largest **fully tested application dataset is 500 images**, with training, cached
retraining, deletion/cleanup and rejection of image 501 tested on real PostgreSQL.
A separate **1,000-image extraction-only** experiment completed in 2.892 seconds at
209.4 MiB peak process RSS. Training above 500 was deliberately not enabled. The quota
counts all owner images, including prediction inputs; reserve slots for new uploads.
Concurrent users, full-size images, DB storage/backups and cleanup at higher limits need
additional testing before any quota change. All current quotas remain in force.

Raw aggregate measurements are in [evaluation](evaluation/); they contain no photographs,
user identifiers, individual annotations or model coefficients.

## Verification

| Check | Result |
| --- | --- |
| `uv run pytest --integration --pretrained -q` | **152 passed**, no skips; 146.11 s |
| Frontend unit tests | **32 passed** |
| Development browser suite with both extractors | **5 passed**, 46.6 s |
| HTTPS cloud suite with both extractors | **4 passed**, 2.4 minutes |
| Ruff lint / format | Passed, 126 formatted files |
| Mypy | Passed, 60 source files |
| ESLint / TypeScript | Passed |
| Next.js host production build | Passed |
| Final API/worker and web production images | Built successfully |
| Cloud readiness / Alembic schema check | Ready, all six services healthy; no schema drift |

The tests cover actual pretrained extraction, batch/single consistency, changed pixels,
JSON manifest/finite-vector validation, old checkpoint compatibility, matched holdout
indices/errors, cache reuse, owned unavailable-weight rejection, corrupted-weight failure,
legacy predictions after pretrained removal, real worker execution, quotas, source
cleanup and unchanged Credits. The website tests upload/rate, train, predict a new image,
add its annotation, retrain and reload preserved versions for both extractors. Cloud
recreation tests remove only their generated prediction image's cache before recomputing,
so cache reuse cannot hide an extractor/weight persistence problem.

Failures encountered and resolved: the first 500-image quota assertion expected the wrong
error wording; a browser select locator needed the combobox role; a test worker needed
direct Python process termination; a pretrained test fixture needed a repository-relative
weight path despite tests changing cwd; and Compose copying preserved a host UID that
required a narrowly scoped pretrained-bundle ownership repair. Normal application
capability restrictions were retained. The ONNX Model Zoo candidate download was blocked
by network policy; the independently licensed timm candidate succeeded through approved
GitHub Releases. No policy bypass or network change was needed. Cloud restarts temporarily
interrupted terminal access; source and private volumes were retained.

Disk headroom was monitored. Unused Docker **build cache only** was reclaimed when needed;
no Docker volume prune, `down -v`, data deletion or repeated blind rebuild loop was used.
Final source/model selection was tested before final image builds. Images, private data,
credentials and the pre-existing backup remain excluded from Git.

## Real evaluation and remaining work

[The adult-face evaluation workflow](evaluation/adult-face-workflow.md) and its deliberately
unapproved example plan establish licensing/access review, verified adult ages, complete
subject IDs, explicit temporary-cloud authorization, a deletion deadline and approved
backup/retention arrangements before importing photographs. The executable plan validator
checks those fields without downloading or reading photos. No real face dataset has been
authorized or imported for this milestone.

Outstanding quality work: authorized adult-face studies, preregistered external holdouts,
subject-level uncertainty estimates, annotation consistency and crop/lighting sensitivity.
MobileNet is a general-object representation, not a face/age/identity detector. Small
personal holdouts and unknown identities remain material limitations.

Pairwise annotation remains implemented; a separate pairwise ranking trainer is still
future work. Independently licensed/installed GitHub scoring plugins and calibrated
comparison UI remain future work; they do not supply labels or dependencies to custom
models. No public deployment or commercial model approval is implied by this milestone.

After verification, the disposable loopback HTTPS stack was stopped with `down` and
**without `-v`**. Its PostgreSQL/private model/upload volumes, installed graph and
matching ignored credentials remain intact. The pre-existing development PostgreSQL
and Redis services were left untouched. No paid or publicly deployed service exists.
