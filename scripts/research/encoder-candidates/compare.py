"""Dev-only paired grouped CV over precomputed development-image embeddings."""

import csv
import json
from pathlib import Path

import numpy as np
from aevyra_inference.native import metrics
from aevyra_inference.native_dev_study import paired_bootstrap, protocol_a, protocol_b
from aevyra_inference.native_selection import grouped_folds

out = Path("private-data/encoder-study")
rows = list(csv.DictReader(open(out / "development.csv")))
assert [r["image"] for r in rows] == json.load(open(out / "development-images.json"))
y = np.asarray([float(r["rating"]) for r in rows])
subjects = [r["subject_id"] for r in rows]
encoders = json.load(open(out / "encoders.json"))
feats = {n: dict(np.load(out / f"{n}.npz")) for n in encoders}
variants = {}
for n in encoders:
    short = n.split(".")[0]
    variants[short + "-A"] = (protocol_a, feats[n])
    variants[short + "-B"] = (protocol_b, feats[n])
runs = {k: [] for k in [*variants, "train-mean"]}
for repeat in range(5):
    pred = {k: np.empty(len(y)) for k in runs}
    for train, held in grouped_folds(subjects, 5, seed=42 + 1000 + repeat):
        inner = [subjects[i] for i in train]
        for k, (protocol, f) in variants.items():
            views = np.stack([f["lighting"][train], f["crop"][train]])
            head, _ = protocol(f["clean"][train], views, y[train], inner, 42, 7.0)
            pred[k][held] = head.predict(f["clean"][held])
        pred["train-mean"][held] = y[train].mean()
    for k in runs:
        runs[k].append(pred[k])
err = {k: np.mean([np.abs(p - y) for p in v], axis=0) for k, v in runs.items()}
summary = {}
for k, v in runs.items():
    s = [metrics(p, y) for p in v]
    summary[k] = {
        "mae": float(np.mean([x["mae"] for x in s])),
        "rmse": float(np.mean([x["rmse"] for x in s])),
        "spearman": None if k == "train-mean" else float(np.mean([x["spearman"] for x in s])),
    }
ref = "mobilenetv3_small_100-A"
result = {
    "policy": (
        "development subjects only (80); sealed seed-42 test subjects excluded before "
        "ratings were parsed; timm preprocessing for every encoder"
    ),
    "encoders": encoders,
    "variants": summary,
    "paired_mae_vs_train_mean": {
        k: paired_bootstrap(err["train-mean"], err[k], subjects, 2000, 20261107) for k in variants
    },
    f"paired_mae_vs_{ref}": {
        k: paired_bootstrap(err[ref], err[k], subjects, 2000, 20261107)
        for k in variants
        if k != ref
    },
}
json.dump(result, open("private-data/encoder-study-result.json", "w"), indent=2)
print(f"{'variant':28s} {'MAE':>6s} {'RMSE':>6s} {'rho':>6s} | vs small-A: diff [interval] share")
for k, v in summary.items():
    p = result[f"paired_mae_vs_{ref}"].get(k)
    extra = (
        ""
        if p is None
        else f"{p['mean']:+.3f} [{p['low']:+.3f},{p['high']:+.3f}] "
        f"{p['share_of_draws_favouring_b']:.2f}"
    )
    rho = "  n/a " if v["spearman"] is None else f"{v['spearman']:6.3f}"
    print(f"{k:28s} {v['mae']:6.3f} {v['rmse']:6.3f} {rho} | {extra}")
