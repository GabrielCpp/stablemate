from __future__ import annotations

from ostler.vet.geometry import BBox, iou


def _box(x, y, w, h) -> BBox:
    return BBox(x=x, y=y, width=w, height=h)


def test_iou_no_overlap_is_zero():
    assert iou(_box(0, 0, 10, 10), _box(100, 100, 10, 10)) == 0.0


def test_iou_identical_boxes_is_one():
    a = _box(5, 5, 20, 20)
    assert iou(a, a.model_copy()) == 1.0


def test_iou_partial_overlap_is_hand_computed():
    a = _box(0, 0, 10, 10)   # area 100
    b = _box(5, 5, 10, 10)   # area 100, intersection 5x5=25, union 175
    assert iou(a, b) == 25 / 175


def test_iou_zero_area_box_is_zero_no_div_by_zero():
    a = _box(0, 0, 0, 0)
    b = _box(0, 0, 10, 10)
    assert iou(a, b) == 0.0
    assert iou(a, a) == 0.0
