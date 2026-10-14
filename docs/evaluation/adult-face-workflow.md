# Authorized adult-face evaluation protocol

No facial dataset has been downloaded or authorized for this cloud workspace. The
synthetic benchmarks in this milestone measure correctness and resources only.
This preparation does not authorize retaining personal photographs in temporary cloud.

## Before obtaining images

An operator and the user must review the actual dataset access terms, photograph rights,
research-purpose restrictions, subject ages and permission for automated subjective
rating research. Public availability is insufficient. Possible candidates for review
include the Face Research Lab London Set and Chicago Face Database; neither is approved
by this document. Do not download access-restricted datasets or bypass registration.
Exclude minors and uncertain ages. A face/age detector is not consent or age evidence.

Copy `adult-face-plan.example.json` into protected, ignored private storage. Record the
actual terms URL, authorization reference, reviewer, complete subject identifiers and
approved deletion date. Record the approved host, access controls, backup location,
backup expiry and how deletions reach backups. Keep access credentials and identifying
information out of Git and logs. Temporary cloud retention requires **explicit user
approval of that location and retention plan**, beyond routine website consent.

Run `uv run python scripts/validate-face-evaluation-plan.py PRIVATE_PLAN.json`. The
example intentionally fails. The validator checks required evidence fields, adult-only
confirmation, subject grouping, 500-image limit, retention bounds and fixed evaluation
configuration; passing does not independently establish legal rights or user approval.
No download/import side effect exists. Obtain actual approval before using the existing
website upload flow. Do not add dataset download credentials to the application.

## Fixed comparison protocol

1. Start with one approved dataset of independent adults, up to the existing 500-image
   account limit. Record acquisition conditions/crops. Assign every photograph of a
   person the same pseudonymous subject ID before any training. Check exact duplicates
   and manually review near-duplicate/person grouping errors. No automatic identity
   recognition is implemented.
2. The user supplies numerical ratings independently, without seeing model predictions.
   Pairwise annotations remain distinct. Record the rating scale, missingness and
   exclusions; do not relabel images to improve a metric.
3. Freeze that eligible dataset and use seed 42, held-out group fraction 0.2 and alpha 10.
   Train the MobileNet version in the website. Its job also fits the original handcrafted
   baseline using the **same immutable annotation snapshot, same identity groups,
   same training/validation indices and alpha**. Both models fit feature normalization
   only on training images. The mean predictor uses only training ratings.
4. Record version ID, snapshot digest (operator-only DB record), extractor manifest,
   weight checksum, known/unknown identity counts, held-out image/group counts,
   clipped MAE/RMSE and mean/baseline errors. A deleted source invalidates its models;
   keep only permitted aggregate results after deletion. Do not publish photographs,
   group IDs, snapshots or checkpoints as part of a research report.
5. Compare paired errors over held-out people, not just a single aggregate mean. A later
   study should add subject-level bootstrap confidence intervals and repeat across
   preregistered seeds. Neither confidence intervals nor demographic subgroup fairness
   estimates are implemented in the website in this milestone. Low counts preclude
   reliable subgroup conclusions. Do not infer demographic attributes from faces.
6. Repeatedly tuning against one holdout biases its estimate. Further tuning needs a
   separate development split and untouched external test people. Retraining with more
   annotations creates a new snapshot and is not automatically an apples-to-apples
   accuracy comparison with an older version. Do not pool independently rated users as
   one objective attractiveness truth.
7. Report negative results and limitations: general ImageNet features, center-crop loss,
   backgrounds/lighting, selection bias, annotation consistency, identity uncertainty,
   small holdouts and drift. No population percentiles or objective beauty claims.

## Retention and completion

The existing authenticated private upload, expiry and deletion workflow remains required.
Before real import, verify source deletion blocks predictions immediately and the worker
physically removes images, embeddings, copied snapshots and derived checkpoints. Keep
workers running until cleanup completes. Verify backups obey the approved retention and
propagate deletion according to that plan. Temporary cloud is not an essential-data backup.
Do not commit photographs, model artifacts, individual ratings or private plans to Git.
