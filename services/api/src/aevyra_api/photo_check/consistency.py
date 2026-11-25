"""Run one photo through the photo check several times and report how stable it is.

Operator tool, run inside the API container with the deployed settings. The photo is read
from standard input and never written anywhere:

    dc exec -T api python -m aevyra_api.photo_check.consistency --runs 5 < my-photo.jpg

It prints only numbers: each run's technique score, whether it passed the quality gate, its
band (shown to users only when the gate passes) and the six scores; then the gate
agreement, the band agreement among runs that passed, and the spread of every score.
Each run is a real paid Gemini call (about $0.002 for one photo); the spend is added to
today's budget so the daily cap stays accurate.
"""

import argparse
import sys
from collections import Counter

from aevyra_contracts.photo_check import QUALITY_GATE

from aevyra_api.config import Settings
from aevyra_api.database import DependencyChecks
from aevyra_api.photo_check.gemini import ProviderError
from aevyra_api.photo_check.service import (
    PhotoCheckService,
    gemini_provider,
    passes_quality_gate,
    prepare_photo,
)

CRITERIA = ("lighting", "sharpness", "framing", "expression", "eye_contact", "background")


def summarize(runs: list[dict[str, object]]) -> list[str]:
    """Report lines for a list of per-run results (band and scores, or a refusal).

    Each run shows its technique score and whether it passed the quality gate; band
    agreement counts only runs that passed, because only those ever show a band.
    """
    lines = []
    passed_runs = []
    for number, run in enumerate(runs, start=1):
        if run.get("refusal"):
            lines.append(f"run {number}: no result ({run['refusal']}), gate=failed")
            continue
        quality = sum(int(str(run[name])) for name in CRITERIA) / len(CRITERIA)
        passed = passes_quality_gate(quality)
        if passed:
            passed_runs.append(run)
        scores = " ".join(f"{name}={run[name]}" for name in CRITERIA)
        lines.append(
            f"run {number}: quality {quality:.1f} gate={'passed' if passed else 'failed'} "
            f"band={run['band'] if passed else '-'} {scores}"
        )
    passes = len(passed_runs)
    majority = max(passes, len(runs) - passes)
    lines.append(
        f"quality gate agreement: {majority}/{len(runs)} runs "
        f"{'passed' if passes >= len(runs) - passes else 'failed'} "
        f"({round(100 * majority / len(runs))}%; gate is {QUALITY_GATE:.1f}/10)"
    )
    if passed_runs:
        band, count = Counter(run["band"] for run in passed_runs).most_common(1)[0]
        lines.append(
            f"band agreement (runs that passed the gate): {count}/{passes} gave band {band} "
            f"({round(100 * count / passes)}%)"
        )
    else:
        lines.append("band agreement: no run passed the quality gate, so no band is shown")
    scored = [run for run in runs if not run.get("refusal")]
    for name in CRITERIA if scored else ():
        values = [int(str(run[name])) for run in scored]
        lines.append(
            f"{name}: min {min(values)}, max {max(values)}, spread {max(values) - min(values)}"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=5, choices=range(2, 11))
    parser.add_argument("--language", choices=["en", "zh-CN"], default="en")
    args = parser.parse_args()
    if sys.stdin.isatty():
        print("Pipe a JPEG or PNG on standard input: ... consistency < photo.jpg", file=sys.stderr)
        return 2
    settings = Settings()
    checks = DependencyChecks(settings)
    service = PhotoCheckService(checks.sessions, settings)
    reason = service.configuration()
    if reason != "ready":
        print(f"Photo check is not ready: {reason}", file=sys.stderr)
        return 1
    photo = prepare_photo(sys.stdin.buffer.read())
    provider = gemini_provider(settings)
    runs: list[dict[str, object]] = []
    spent = 0
    for _ in range(args.runs):
        try:
            assessment = provider.assess([photo], args.language)
        except ProviderError as error:
            print(f"Gemini call failed: {error.reason} (HTTP {error.status_code})", file=sys.stderr)
            if error.usage:
                spent += service.record_spend(error.usage)
            return 1
        spent += service.record_spend(assessment.usage)
        result = assessment.photos[0]
        if result.refusal_reason:
            runs.append({"refusal": result.refusal_reason})
        else:
            runs.append({"band": result.band, **{name: getattr(result, name) for name in CRITERIA}})
    print("\n".join(summarize(runs)))
    print(f"cost: ${spent / 1_000_000:.4f} (added to today's photo check budget)")
    checks.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
