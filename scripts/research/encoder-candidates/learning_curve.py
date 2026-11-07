"""Dev-only learning curve: MobileNet-A trained on subsets of each outer training fold."""

import json
import os
from pathlib import Path

import numpy as np
from aevyra_inference.native import metrics
from aevyra_inference.native_dev_study import checked_development_rows, protocol_a
from aevyra_inference.native_selection import grouped_folds

out = Path("private-data/encoder-study")

rows = checked_development_rows(
    out / "development.csv", Path(os.environ["AUVYLEN_LONDON_REGISTRY"])
)
y = np.asarray([float(r["rating"]) for r in rows])
subjects = [r["subject_id"] for r in rows]
f = dict(np.load(out / "mobilenetv3_small_100.lamb_in1k.npz"))
rng = np.random.default_rng(20261107)
curve = {}
for size in (16, 24, 32, 48, 64):
    maes, base, rhos = [], [], []
    for repeat in range(5):
        for train, held in grouped_folds(subjects, 5, seed=42 + 1000 + repeat):
            for _ in range(4):
                pick = np.sort(rng.choice(train, size=min(size, len(train)), replace=False))
                views = np.stack([f["lighting"][pick], f["crop"][pick]])
                head, _ = protocol_a(
                    f["clean"][pick], views, y[pick], [subjects[i] for i in pick], 42, 7.0
                )
                m = metrics(head.predict(f["clean"][held]), y[held])
                maes.append(m["mae"])
                rhos.append(m["spearman"])
                base.append(np.abs(y[held] - y[pick].mean()).mean())
                if size >= len(train):
                    break
    curve[size] = {
        "mae": float(np.mean(maes)),
        "train_mean_mae": float(np.mean(base)),
        "gain_vs_mean": float(np.mean(base) - np.mean(maes)),
        "spearman": float(np.nanmean(rhos)),
    }
    print(size, {k: round(v, 3) for k, v in curve[size].items()})
json.dump(
    {
        "policy": (
            "development subjects only; held-out folds never subsampled; one portrait per subject"
        ),
        "curve": curve,
    },
    open("private-data/learning-curve.json", "w"),
    indent=2,
)
