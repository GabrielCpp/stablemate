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
from urllib.parse import urlsplit

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
    #: The accessible name the book claims this component has. Empty when the book makes no
    #: claim — which, per the grammar, an absent `name:` and a `name:` whose value names
    #: emptiness both are.
    name: str = ""
    #: The book gives a reason this one may legitimately not be in the render — a `states:`
    #: bullet, or an `exclusive-with:` sibling it can never co-render with. Presence is then
    #: unprovable from one photograph, and the scenario's own assertions are what establish it.
    conditional: bool = False


class ComponentVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    selector: str
    status: str  # matched | misplaced | misnamed | missing
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
        if self.status == "misnamed":
            return f"{self.node_id} (`{self.selector}`) is named wrong: " + "; ".join(self.detail)
        return f"{self.node_id} (`{self.selector}`) is where the book places it"

    def observed(self) -> str:
        """What the page showed, as the ledger's `actual`.

        The ledger asks a verdict for the observation it made, and a verdict that has made
        none says so in those words. It used to be written as the literal `"as documented"`
        whenever `detail` was empty — which is every `missing` verdict, since a component
        that rendered nowhere has no band to disagree with. A reader of `qa-run.ndjson` then
        saw a failed assertion whose `actual` read like a pass, and the real observation
        (`status: missing`, `bbox: null`) stayed in the vet JSON beside it. A constant is not
        an observation.
        """
        if self.status == "missing":
            return "missing: nothing on the rendered screen answered this selector"
        where = (
            f" at x={self.bbox.x:g}, y={self.bbox.y:g}, "
            f"{self.bbox.width:g}x{self.bbox.height:g}"
            if self.bbox is not None
            else ""
        )
        return f"{self.status}{where}" + ("; " + "; ".join(self.detail) if self.detail else "")


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

#: A documented selector in the one other form `_matches` can ever agree with: an id, or a bare
#: tag optionally followed by one or more classes. The scan's own `:nth(i)` disambiguating suffix
#: is never written in the book — it is a position in one particular render, minted by the scan,
#: not a fact the book could know in advance.
_STRING_SELECTOR = re.compile(r"^(?:#[\w-]+|[a-zA-Z][\w-]*(?:\.[\w-]+)*)$")


def is_addressable(selector: str) -> bool:
    """Whether *selector* is a form `ostler vet`'s screen census can ever resolve.

    The census matches a documented selector against strings the render scan mints for each
    element — `#id`, or `tag.class` (optionally the scan's own `:nth(i)` position suffix) — or,
    for the one vocabulary the scan never mints as a string, against the ARIA role it recorded
    on the region (`_ROLE_SELECTOR`). Anything else — an attribute-value predicate
    (`[data-state="booked"]`), a boolean attribute (`[disabled]`), a pseudo-class — addresses
    nothing the scan ever produces, on any render, however precisely it describes the DOM: the
    component reads `missing` every time, which makes the one defect that would move it
    unmeasurable. This is the rule behind the doctor's `unaddressable-selector` check.

    It is a claim about the *census*, not about the compiled plan: `qa.by_css` compiles any
    valid CSS, so a `visible(locator=...)` on such a selector is observed by the QA run even
    while the census stays blind to it. `compile_plan` therefore raises no gap here — a gap
    reports what the plan being compiled failed to observe, and one observer's blindness is
    not a channel the other one's report can carry.
    """
    return bool(_ROLE_SELECTOR.match(selector) or _STRING_SELECTOR.match(selector))


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


def _find_region(selector: str, regions: list[RegionBox]) -> tuple[RegionBox, int] | None:
    """The region a documented selector addresses and **which of its elements**, or None.

    Two vocabularies meet here: the string forms the scan mints (matched by `_matches`),
    and the `tag[role=...]` form the scan cannot mint, matched by the role it recorded.

    The index is not a detail. A region is a rect, several elements share a rect, and a
    property like an accessible name belongs to one element and not to the rect — so a caller
    that asks the region a question about the documented element needs to know which member
    of it was documented. For a role selector that is the member whose *own* role is the one
    written down; `region.role` is the nearest ancestor carrying a role and can belong to an
    element the book never named.
    """
    by_role = _ROLE_SELECTOR.match(selector)
    if by_role:
        tag, role = (by_role.group(1) or "").lower(), by_role.group(2)
        for region in regions:
            if region.role != role:
                continue
            tags = _region_tags(region)
            if not tag or not tags or tag in tags:
                own = next((i for i, r in enumerate(region.own_roles) if r == role), 0)
                return region, own
        return None
    for region in regions:
        for index, scanned in enumerate(region.selectors):
            if _matches(selector, scanned):
                return region, index
    return None


