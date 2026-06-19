"""Exercise the blind global pass on a few images and print the raw records.

Run from the `code/` directory:

    python -m stage1.run_blind_pass

Optionally pass image paths (relative to repo root or absolute):

    python -m stage1.run_blind_pass dataset/images/sample/case_001/img_1.jpg
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import config, devlog
from .vision import _repo_root, see_image
from .providers import VisionError

# case_025 lives under test/ (sample/ only has cases 001–020); case_001 single
# image is taken from sample/.
DEFAULT_IMAGES = [
    "dataset/images/sample/case_001/img_1.jpg",   # single
    "dataset/images/test/case_025/img_1.jpg",     # multi (1 of 2)
    "dataset/images/test/case_025/img_2.jpg",     # multi (2 of 2)
]


def main(argv: list[str]) -> int:
    root = _repo_root()
    rels = argv or DEFAULT_IMAGES
    paths = [Path(r) if Path(r).is_absolute() else root / r for r in rels]

    provider, model = config.vision_provider(), config.vision_model()
    print(f"provider={provider}  model={model}\n", file=sys.stderr)
    devlog.append(
        "Stage 1 blind pass run",
        f"provider={provider} model={model}\nImages: " + ", ".join(rels),
    )

    records = []
    for p in paths:
        try:
            rec = see_image(p)
            records.append(rec.to_dict())
            print(json.dumps(rec.to_dict(), ensure_ascii=False, indent=2))
            print()
        except VisionError as e:
            print(f"[FAILED] {p}: {e}", file=sys.stderr)
            return 1

    devlog.append(
        "Stage 1 blind pass done",
        f"Emitted {len(records)} record(s).",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
