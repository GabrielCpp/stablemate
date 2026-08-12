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

from ostler.qa.harness_host import load_harness_module
from ostler.vet.geometry import BBox

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
