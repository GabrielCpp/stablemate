from __future__ import annotations

from ostler.vet.geometry import BBox
from ostler.vet.manifest import DomElement
from ostler.vet.register import match
from ostler.vet.regions import RegionBox


def _dom(selector, x, y, w, h, visible=True, role="") -> DomElement:
    return DomElement(selector=selector, role=role, visible=visible,
                      bbox=BBox(x=x, y=y, width=w, height=h))


def _region(x, y, w, h, role=None, selectors=None) -> RegionBox:
    return RegionBox(bbox=BBox(x=x, y=y, width=w, height=h), role=role,
                     selectors=selectors or ["#r"])


def test_matched_missing_unexpected_unlabeled_bucketing():
    elements = [_dom("#nav", 0, 0, 10, 10), _dom("#gone", 100, 100, 10, 10)]
    regions = [
        _region(0, 0, 10, 10, role="navigation"),
        _region(50, 50, 10, 10, role="dialog"),
        _region(200, 200, 5, 5, role=None),
    ]
    result = match(elements, regions)
    assert len(result.matched) == 1
    assert result.matched[0].dom.selector == "#nav"
    assert [d.selector for d in result.missing] == ["#gone"]
    assert [r.role for r in result.unexpected] == ["dialog"]
    assert len(result.unlabeled) == 1 and result.unlabeled[0].role is None


def test_invisible_elements_excluded_from_all_buckets():
    elements = [_dom("#hidden", 0, 0, 10, 10, visible=False)]
    regions = [_region(0, 0, 10, 10, role="navigation")]
    result = match(elements, regions)
    assert result.matched == []
    assert result.missing == []
    assert len(result.unexpected) == 1  # region never claimed since the dom element is skipped


def test_matching_is_deterministic_regardless_of_input_order():
    elements = [_dom("#a", 0, 0, 10, 10), _dom("#b", 1, 1, 10, 10)]
    regions = [_region(0, 0, 10, 10, role="main", selectors=["#r1"]),
              _region(1, 1, 10, 10, role="main", selectors=["#r2"])]

    forward = match(elements, regions)
    backward = match(list(reversed(elements)), list(reversed(regions)))

    forward_pairs = {(p.dom.selector, tuple(p.region.selectors)) for p in forward.matched}
    backward_pairs = {(p.dom.selector, tuple(p.region.selectors)) for p in backward.matched}
    assert forward_pairs == backward_pairs
    assert len(forward.matched) == len(backward.matched) == 2
