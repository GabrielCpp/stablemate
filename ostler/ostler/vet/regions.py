"""Merge scanned DOM elements into labeled regions — the deterministic replacement for
classical-CV pixel segmentation. Both sides of a merge are exact `getBoundingClientRect`
geometry, so "segmentation" is just grouping-by-identical-rect, not a probabilistic guess.
"""

from __future__ import annotations

from pydantic import BaseModel, TypeAdapter

from ostler.vet.cdp import ScannedElement
from ostler.vet.geometry import BBox


class RegionBox(BaseModel):
    bbox: BBox
    role: str | None
    selectors: list[str]
    crop: str | None = None  # set by crop.maybe_crop() for an `unlabeled` finding, else unused


RegionList: TypeAdapter[list[RegionBox]] = TypeAdapter(list[RegionBox])


def _rect_key(bbox: BBox, rect_epsilon: float) -> tuple[float, float, float, float]:
    return (
        round(bbox.x / rect_epsilon),
        round(bbox.y / rect_epsilon),
        round(bbox.width / rect_epsilon),
        round(bbox.height / rect_epsilon),
    )


def merge(elements: list[ScannedElement], *, rect_epsilon: float = 1.0) -> list[RegionBox]:
    """Group elements sharing a (near-)identical rect (rounded to *rect_epsilon* px) into one
    region. A region's role is the first non-empty role among its members, else ``None``
    ("unlabeled") — a deliberately limited fallback, not a heuristic guess."""
    groups: dict[tuple[float, float, float, float], list[ScannedElement]] = {}
    order: list[tuple[float, float, float, float]] = []
    for el in elements:
        key = _rect_key(el.bbox, rect_epsilon)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(el)

    regions: list[RegionBox] = []
    for key in order:
        members = groups[key]
        role = next((m.role for m in members if m.role), None)
        regions.append(RegionBox(
            bbox=members[0].bbox,
            role=role,
            selectors=[m.selector for m in members],
        ))
    return regions
