"""Merge scanned DOM elements into labeled regions — the deterministic replacement for
classical-CV pixel segmentation. Both sides of a merge are exact `getBoundingClientRect`
geometry, so "segmentation" is just grouping-by-identical-rect, not a probabilistic guess.
"""

from __future__ import annotations

from pydantic import BaseModel, TypeAdapter

from ostler.qa.harness_host import load_harness_module
from ostler.vet.geometry import BBox

_merge_rects = load_harness_module("ostler_qa_scan").merge_rects


class ScannedElement(BaseModel):
    """One element as the scan reports it — the input side of a merge.

    It lives here rather than beside the CDP connection that produces it because a scan also
    arrives from a QA scenario that ran the same JS itself, and the live-browser module
    imports the QA harness host. Keeping the model next to the merge that consumes it is what
    keeps `ostler.vet` importable from inside `ostler.qa` rather than in a circle with it.
    """

    selector: str
    bbox: BBox
    role: str = ""
    tag: str = ""


class RegionBox(BaseModel):
    bbox: BBox
    role: str | None
    selectors: list[str]
    crop: str | None = None  # set by crop.maybe_crop() for an `unlabeled` finding, else unused


RegionList: TypeAdapter[list[RegionBox]] = TypeAdapter(list[RegionBox])


def merge(elements: list[ScannedElement], *, rect_epsilon: float = 1.0) -> list[RegionBox]:
    """Group elements sharing a (near-)identical rect (rounded to *rect_epsilon* px) into one
    region. A region's role is the first non-empty role among its members, else ``None``
    ("unlabeled") — a deliberately limited fallback, not a heuristic guess.

    The grouping itself is the harness's, so a region a QA scenario recorded and a region
    `vet` computed are the same region; this side only puts the models back on."""
    merged = _merge_rects(
        [element.model_dump(mode="json") for element in elements], rect_epsilon=rect_epsilon
    )
    return [RegionBox.model_validate(region) for region in merged]
