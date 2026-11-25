"""``python -m auvylen7b --source synthetic|london --store DIR --work DIR``.

Stages are idempotent and content-addressed: rerunning after a Colab disconnect resumes
from the last finished shard. ``london`` requires the Owner-confirmed rights/storage note.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from auvylen7b import data
from auvylen7b.encoders import ENCODERS, embed
from auvylen7b.evaluate import evaluate
from auvylen7b.store import Store

DEFAULT = ["mobilenetv3-small", "dinov2-small", "dinov2-base", "siglip-base", "clip-b16"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["synthetic", "london"], required=True)
    parser.add_argument("--store", type=Path, required=True, help="Persistent (Drive) directory")
    parser.add_argument("--work", type=Path, required=True, help="Ephemeral local directory")
    parser.add_argument("--encoder", action="append", choices=sorted(ENCODERS))
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--confirm-london-rights", action="store_true")
    args = parser.parse_args()
    if args.source == "london" and not args.confirm_london_rights:
        print("London requires --confirm-london-rights (Owner-confirmed note)", file=sys.stderr)
        return 2
    store = Store(args.store / args.source)
    dataset = data.london(args.work) if args.source == "london" else data.synthetic(args.work)
    encoders = args.encoder or DEFAULT
    if "mobilenetv3-small" not in encoders:
        encoders = ["mobilenetv3-small", *encoders]
    shards = embed(store, dataset, encoders, device=args.device)
    result = evaluate(store, dataset, shards, encoders)
    print(
        json.dumps(
            {k: result[k] for k in ("dataset", "synthetic", "subjects", "decision", "promotable")},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
