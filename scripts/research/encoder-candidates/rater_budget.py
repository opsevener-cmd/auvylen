"""Dev-only: how many raters per portrait does a study need? London development faces only.

London raters each rated every face, so k-rater averages can be compared with the
consensus of all adult raters. Only the 80 development subjects are read (the sealed
seed-42 test subjects are excluded by the development table). Aggregate output only.
"""

import csv
import json
import sys
from pathlib import Path

import numpy as np
from aevyra_inference.native_dev_study import checked_development_rows

root, study = Path(sys.argv[1]), Path(sys.argv[2])
development = [
    r["image"]
    for r in checked_development_rows(study / "development.csv", root / "subject-metadata.json")
]
columns = ["X" + name.split("_")[0] for name in development]
with open(root / "source-ratings.csv", newline="") as file:
    raters = [r for r in csv.DictReader(file) if 18 <= float(r["rater_age"] or 0) <= 120]
scores = np.asarray(
    [[float(r[c]) if r[c] not in ("", "NA") else np.nan for c in columns] for r in raters]
)
consensus = np.nanmean(scores, axis=0)
rng = np.random.default_rng(20261107)
# One-way variance decomposition (each face is rated by every rater in this design).
counts = np.isfinite(scores).sum(axis=0)
within = float(np.mean(np.nanvar(scores, axis=0, ddof=1)))
between = float(np.var(consensus, ddof=1) - np.mean(np.nanvar(scores, axis=0, ddof=1) / counts))
rho = between / (between + within)
needed = {str(t): int(np.ceil(t * (1 - rho) / (rho * (1 - t)))) for t in (0.7, 0.8, 0.9)}
agreement = {"single_rater_icc": rho, "raters_needed_for_reliability": needed}
budget = {}
for k in (3, 5, 8, 12, 20, 30):
    rs, maes = [], []
    for _ in range(200):
        means = []
        for j in range(len(columns)):
            pool = np.flatnonzero(np.isfinite(scores[:, j]))
            means.append(scores[rng.choice(pool, k, replace=False), j].mean())
        means = np.asarray(means)
        rs.append(np.corrcoef(means, consensus)[0, 1])
        maes.append(np.abs(means - consensus).mean())
    budget[k] = {
        "r_with_consensus": float(np.mean(rs)),
        "label_mae_vs_consensus": float(np.mean(maes)),
    }
print(
    json.dumps(
        {
            "policy": "80 development faces only; adult raters; sealed test faces never read",
            "adult_raters": len(raters),
            "agreement": agreement,
            "k_rater_labels": budget,
        },
        indent=2,
    )
)
