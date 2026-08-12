"""Where a documented component is supposed to sit on the screen, and whether it did.

`ostler vet`'s manifest path answers a different question: it registers regions by IoU against
bboxes measured off the very page under test, so it is a *census* — which documented components
rendered, and what rendered that nothing documents. It cannot say a component is in the wrong
place, because its notion of the right place came from the render.

A `placement:` bullet is the missing half, and it is deliberately not a layout vocabulary. No
`sidebar`, no `main-column`, nothing that assumes the page has a grid: just where the box lands
against the window, as a percentage of it.

    - placement: width 60-100%, x 0-20%

Bands, never points — a band wide enough to survive a resize is the difference between a check
that finds real defects and one people stop authoring because it flakes.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from ostler.model import Graph
from ostler.qa.harness_host import load_harness_module
from ostler.vet.geometry import BBox
from ostler.vet.regions import RegionBox

#: The same rounding the layout digest beside every screenshot reports, so a component is never
#: on one side of its band in the evidence and the other side in the verdict.
share = load_harness_module("ostler_qa_scan").share

#: What a band constrains, and which viewport dimension it is a fraction of.
AXIS: dict[str, str] = {"x": "width", "width": "width", "y": "height", "height": "height"}

_BAND = re.compile(r"^(x|y|width|height)\s+(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*%$")

#: Roles whose placement is worth stating: they carry a page rather than sitting inside
#: something that does. A button's placement is brittle and proves nothing.
PLACED_ROLES = frozenset(
    {"main", "article", "navigation", "banner", "complementary", "region", "form", "dialog"}
)


class Viewport(BaseModel):
    model_config = ConfigDict(frozen=True)

    width: float
    height: float


class Band(BaseModel):
    model_config = ConfigDict(frozen=True)

    low: float   # a fraction of the viewport, not a percentage
    high: float

    def text(self) -> str:
        return f"{self.low * 100:g}-{self.high * 100:g}%"


class Placement(BaseModel):
    """One `placement:` value. A key it does not carry is unconstrained, not zero."""

    model_config = ConfigDict(frozen=True)

    bands: dict[str, Band]

    def text(self) -> str:
        return ", ".join(f"{key} {band.text()}" for key, band in self.bands.items())

    def disagreements(self, bbox: BBox, viewport: Viewport) -> list[str]:
        """One sentence per violated band, each quoting the measured number.

        A disagreement that does not say what was measured is unactionable — the fix loop
        receives this text and nothing else about the geometry.
        """
        out: list[str] = []
        for key, band in self.bands.items():
            total = viewport.width if AXIS[key] == "width" else viewport.height
            measured = share(getattr(bbox, key), total)
            if measured < band.low or measured > band.high:
                out.append(
                    f"{key} is {measured * 100:g}% of the viewport, documented as {band.text()}"
                )
        return out


class VettedComponent(BaseModel):
    """One documented component of a screen, as the check needs it."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    selector: str
    placement: Placement | None = None


class ComponentVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    selector: str
    status: str  # matched | misplaced | missing
    expected: str
    detail: list[str] = []
    bbox: BBox | None = None

    @property
    def ok(self) -> bool:
        return self.status == "matched"

    def sentence(self) -> str:
        """What the ledger records — the assertion label a reader sees, alone."""
        if self.status == "missing":
            return f"{self.node_id} (`{self.selector}`) rendered nowhere on this screen"
        if self.status == "misplaced":
            return f"{self.node_id} (`{self.selector}`) is placed wrong: " + "; ".join(self.detail)
        return f"{self.node_id} (`{self.selector}`) is where the book places it"


def _matches(selector: str, scanned: str) -> bool:
    """Whether a scanned element's selector is the documented one.

    The scan mints `tag.class:nth(i)` for an element with no id, and the index is a position
    in one render — the book cannot know it and must not have to. So the documented selector
    matches the scanned one whole, or up to that suffix.
    """
    return scanned == selector or scanned.startswith(f"{selector}:nth(")


