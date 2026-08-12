"""Where a component is documented to sit, and what a disagreement reads like.

The defect these exist for reached a green QA run: a page whose whole content was a narrow
column pinned against the right margin, under a scenario asserting `by_role("article")` —
which is true either way. A `placement:` band is the documented fact that assertion cannot
carry, so the grammar's failure modes are contract: a band nobody can violate is worse than
no band at all, because it reads as coverage.
"""

from __future__ import annotations

from ostler.vet.geometry import BBox
from ostler.vet.placement import Placement, Viewport, parse_placement

VIEWPORT = Viewport(width=1440, height=900)


def _bands(text: str) -> Placement:
    parsed = parse_placement(text)
    assert isinstance(parsed, Placement), parsed
    return parsed


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
