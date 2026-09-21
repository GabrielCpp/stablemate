"""IoU-based greedy registration between the expected manifest and the auto-derived regions."""

from __future__ import annotations

from pydantic import BaseModel

from ostler.vet.geometry import iou
from ostler.vet.manifest import DomElement
from ostler.vet.regions import RegionBox


class MatchedPair(BaseModel):
    dom: DomElement
    region: RegionBox
    iou: float
    crop: str | None = None


class MatchResult(BaseModel):
    matched: list[MatchedPair]
    missing: list[DomElement]
    unexpected: list[RegionBox]
    unlabeled: list[RegionBox]


def match(elements: list[DomElement], regions: list[RegionBox], *,
          iou_threshold: float = 0.5) -> MatchResult:
    """Greedy match sorted by (-iou, i, j) for determinism, regardless of input order."""
    candidates = [e for e in elements if e.visible]
    pairs: list[tuple[float, int, int]] = []
    for i, dom in enumerate(candidates):
        for j, region in enumerate(regions):
            score = iou(dom.bbox, region.bbox)
            if score >= iou_threshold:
                pairs.append((score, i, j))
    pairs.sort(key=lambda p: (-p[0], p[1], p[2]))

    matched_dom: set[int] = set()
    matched_region: set[int] = set()
    matched: list[MatchedPair] = []
    for score, i, j in pairs:
        if i in matched_dom or j in matched_region:
            continue
        matched_dom.add(i)
        matched_region.add(j)
        matched.append(MatchedPair(dom=candidates[i], region=regions[j], iou=score))

    missing = [dom for i, dom in enumerate(candidates) if i not in matched_dom]
    unexpected: list[RegionBox] = []
    unlabeled: list[RegionBox] = []
    for j, region in enumerate(regions):
        if j in matched_region:
            continue
        if region.role is None:
            unlabeled.append(region)
        else:
            unexpected.append(region)

    return MatchResult(matched=matched, missing=missing,
                       unexpected=unexpected, unlabeled=unlabeled)
