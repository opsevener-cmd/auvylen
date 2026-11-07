"""Input check: does an image resemble the portraits a native head was trained on?

A ridge head returns a number for any input, including noise, a blank wall or a tiny face
in a large frame. This check measures how far an image's encoder features lie from the
training portraits, using the head's own pinned training standardization:

    distance = sqrt(mean(((features - train_mean) / train_scale) ** 2))

Thresholds come from the training split only and are stored in the manifest report, so
they are covered by the checkpoint's SHA-256 pin. Nothing here uses validation or test
labels. It is a coarse guard against clearly wrong inputs, not a face detector, an age
or identity check, or evidence that a typical-looking input will be predicted accurately.
"""

from typing import Any, Literal

import numpy as np

from aevyra_inference.native import Array, NativeHead

Verdict = Literal["typical", "unusual", "outside", "unchecked"]
STATISTIC = "rms-standardized-feature-distance-v1"
# Development calibration (MobileNet, London training split): portraits <= 1.69; rotated
# portraits 1.9–2.4; background crops, tiny faces, noise and flat colour >= 3.4.
CAUTION_MARGIN = 1.1  # x the largest training distance
OUTSIDE_FACTOR = 3.0  # x the median training distance


def distance(head: NativeHead, features: Array) -> Array:
    z = (np.asarray(features, dtype=np.float64) - head.mean) / head.scale
    return np.asarray(np.sqrt((z**2).mean(axis=1)), dtype=np.float64)


def profile(head: NativeHead, train_features: Array) -> dict[str, Any]:
    values = distance(head, train_features)
    if len(values) < 5 or not np.isfinite(values).all():
        raise ValueError("Input profile needs at least five finite training portraits")
    caution = float(values.max() * CAUTION_MARGIN)
    outside = float(max(np.median(values) * OUTSIDE_FACTOR, caution * 1.25))
    return {
        "statistic": STATISTIC,
        "fitted_on": "training portraits only (clean, no augmentation)",
        "training_images": int(len(values)),
        "training_median": float(np.median(values)),
        "training_max": float(values.max()),
        "caution_above": caution,
        "outside_above": outside,
    }


def verdict(value: float, input_profile: dict[str, Any] | None) -> Verdict:
    if not input_profile or input_profile.get("statistic") != STATISTIC:
        return "unchecked"
    if not np.isfinite(value) or value > input_profile["outside_above"]:
        return "outside"
    return "unusual" if value > input_profile["caution_above"] else "typical"
