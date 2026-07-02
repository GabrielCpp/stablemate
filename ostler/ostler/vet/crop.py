"""Optional nicety: crop `unlabeled` bboxes out of the screenshot for a downstream VLM step.

`Pillow` is imported lazily and this degrades cleanly (no crop, just bbox + screenshot path)
when it isn't installed — the only place an image library is ever touched, and it's optional.

Crops are returned as in-memory PNG bytes, never written directly: `ostler vet` is dry-run by
default, so the caller bundles them into the returned `VetPlan` and only `plan.apply()` touches
disk, same as every other write this command makes.
"""

from __future__ import annotations

import io
from pathlib import Path

from .regions import RegionBox


def maybe_crop(screenshot: Path, unlabeled: list[RegionBox]) -> dict[int, bytes]:
    """Return {index into *unlabeled*: PNG bytes} for every region actually cropped."""
    try:
        from PIL import Image
    except ImportError:
        return {}
    if not screenshot.is_file():
        return {}

    crops: dict[int, bytes] = {}
    try:
        with Image.open(screenshot) as img:
            for i, region in enumerate(unlabeled):
                b = region.bbox
                box = (int(b.x), int(b.y), int(b.x + b.width), int(b.y + b.height))
                buf = io.BytesIO()
                img.crop(box).save(buf, format="PNG")
                crops[i] = buf.getvalue()
    except OSError:
        return crops
    return crops
