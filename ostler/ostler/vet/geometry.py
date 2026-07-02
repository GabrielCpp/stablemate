"""Pure geometry: the exact-rect model both sides of `ostler vet` share, and IoU registration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BBox(BaseModel):
    model_config = ConfigDict(frozen=True)

    x: float
    y: float
    width: float
    height: float

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return max(self.width, 0.0) * max(self.height, 0.0)


def iou(a: BBox, b: BBox) -> float:
    """Intersection-over-union of two boxes; 0 for no overlap or zero-area boxes."""
    ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    intersection = iw * ih
    union = a.area + b.area - intersection
    if union <= 0:
        return 0.0
    return intersection / union
