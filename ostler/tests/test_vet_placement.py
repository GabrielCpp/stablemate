"""Where a component is documented to sit, and what a disagreement reads like.

The defect these exist for reached a green QA run: a page whose whole content was a narrow
column pinned against the right margin, under a scenario asserting `by_role("article")` —
which is true either way. A `placement:` band is the documented fact that assertion cannot
carry, so the grammar's failure modes are contract: a band nobody can violate is worse than
no band at all, because it reads as coverage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler.model import Graph, UINode
from ostler.vet.geometry import BBox
from ostler.vet.placement import (
    Placement, VettedComponent, Viewport, check, parse_placement, screen_components,
)
from ostler.vet.regions import RegionBox

VIEWPORT = Viewport(width=1440, height=900)


def _bands(text: str) -> Placement:
    parsed = parse_placement(text)
    assert isinstance(parsed, Placement), parsed
    return parsed


def _conditional(node_id: str, selector: str) -> VettedComponent:
    return VettedComponent(node_id=node_id, selector=selector, conditional=True)


def _graph_with_component(meta: dict[str, str]) -> Graph:
    node = UINode(
        type="component", kind="section", id="s.md#c", path=Path("s.md"), anchor="c", meta=meta,
    )
    return Graph(root=Path("."), org_name="acme", profile="full", doc_roots={}, ui_nodes=[node])


def test_a_placement_is_bands_of_the_viewport_and_nothing_else() -> None:
    placement = _bands("width 60-100%, x 0-20%")
    assert sorted(placement.bands) == ["width", "x"]
    assert placement.bands["width"].low == 0.6 and placement.bands["width"].high == 1.0
    assert placement.bands["x"].low == 0.0 and placement.bands["x"].high == 0.2

    assert _bands("height 80-100%").bands.keys() == {"height"}, (
        "an omitted key is unconstrained, not zero"
    )
    assert _bands("y 5.5-12%").bands["y"].low == 0.055, "a fractional percent is a percent"
    assert _bands("  width   60 - 100 %  ").bands.keys() == {"width"}, "whitespace is not meaning"


def test_every_spelling_that_is_not_a_band_says_why() -> None:
    """A malformed placement is reported on the bullet, so `parse_placement` returns the
    reason rather than raising — the doctor needs to keep going and check the next node."""
    for text, needle in [
        ("wide 60-100%", "not a `key min-max%` pair"),
        ("width 60-100", "not a `key min-max%` pair"),
        ("width 60%", "not a `key min-max%` pair"),
        ("width 60-100%,", "no empty part"),
        ("width 100-60%", "runs backwards"),
        ("width 60-140%", "exceeds the viewport"),
        ("width 10-20%, width 60-100%", "constrained twice"),
    ]:
        problem = parse_placement(text)
        assert isinstance(problem, str), f"{text!r} must not parse"
        assert needle in problem, problem


def test_a_disagreement_quotes_the_number_that_produced_it() -> None:
    """The fix loop receives this sentence and nothing else about the geometry, so a
    disagreement that does not say what was measured is unactionable."""
    crushed = BBox(x=1180, y=88, width=250, height=760)
    said = _bands("width 60-100%, x 0-20%").disagreements(crushed, VIEWPORT)

    assert said == [
        "width is 17.4% of the viewport, documented as 60-100%",
        "x is 81.9% of the viewport, documented as 0-20%",
    ]


def test_a_band_is_inclusive_and_an_unconstrained_key_never_disagrees() -> None:
    """Bands are authored by reading the running UI, so a value landing exactly on the
    boundary someone just measured must not be a failure — that is a flake generator."""
    edge = BBox(x=0, y=0, width=864, height=900)  # 864/1440 == 0.6 exactly
    assert _bands("width 60-100%").disagreements(edge, VIEWPORT) == []
    assert _bands("height 5-20%").disagreements(edge, VIEWPORT) == [
        "height is 100% of the viewport, documented as 5-20%"
    ]
    assert _bands("x 0-20%").disagreements(edge, VIEWPORT) == [], (
        "y and height are unconstrained here, so they cannot be violated"
    )


def test_the_share_is_the_one_the_evidence_beside_the_screenshot_reports() -> None:
    """`share` is imported from the harness scan rather than restated, so a component can
    never be inside its band in the layout digest and outside it in the verdict."""
    box = BBox(x=0, y=0, width=1000, height=900)
    assert _bands("width 69.4-69.4%").disagreements(box, VIEWPORT) == [], (
        "1000/1440 rounds to 0.694 in the digest and must round the same way here"
    )


def _region(role: str | None, selectors: list[str], box: tuple[float, float, float, float]) -> RegionBox:
    x, y, w, h = box
    return RegionBox(bbox=BBox(x=x, y=y, width=w, height=h), role=role, selectors=selectors)


def _component(node_id: str, selector: str, placement: str | None = None) -> VettedComponent:
    return VettedComponent(
        node_id=node_id, selector=selector,
        placement=_bands(placement) if placement else None,
    )


def test_the_screen_the_book_documents_is_registered_against_the_one_that_rendered() -> None:
    """The verdict `vet`'s IoU path cannot reach: there, the expected bboxes were measured off
    the very render under test, so agreement is guaranteed by construction. Here the book names
    the element and the render supplies the geometry, so the two can disagree."""
    regions = [
        _region("banner", ["header.site"], (0, 0, 1440, 64)),
        _region("article", ["article.prose:nth(41)"], (1180, 88, 250, 760)),
        _region(None, ["div.decoration:nth(7)"], (0, 0, 8, 8)),
    ]
    verdicts = check(
        [
            _component("screens/ref.md#header", "header.site", "width 90-100%, x 0-10%"),
            _component("screens/ref.md#body", "article.prose", "width 60-100%, x 0-20%"),
            _component("screens/ref.md#toc", "nav.toc", "width 10-25%"),
        ],
        regions,
        VIEWPORT,
    )

    assert [(v.node_id.split("#")[1], v.status) for v in verdicts] == [
        ("header", "matched"), ("body", "misplaced"), ("toc", "missing"),
    ]
    assert verdicts[1].detail == [
        "width is 17.4% of the viewport, documented as 60-100%",
        "x is 81.9% of the viewport, documented as 0-20%",
    ]
    assert verdicts[1].bbox == BBox(x=1180, y=88, width=250, height=760)
    assert verdicts[2].sentence().endswith("rendered nowhere on this screen")


def test_a_region_no_component_claims_is_counted_not_judged() -> None:
    """A real screen renders chrome the book does not model. Failing on it would make the
    check unauthorable, which is how a check stops being authored at all."""
    verdicts = check(
        [_component("s.md#main", "#root", "width 90-100%")],
        [
            _region("main", ["#root"], (0, 0, 1440, 900)),
            _region("contentinfo", ["footer.vendor-widget"], (0, 860, 1440, 40)),
        ],
        VIEWPORT,
    )
    assert [v.status for v in verdicts] == ["matched"]


def test_a_component_with_no_placement_is_still_checked_for_being_there() -> None:
    """`placement:` is only demanded of the roles that carry a page, so most components
    arrive without one. Presence is what remains provable about them."""
    present, absent = check(
        [_component("s.md#save", "#save"), _component("s.md#undo", "#undo")],
        [_region("button", ["#save"], (1300, 20, 100, 32))],
        VIEWPORT,
    )
    assert (present.status, absent.status) == ("matched", "missing")
    assert present.detail == []


def test_a_component_the_book_says_comes_and_goes_is_not_missing_when_it_is_gone() -> None:
    """One photograph cannot be every state a screen has.

    A screen documents its error banner and its empty-list placeholder next to its steady
    state, and a scenario exercising the successful render contains neither. Failing the vet
    on their absence makes a passing screen unvettable and pushes the author to delete the
    documentation of the states — so a component the book already says comes and goes is
    judged on where it sits when it is there, and nothing when it is not.
    """
    verdicts = check(
        [
            _conditional("s.md#error", "#error"),
            _component("s.md#list", "#list"),
        ],
        [],
        VIEWPORT,
    )

    assert [(v.node_id, v.status) for v in verdicts] == [("s.md#list", "missing")]


@pytest.mark.parametrize(
    ("bullets", "conditional"),
    [
        ({"states": "`full` (default on load), `loading`, `empty`"}, True),
        ({"exclusive-with": "the publish action itself — publishing is a separate story"}, True),
        # Both keys are written on every component that carries them, so an author who filled
        # the stub in with the negative said the component is always up — not that nobody looked.
        ({"states": "none — content is fixed regardless of which fixture is active"}, False),
        ({"exclusive-with": "n/a"}, False),
        ({}, False),
    ],
)
def test_only_a_stated_condition_excuses_a_component_from_being_there(
    bullets: dict[str, str], conditional: bool
) -> None:
    """`- states: none` and `- exclusive-with: n/a` are the documented ways to say *no
    condition*, and they are the whole difference between a component that may be absent and
    one whose absence is a defect."""
    graph = _graph_with_component({"selector": "#c", **bullets})

    assert screen_components(graph)["s.md"][0].conditional is conditional
