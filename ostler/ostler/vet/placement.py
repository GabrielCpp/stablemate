"""Where a documented component is supposed to sit on the screen, and whether it did."""

from __future__ import annotations

import re

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from ostler.model import Graph, UINode
from ostler.qa.harness_host import load_harness_module
from ostler.vet.geometry import BBox
from ostler.vet.regions import RegionBox

share = load_harness_module("ostler_qa_scan").share

AXIS: dict[str, str] = {"x": "width", "width": "width", "y": "height", "height": "height"}

_BAND = re.compile(r"^(x|y|width|height)\s+(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*%$")

PLACED_ROLES = frozenset(
    {"main", "article", "navigation", "banner", "complementary", "region", "form", "dialog"}
)


class Viewport(BaseModel):
    model_config = ConfigDict(frozen=True)

    width: float
    height: float


class Band(BaseModel):
    model_config = ConfigDict(frozen=True)

    low: float
    high: float

    def text(self) -> str:
        return f"{self.low * 100:g}-{self.high * 100:g}%"


class Placement(BaseModel):
    """One `placement:` value."""

    model_config = ConfigDict(frozen=True)

    bands: dict[str, Band]

    def text(self) -> str:
        return ", ".join(f"{key} {band.text()}" for key, band in self.bands.items())

    def disagreements(self, bbox: BBox, viewport: Viewport) -> list[str]:
        """One sentence per violated band, each quoting the measured number."""
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
    name: str = ""
    conditional: bool = False


class ComponentVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    selector: str
    status: str
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
        """What the page showed, as the ledger's `actual`."""
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
    """Whether a scanned element's selector is the documented one."""
    return scanned == selector or scanned.startswith(f"{selector}:nth(")


_ROLE_SELECTOR = re.compile(r"""^([a-zA-Z][\w-]*)?\[role=["']([\w-]+)["']\]$""")

_STRING_SELECTOR = re.compile(r"^(?:#[\w-]+|[a-zA-Z][\w-]*(?:\.[\w-]+)*)$")

_SCHEME_SELECTOR = re.compile(r"^([A-Za-z][\w-]*)=(.+)$")

SELECTOR_SCHEMES: frozenset[str] = frozenset({"testID"})


def parse_scheme_selector(selector: str) -> tuple[str, str] | None:
    """`(scheme, value)` for a self-identifying selector naming a known scheme, else `None`."""
    matched = _SCHEME_SELECTOR.match(selector)
    if matched is None:
        return None
    scheme, value = matched.group(1), matched.group(2)
    return (scheme, value) if scheme in SELECTOR_SCHEMES else None


def is_addressable(selector: str) -> bool:
    """Whether *selector* is a form `ostler vet`'s screen census can ever resolve, **or** a self-identifying address the census was never going to resolve for an honest reason."""
    if parse_scheme_selector(selector) is not None:
        return True
    return bool(_ROLE_SELECTOR.match(selector) or _STRING_SELECTOR.match(selector))


def is_web_representable(selector: str) -> bool:
    """Whether *selector* could be handed to a web DOM driver — false for a `scheme=value` address written against a component whose surface a browser drives."""
    return parse_scheme_selector(selector) is None


NOT_WEB_REPRESENTABLE_REASON = (
    "it is a `scheme=value` address (a non-web selector, e.g. `testID=...`), and this "
    "component's surface is driven by a browser, which queries the DOM, not a scheme"
)

_DOM_LEADING_ID_OR_CLASS = re.compile(r"^[#.][A-Za-z_-]")
_DOM_ATTRIBUTE_PREDICATE = re.compile(r"\[[^\]]*\]")
_DOM_COMBINATOR = re.compile(r"[>~]")
_DOM_COMPOUND_TAG = re.compile(r"^[A-Za-z][\w-]*[.#][\w-]+")


