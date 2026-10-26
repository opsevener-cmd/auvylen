"""Create a SYNTHETIC aesthetic checkpoint for automated browser tests only.

Trained on generated vectors and sampled vote counts; it says nothing about real photographs.
The API accepts it only with AESTHETIC_ALLOW_SYNTHETIC_TEST_CHECKPOINT=true, which settings
forbid in staging/production. Prints shell assignments for the pinned version and checksum.
"""

import argparse
from pathlib import Path

import numpy as np
from aevyra_inference.aesthetic import fit_scoring_head
from aevyra_inference.aesthetic_checkpoint import DatasetEvidence, write_checkpoint
from aevyra_inference.extractors import BASELINE, dimension

VERSION = "synthetic-e2e-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-root", type=Path, required=True)
    args = parser.parse_args()
    rng = np.random.default_rng(1)
    d = dimension(BASELINE)
    direction = rng.normal(0, 1, d)
    rows, votes, ids = [], [], []
    for subject in range(200):
        base = rng.normal(0, 1, d)
        for _ in range(3):
            x = base + rng.normal(0, 0.3, d)
            quality = float(x @ direction) / np.linalg.norm(direction)
            logits = -0.8 * (np.arange(1, 6) - (3 + 1.2 * quality)) ** 2
            p = np.exp(logits - logits.max())
            votes.append(rng.multinomial(25, p / p.sum()))
            rows.append(x)
            ids.append(f"generated-{subject}")
    head, metrics = fit_scoring_head(np.asarray(rows), np.asarray(votes, dtype=float), ids)
    _, sha = write_checkpoint(
        args.model_root,
        head,
        model_version=VERSION,
        extractor=BASELINE,
        dataset=DatasetEvidence(
            name="Generated synthetic fixture (browser tests)",
            license="Test-only generated data",
            terms_url="https://example.invalid/test-only",
            authorization_reference="TEST-ONLY",
            reviewer="automated test",
            annotator_population="simulated raters",
            adult_subjects_confirmed=True,
            rating_scale="five ordered categories, 1 (lowest) to 5 (highest)",
            synthetic=True,
        ),
        training={"seed": 42, "purpose": "automated browser test"},
        metrics=metrics,
    )
    print(f"E2E_AESTHETIC_VERSION={VERSION}")
    print(f"E2E_AESTHETIC_SHA256={sha}")


if __name__ == "__main__":
    main()
