from __future__ import annotations

from ostler.vet.cdp import ScannedElement
from ostler.vet.geometry import BBox
from ostler.vet.regions import RegionList, merge


def _el(selector, x, y, w, h, role="", tag="div") -> ScannedElement:
    return ScannedElement(selector=selector, tag=tag, role=role,
                          bbox=BBox(x=x, y=y, width=w, height=h))


def test_elements_sharing_identical_rect_merge():
    elements = [_el("#a", 0, 0, 10, 10), _el(".a-child", 0, 0, 10, 10)]
    regions = merge(elements)
    assert len(regions) == 1
    assert regions[0].selectors == ["#a", ".a-child"]


def test_aria_role_labels_the_region():
    elements = [_el("#a", 0, 0, 10, 10, role=""), _el(".a-child", 0, 0, 10, 10, role="navigation")]
    regions = merge(elements)
    assert regions[0].role == "navigation"


def test_group_with_no_role_anywhere_is_unlabeled():
    elements = [_el("#a", 0, 0, 10, 10), _el(".a-child", 0, 0, 10, 10)]
    regions = merge(elements)
    assert regions[0].role is None


def test_near_identical_rects_merge_within_epsilon():
    elements = [_el("#a", 0.0, 0.0, 10.0, 10.0), _el("#b", 0.4, 0.0, 10.0, 10.0)]
    regions = merge(elements, rect_epsilon=1.0)
    assert len(regions) == 1


def test_rects_further_apart_do_not_merge():
    elements = [_el("#a", 0.0, 0.0, 10.0, 10.0), _el("#b", 5.0, 0.0, 10.0, 10.0)]
    regions = merge(elements, rect_epsilon=1.0)
    assert len(regions) == 2


def test_region_list_round_trips_through_json():
    elements = [_el("#a", 0, 0, 10, 10, role="main")]
    regions = merge(elements)
    data = RegionList.dump_json(regions)
    restored = RegionList.validate_json(data)
    assert restored == regions
