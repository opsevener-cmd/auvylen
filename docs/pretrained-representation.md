# Pretrained visual representation for personal rating models

Implemented in Phase 4B, October 2026. The permanent custom subsystem now offers
`mobilenetv3-small-imagenet-onnx-v1` alongside unchanged `rgb-grid-texture-v1`.
Both learn numerical preferences from the owner's annotations. Research remains free
of Credit mutations. No attractiveness-scoring plugin or external inference API is used.

## Model selection and exact licenses

| Component | Exact selection | License and evidence |
| --- | --- | --- |
| Architecture/model definition | timm 1.0.30 `mobilenetv3_small_100.lamb_in1k` | Apache-2.0, [pinned source license](https://github.com/huggingface/pytorch-image-models/blob/0df212b369a5385b16dfe513d5143a7311ea1ddc/LICENSE) |
| Original pretrained checkpoint | `mobilenetv3_small_100_lamb-266a294c.pth`, ImageNet-1k | **Apache-2.0 explicitly attached to this pretrained configuration** by `_cfg(license='apache-2.0')`, [pinned model configuration](https://github.com/huggingface/pytorch-image-models/blob/0df212b369a5385b16dfe513d5143a7311ea1ddc/timm/models/mobilenetv3.py#L1057) |
| Converted frozen embedding graph | Auvylen `mobilenetv3-small-100-lamb-embedding-v1.onnx` | Derived Apache-2.0 weights; retained [license](licenses/mobilenetv3-small-LICENSE.txt) and [source/modification notice](licenses/mobilenetv3-small-NOTICE.txt) |
| Production execution | ONNX Runtime 1.31.0 CPU | [MIT](https://github.com/microsoft/onnxruntime/blob/v1.31.0/LICENSE) |
| Operator-only conversion | PyTorch 2.10.0+cpu / TorchVision 0.25.0+cpu / ONNX 1.22.0 | [BSD-3-Clause](https://github.com/pytorch/pytorch/blob/v2.10.0/LICENSE), [BSD-3-Clause](https://github.com/pytorch/vision/blob/v0.25.0/LICENSE), [Apache-2.0](https://github.com/onnx/onnx/blob/v1.22.0/LICENSE) |
| Shared preprocessing/regression | NumPy 2.5.4 / Pillow 12.3.0 | BSD-3-Clause / MIT-CMU; preserve all installed wheel notices and bundled-library licenses |

Source code being public was not treated as checkpoint permission. TorchVision's generic
pretrained-model notice leaves dataset-derived terms to the user, so a blanket BSD claim
was insufficient for selecting its ResNet18 checkpoints. MobileNetV2 from ONNX Model Zoo
was reviewed but its GitHub download redirected to a blocked host. No policy bypass was
used. The separately licensed timm MobileNetV3-Small checkpoint downloaded successfully
through the existing GitHub Releases policy. The earlier request to change the host
allow-list is **not needed**. No ImageNet dataset or real facial photograph was downloaded.

The application approves this combination for non-commercial research only. This review
and a checkpoint license do not grant rights to photographs or authorize a public
commercial attractiveness service. Preserve the source notices with exported weights.

## Reproducible representation

- Source: `https://github.com/rwightman/pytorch-image-models/releases/download/v0.1-weights/mobilenetv3_small_100_lamb-266a294c.pth`
- Source bytes: **10,256,237**; SHA-256:
  `266a294cbf3d119000a760bf5664a4d80a9674d0616b5cc0836b093d20c38249`.
- Converted graph bytes: **6,078,515**; SHA-256:
  `164c481657afe9d36e08ff58693df24e511b5bf1a07de9b9389dfc468eedd2a6`.
- Definition commit: `0df212b369a5385b16dfe513d5143a7311ea1ddc` (timm v1.0.30).
- Conversion: strict source state-dict loading with `weights_only=True`, CPU evaluation
  mode, `reset_classifier(0)`, ONNX opset 17, dynamic batch, no external tensors.
  The pinned legacy TorchScript exporter is intentional; a future exporter change must
  produce a reviewed new extractor ID rather than silently replacing these bytes.
- Features: 1,024 penultimate activations after spatial global averaging, `conv_head`
  and hardswish. The ImageNet classifier is removed. The network remains frozen.
- Preprocessing: EXIF orientation, RGB, bicubic resize of shorter edge to 256, center
  crop to 224 using rounded offsets, float32 /255, NCHW, ImageNet means
  `[0.485, 0.456, 0.406]`, standard deviations `[0.229, 0.224, 0.225]`.
- Input limits remain JPEG/PNG, bounded bytes/dimensions/single frame. The pretrained
  extractor additionally rejects aspect ratios above 8:1 to bound resize memory.
- CPUExecutionProvider, sequential execution, one intra/inter-op thread; batches of
  at most 8. Runtime telemetry disabled. No runtime network downloads.

Two independent exports produced identical bytes. A generated rectangular image compared
against timm's upstream preprocessing/PyTorch representation differed by at most
**7.87e-6** per activation (tolerance 1e-4). This validates conversion/preprocessing on
that synthetic fixture; it is not an accuracy measurement. Cross-hardware floating-point
bit identity is not promised. Runtime versions, preprocessing and checksums are pinned;
container recreation is separately regression-tested on the cloud CPU.

## Training, comparison and compatibility

The website's **Visual feature extractor** selector defaults to the existing baseline.
MobileNet becomes selectable when its exact graph is installed. `GET
/api/v1/research/preferences/extractors` returns authenticated availability and provenance;
there is no browser weight endpoint. Unknown IDs and missing/corrupt graphs fail closed.

New MobileNet jobs use the existing durable CPU research queue, immutable annotation
snapshot, ownership checks, cancellation/leases, private checkpoints, version allocation,
retraining, archive/delete and source-retention behavior. Embeddings are cached separately
by image and immutable extractor ID, checked against source SHA and finite dimensions.
The worker decodes/processes at most eight uncached images per pretrained batch. Cached
retraining reuses both the MobileNet and baseline descriptors. Prediction also caches the
selected image descriptor, with normal ownership/source validation and graph verification.

Every MobileNet training job fits two genuine ridge models: MobileNet features and the
original handcrafted features. The same snapshot, identity-grouped split, seed, alpha,
training-only normalization and held-out images are used for both. The training-mean
predictor uses only training ratings. Display MAE and RMSE for all three are shown in the
website. The saved model is the selected extractor's training-split model; held-out labels
are never fitted or included in normalization. The comparison baseline is evaluated
inside the job, not published as an extra model version. Existing handcrafted versions
remain independently selectable.

Pretrained rating checkpoints use JSON format `auvylen-rating-ridge-v2` and include the
full immutable representation manifest plus coefficients, fitted normalization, rating
bounds and snapshot SHA. The loader checks the exact manifest and graph hash. Legacy
`auvylen-rating-ridge-v1` remains accepted with its original fixed 230-feature schema.
A golden regression derived from commit `b37d2b8` verifies identical legacy checkpoint
bytes and raw prediction. Older stored metrics are not fabricated or backfilled.

No schema migration is required: existing version/configuration/metrics/embedding tables
already support these additions. No old checkpoint, annotation, job, model version or
Phase 4A table is rewritten. GitHub scoring plugin availability/configuration has no
influence on this first-party extractor.

## Operator installation on the approved cloud host

The production API/worker installs only the locked CPU runtime. Keep export tooling in a
separate ignored environment; never install CUDA wheels or place these weights in Git or
Docker image layers. Allow approximately 1 GiB for export tooling plus package caches and
normal build headroom; the runtime graph itself is approximately 5.8 MiB.

```sh
uv venv .venv-extractor-export --python 3.14
uv pip install --python .venv-extractor-export/bin/python --index-url https://download.pytorch.org/whl/cpu 'torch==2.10.0+cpu' 'torchvision==0.25.0+cpu'
uv pip install --python .venv-extractor-export/bin/python 'timm==1.0.30' 'onnx==1.22.0' 'numpy==2.5.4'
OPENBLAS_NUM_THREADS=1 .venv-extractor-export/bin/python scripts/export-pretrained-extractor.py --download --output private-data/exports/mobilenetv3-small-100-lamb-embedding-v1.onnx
uv run python scripts/install-pretrained-extractor.py --source-file private-data/exports/mobilenetv3-small-100-lamb-embedding-v1.onnx --root private-data/models/pretrained
```

Set host `PRIVATE_MODEL_ROOT` to the parent `private-data/models`. For the existing
Compose stack, install the verified graph and accompanying license/notice under
`/var/lib/auvylen/models/pretrained` in the existing private model volume, owned by UID
10001, mode 600 files and mode 700 directory. API mounts that volume read-only; workers
retain their existing private write access; web/proxy have no mount. Compose `cp` preserves source ownership here, and the hardened containers drop all
capabilities: even `exec --user root` cannot traverse a 700 directory owned by UID 10001.
A trusted operator can copy the prepared bundle, then use a one-off **network-disabled**
helper mounted only to the identified private model volume with `--user 0:0 --read-only
--cap-drop ALL --cap-add DAC_OVERRIDE --cap-add CHOWN --cap-add FOWNER`. Set ownership
and modes only on `pretrained` and its three known graph/license/notice files. Remove the
helper with `--rm`; retain the normal application capability restrictions. Alternatively,
stream the verified files to a process running as UID 10001. Do not relax normal app
permissions or recursively change the rest of the private volume. Always verify its hash
inside the worker before using the website. Runtime loading never invokes PyTorch pickle.

The exporter verifies source and output hashes and refuses to overwrite existing files.
The installer also refuses replacement and retains license/notice files. Back up the
pretrained graph/license bundle together with versioned personal checkpoints, PostgreSQL
metadata/annotations and private uploads using the existing backup strategy. Losing the
pretrained bundle makes its versions unavailable until exactly those bytes are restored;
legacy handcrafted models continue to work. Essential data needs an approved persistent
host and backup, not sole storage in an ephemeral workspace.

## Evaluation and limitations

See [measured results](phase4b-representation-report.md), [synthetic measurements](evaluation/)
and the [adult-face evaluation workflow](evaluation/adult-face-workflow.md). The model was
pretrained for general objects, not faces, identity, age or attractiveness. Lighting,
background, crop and image quality can dominate; a center crop can cut off a face. There
is no new face detector or automatic identity grouping. Unknown person IDs can leak
identity across splits. Eight ratings is an operational minimum, not statistical support.

Synthetic labels/fixtures verify software correctness and capacity. They do not establish
improved facial preference accuracy. Real evaluation requires separately authorized adult
photographs and an approved retention strategy. Pairwise ranking, confidence intervals,
external test cohorts and independent GitHub scoring integrations remain future work.

The 500-image quota counts **all owner images**, including unrated prediction inputs.
Reserve spare image slots for unseen predictions; 500 rated images already fill the
account quota. The 1,000-image experiment measures extractor scaling only and does not
approve a higher service limit. Full-size image ingestion, concurrent users, DB JSON
embedding growth, backups and cleanup need further capacity testing before any increase.