def is_mobile_representable(selector: str) -> bool:
    """Whether *selector* could be a Maestro address — false only for a string that unmistakably names DOM syntax instead."""
    text = selector.strip()
    return not (
        _DOM_LEADING_ID_OR_CLASS.match(text)
        or _DOM_ATTRIBUTE_PREDICATE.search(text)
        or _DOM_COMBINATOR.search(text)
        or _DOM_COMPOUND_TAG.match(text)
    )


NOT_MOBILE_REPRESENTABLE_REASON = (
    "it is DOM syntax (an id, a class, an attribute predicate, a combinator, or a "
    "tag.class/tag#id compound), and this component's surface is driven by Maestro, which "
    "resolves a control by a `scheme=value` address (e.g. `testID=...`) or by its visible "
    "text, never by CSS"
)


def is_never_selected(selector: str) -> bool:
    """Always false — the predicate for a driver whose surface renders nothing to query."""
    del selector
    return False


NEVER_SELECTED_REASON = (
    "this driver renders nothing to query — it owns no `screen`/`component` node at all"
)


SELECTOR_GRAMMAR: dict[str, tuple[Callable[[str], bool], str]] = {
    "web": (is_web_representable, NOT_WEB_REPRESENTABLE_REASON),
    "mobile": (is_mobile_representable, NOT_MOBILE_REPRESENTABLE_REASON),
    "http": (is_web_representable, NOT_WEB_REPRESENTABLE_REASON),
    "cli": (is_never_selected, NEVER_SELECTED_REASON),
    "iac": (is_never_selected, NEVER_SELECTED_REASON),
    "artifact": (is_never_selected, NEVER_SELECTED_REASON),
    "none": (is_never_selected, NEVER_SELECTED_REASON),
}

_DEFAULT_SELECTOR_GRAMMAR: tuple[Callable[[str], bool], str] = (lambda _selector: True, "")


def selector_grammar(driver: str | None) -> tuple[Callable[[str], bool], str]:
    """The `(predicate, reason)` pair *driver* is held to for a `selector:` bullet."""
    predicate, reason = SELECTOR_GRAMMAR.get(driver or "", _DEFAULT_SELECTOR_GRAMMAR)
    return predicate, reason


def _region_tags(region: RegionBox) -> set[str]:
    """The element tags a region's minted selectors reveal."""
    tags: set[str] = set()
    for scanned in region.selectors:
        if scanned.startswith("#"):
            return set()
        tag = re.split(r"[.:#]", scanned, maxsplit=1)[0]
        if tag:
            tags.add(tag.lower())
    return tags


def _find_region(selector: str, regions: list[RegionBox]) -> tuple[RegionBox, int] | None:
    """The region a documented selector addresses and **which of its elements**, or None."""
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
    """Why the element the book named is not reachable by the name the book gave it."""
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
    """Register a screenshot's regions against what the book says that screen contains."""
    verdicts: list[ComponentVerdict] = []
    for component in components:
        expected = component.placement.text() if component.placement else "rendered on this screen"
        found = _find_region(component.selector, regions)
        if found is None:
            if component.conditional:
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


_NO_CONDITION = ("none", "n/a", "na", "-")


def _declares_coming_and_going(node: UINode) -> bool:
    """Whether the book gives this component a reason to be absent from a given render."""
    for key in ("states", "exclusive-with"):
        value = str(node.meta.get(key, "")).strip()
        if value and value.split("—")[0].split(",")[0].strip().strip("`").lower() not in _NO_CONDITION:
            return True
    return False


_NO_NAME = frozenset({"none", "n/a", "na", "-", ""})


def _documented_name(node: UINode) -> str:
    """The accessible name the book claims, or "" when it claims none."""
    value = str(node.meta.get("name", "")).strip().strip("`").strip().strip('"').strip()
    return "" if value.lower() in _NO_NAME else value


def screen_components(graph: Graph) -> dict[str, list[VettedComponent]]:
    """Every documented screen's registrable components, keyed by the screen's doc path."""
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


def parse_placement(text: str) -> Placement | str:
    """The declared bands, or the reason the value is not one — never a partial parse."""
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
        bands[key] = Band(low=round(low / 100, 5), high=round(high / 100, 5))
    return Placement(bands=bands)