def _flat(text: str) -> str:
    """Whitespace collapsed the way the accessibility tree collapses it, and the scan with it."""
    return " ".join(text.split())


def _name_disagreement(
    documented: str, region: RegionBox, index: int
) -> list[str]:
    """Why the element the book named is not reachable by the name the book gave it.

    The comparison is the one a Playwright `get_by_role(role, name=...)` performs: whitespace
    collapsed, case folded, the whole string. A book that states a name no accessibility tree
    computes is not a cosmetic defect — that locator matches zero elements while the element
    is painted, so every check written against it fails for a reason the screenshot denies.

    Silence has two spellings and they are not the same claim. A book with no `name:` states
    nothing to disagree with. A scan that recorded no name — a `regions.json` frozen before
    this observation existed — is a page nobody looked at, and reporting a disagreement from
    it would be reporting an absence as an event.
    """
    if not documented:
        return []
    observed = region.observed(index)
    if observed is None:
        return []
    own_role, actual = observed
    if _flat(actual).casefold() == _flat(documented).casefold():
        return []
    where = f"the `{own_role}` there" if own_role else "the element there"
    has = f"is named {_flat(actual)!r}" if _flat(actual) else "has no accessible name"
    return [f"the book names it {_flat(documented)!r}, but {where} {has}"]


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
        found = _find_region(component.selector, regions)
        if found is None:
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
        region, index = found
        said = (
            component.placement.disagreements(region.bbox, viewport)
            if component.placement
            else []
        )
        named = _name_disagreement(component.name, region, index)
        # The name is reported ahead of the placement, and instead of it, because a name the
        # accessibility tree does not compute makes every other claim about that element
        # unmeasurable: the locator the book's own checks compile to selects nothing. The
        # placement is measured again, against the element the repaired name reaches.
        status = "misnamed" if named else "misplaced" if said else "matched"
        verdicts.append(ComponentVerdict(
            node_id=component.node_id,
            selector=component.selector,
            status=status,
            expected=expected,
            detail=named or said,
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


#: How a `name:` bullet says *this component has no accessible name*. An absent bullet says the
#: same thing, which is why both land on the empty string: an empty key and a key whose value
#: names emptiness are one claim, and the check has nothing to compare either against.
_NO_NAME = frozenset({"none", "n/a", "na", "-", ""})


def _documented_name(node: UINode) -> str:
    """The accessible name the book claims, or "" when it claims none."""
    value = str(node.meta.get("name", "")).strip().strip("`").strip().strip('"').strip()
    return "" if value.lower() in _NO_NAME else value


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
            name=_documented_name(node),
            conditional=_declares_coming_and_going(node),
        ))
    return table


def screen_routes(graph: Graph) -> dict[str, str]:
    """Each documented screen's `route:`, keyed the way `screen_components` keys components.

    The route is what a reader of a rendered page has to go on to say *which* screen it is:
    a screen node carries no other bullet that a browser could be asked about. A file
    documenting two screens is left out rather than guessed at — two routes and one page is
    an ambiguity, and a vet that picked one of them would establish its subject by coin-toss.
    """
    routes: dict[str, set[str]] = {}
    for node in graph.ui_nodes:
        if node.type != "screen":
            continue
        route = str(node.meta.get("route", "")).strip().strip("`").strip()
        if route:
            routes.setdefault(node.id.split("#")[0], set()).add(route)
    return {path: next(iter(found)) for path, found in routes.items() if len(found) == 1}


def literal_route(route: str) -> str:
    """The path a browser's URL must equal for this route, or "" when the route is a pattern.

    A route with a `{param}` in it names a family of pages, and no string comparison can say
    whether the one on screen is a member. Rather than match loosely — which would let a vet
    establish the wrong subject and report every verdict about it anyway — a pattern route
    returns nothing and the caller says it could not establish the screen.
    """
    text = route.strip()
    if not text.startswith("/") or "{" in text or "*" in text:
        return ""
    return text.rstrip("/") or "/"


def arrived_at(url: str, route: str) -> bool:
    """Whether a page at *url* is the screen documented at *route*.

    Compares paths only: a query string and a fragment are state within a screen, not a
    different screen, and a book that had to enumerate them could never be written.
    """
    path = urlsplit(url).path
    return (path.rstrip("/") or "/") == literal_route(route)


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