def check(
    components: list[VettedComponent], regions: list[RegionBox], viewport: Viewport
) -> list[ComponentVerdict]:
    """Register a screenshot's regions against what the book says that screen contains.

    Matching is by **selector**, not by IoU as `vet/register.py` does, and the difference is
    the whole point. The manifest path measures the expected bboxes off the very render under
    test, so it can only answer *which documented components appeared* — a census where
    agreement is guaranteed by construction. Here the book names the element and the render
    supplies the geometry, so the two can genuinely disagree.

    Regions no component claims are not judged: a real screen renders chrome the book does
    not model, and failing on that would make the check unauthorable.
    """
    verdicts: list[ComponentVerdict] = []
    for component in components:
        expected = component.placement.text() if component.placement else "rendered on this screen"
        region = next(
            (r for r in regions if any(_matches(component.selector, s) for s in r.selectors)),
            None,
        )
        if region is None:
            verdicts.append(ComponentVerdict(
                node_id=component.node_id, selector=component.selector,
                status="missing", expected=expected))
            continue
        said = (
            component.placement.disagreements(region.bbox, viewport)
            if component.placement
            else []
        )
        verdicts.append(ComponentVerdict(
            node_id=component.node_id,
            selector=component.selector,
            status="misplaced" if said else "matched",
            expected=expected,
            detail=said,
            bbox=region.bbox,
        ))
    return verdicts


def screen_components(graph: Graph) -> dict[str, list[VettedComponent]]:
    """Every documented screen's registrable components, keyed by the screen's doc path.

    A component with no `selector:` is left out rather than reported: nothing can address it
    in a render, so listing it would turn every vet into a wall of unprovable `missing`. The
    doctor is where that omission is a finding — here it is just absent.
    """
    table: dict[str, list[VettedComponent]] = {}
    for node in graph.ui_nodes:
        if node.type != "component":
            continue
        selector = str(node.meta.get("selector", "")).strip().strip("`").strip()
        if not selector:
            continue
        raw = str(node.meta.get("placement", "")).strip()
        parsed = parse_placement(raw) if raw else None
        table.setdefault(node.id.split("#")[0], []).append(VettedComponent(
            node_id=node.id,
            selector=selector,
            placement=parsed if isinstance(parsed, Placement) else None,
        ))
    return table


def parse_placement(text: str) -> Placement | str:
    """The declared bands, or the reason the value is not one — never a partial parse.

    Returning the message rather than raising is what lets the doctor report a malformed
    bullet as a finding on the bullet, in the same pass that reports a missing one.
    """
    bands: dict[str, Band] = {}
    parts = [part.strip() for part in text.split(",")]
    for part in parts:
        if not part:
            return "a placement is `key min-max%` pairs separated by commas, with no empty part"
        matched = _BAND.match(part)
        if matched is None:
            return (
                f"'{part}' is not a `key min-max%` pair; key is one of "
                f"{', '.join(sorted(AXIS))} and both bounds are percentages of the viewport"
            )
        key, low_text, high_text = matched.group(1), matched.group(2), matched.group(3)
        if key in bands:
            return f"'{key}' is constrained twice"
        low, high = float(low_text), float(high_text)
        if low > high:
            return f"'{part}' runs backwards — {low:g}% is above {high:g}%"
        if high > 100:
            return f"'{part}' exceeds the viewport; a band is a percentage of it, so at most 100%"
        # Rounded to the resolution `share` reports (3 decimals of a fraction, so 1 decimal of
        # a percent, plus two spare). Without it `69.4 / 100` and the digest's `round(…, 3)`
        # differ by one ulp, and a component measured at exactly its declared bound reports a
        # disagreement whose two numbers print identically.
        bands[key] = Band(low=round(low / 100, 5), high=round(high / 100, 5))
    return Placement(bands=bands)
