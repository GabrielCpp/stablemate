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

from ostler.model import Graph, UINode
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
    #: The book gives a reason this one may legitimately not be in the render — a `states:`
    #: bullet, or an `exclusive-with:` sibling it can never co-render with. Presence is then
    #: unprovable from one photograph, and the scenario's own assertions are what establish it.
    conditional: bool = False


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


#: A documented selector that addresses a component by its ARIA role — `p[role="alert"]`,
#: `[role="dialog"]` — the way an accessibility-first book prefers to. The scan never mints
#: this form (it mints `#id` or `tag.class:nth(i)`), so string comparison can never match it;
#: the role the scan *did* record on the region is what carries the same fact.
_ROLE_SELECTOR = re.compile(r"""^([a-zA-Z][\w-]*)?\[role=["']([\w-]+)["']\]$""")


def _region_tags(region: RegionBox) -> set[str]:
    """The element tags a region's minted selectors reveal. A `#id` selector reveals none,
    which reads as "any tag" — the id was the better address, not a hidden disagreement."""
    tags: set[str] = set()
    for scanned in region.selectors:
        if scanned.startswith("#"):
            return set()
        tag = re.split(r"[.:#]", scanned, maxsplit=1)[0]
        if tag:
            tags.add(tag.lower())
    return tags


def _find_region(selector: str, regions: list[RegionBox]) -> RegionBox | None:
    """The region a documented selector addresses, or None.

    Two vocabularies meet here: the string forms the scan mints (matched by `_matches`),
    and the `tag[role=...]` form the scan cannot mint, matched by the role it recorded.
    """
    by_role = _ROLE_SELECTOR.match(selector)
    if by_role:
        tag, role = (by_role.group(1) or "").lower(), by_role.group(2)
        for region in regions:
            if region.role != role:
                continue
            tags = _region_tags(region)
            if not tag or not tags or tag in tags:
                return region
        return None
    return next(
        (r for r in regions if any(_matches(selector, s) for s in r.selectors)),
        None,
    )


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
        region = _find_region(component.selector, regions)
        if region is None:
            if component.conditional:
                # A screen documents its conditional components alongside its steady state —
                # an error banner, the empty-list placeholder, the half of an `exclusive-with`
                # pair that is not showing. Demanding all of them in one photograph asks a
                # single render to be every state the screen has, which no render is. The
                # book already says these come and go; absence is not the disagreement.
                continue
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


#: The two ways a `states:` or `exclusive-with:` bullet says *there is nothing conditional here*.
#: Both keys are written on every component that has them at all, so their absence is not the
#: signal — an author who filled the stub in with the negative meant the component is always up.
_NO_CONDITION = ("none", "n/a", "na", "-")


def _declares_coming_and_going(node: UINode) -> bool:
    """Whether the book gives this component a reason to be absent from a given render.

    `states:` enumerates the forms it takes and `exclusive-with:` names what it never
    co-renders with; either one means one photograph cannot be expected to contain it. The
    values are prose — `exclusive-with:` in particular is usually a sentence, not a link — so
    this reads presence, not structure, and only the explicit negatives count as "no".
    """
    for key in ("states", "exclusive-with"):
        value = str(node.meta.get(key, "")).strip()
        if value and value.split("—")[0].split(",")[0].strip().strip("`").lower() not in _NO_CONDITION:
            return True
    return False


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
            conditional=_declares_coming_and_going(node),
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
