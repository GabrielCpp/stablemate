"""Optional nicety: crop region bboxes out of the screenshot as small PNGs — `unlabeled` residuals for a downstream VLM step, and each *matched* documented component's visual snippet."""

from __future__ import annotations

import io
from pathlib import Path

from ostler.vet.regions import RegionBox


def maybe_crop(screenshot: Path, regions: list[RegionBox]) -> dict[int, bytes]:
    """Return {index into *regions*: PNG bytes} for every region actually cropped."""
    try:
        from PIL import Image
    except ImportError:
        return {}
    if not screenshot.is_file():
        return {}

    crops: dict[int, bytes] = {}
    try:
        with Image.open(screenshot) as img:
            for i, region in enumerate(regions):
                b = region.bbox
                box = (int(b.x), int(b.y), int(b.x + b.width), int(b.y + b.height))
                buf = io.BytesIO()
                img.crop(box).save(buf, format="PNG")
                crops[i] = buf.getvalue()
    except OSError:
        return crops
    return crops
