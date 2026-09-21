"""Merge scanned DOM elements into labeled regions — the deterministic replacement for classical-CV pixel segmentation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ostler.qa.harness_host import load_harness_module
from ostler.vet.geometry import BBox

_merge_rects = load_harness_module("ostler_qa_scan").merge_rects


class ScannedElement(BaseModel):
    """One element as the scan reports it — the input side of a merge."""

    selector: str
    bbox: BBox
    role: str = ""
    own_role: str = Field(default="", alias="ownRole")
    name: str = ""
    tag: str = ""

    model_config = ConfigDict(populate_by_name=True)


class RegionBox(BaseModel):
    bbox: BBox
    role: str | None
    selectors: list[str]
    own_roles: list[str] = []
    names: list[str] = []
    crop: str | None = None

    def observed(self, selector_index: int) -> tuple[str, str] | None:
        """The (own role, accessible name) recorded for one of this region's selectors, or `None` when this scan recorded none — the absence, kept distinguishable from a name that was observed to be empty."""
        if selector_index >= len(self.names) or selector_index >= len(self.own_roles):
            return None
        return self.own_roles[selector_index], self.names[selector_index]


RegionList: TypeAdapter[list[RegionBox]] = TypeAdapter(list[RegionBox])


def merge(elements: list[ScannedElement], *, rect_epsilon: float = 1.0) -> list[RegionBox]:
    """Group elements sharing a (near-)identical rect (rounded to *rect_epsilon* px) into one region."""
    merged = _merge_rects(
        [element.model_dump(mode="json", by_alias=True) for element in elements],
        rect_epsilon=rect_epsilon,
    )
    return [RegionBox.model_validate(region) for region in merged]
