from __future__ import annotations

from pathlib import Path

import pytest

from ostler.vet.crop import maybe_crop
from ostler.vet.geometry import BBox
from ostler.vet.regions import RegionBox

pytest.importorskip("PIL")


def _region(x, y, w, h) -> RegionBox:
    return RegionBox(bbox=BBox(x=x, y=y, width=w, height=h), role=None, selectors=["#r"])


def test_missing_screenshot_returns_empty(tmp_path: Path):
    assert maybe_crop(tmp_path / "nope.png", [_region(0, 0, 10, 10)]) == {}


def test_crops_each_unlabeled_region_to_in_memory_png_bytes(tmp_path: Path):
    from PIL import Image
    screenshot = tmp_path / "shot.png"
    Image.new("RGB", (100, 100), "white").save(screenshot)

    crops = maybe_crop(screenshot, [_region(0, 0, 10, 10), _region(20, 20, 5, 5)])
    assert set(crops) == {0, 1}
    assert all(isinstance(data, bytes) and data.startswith(b"\x89PNG") for data in crops.values())
    # never written to disk itself
    assert not (tmp_path / "vet").exists()


def test_no_unlabeled_regions_returns_empty(tmp_path: Path):
    from PIL import Image
    screenshot = tmp_path / "shot.png"
    Image.new("RGB", (100, 100), "white").save(screenshot)
    assert maybe_crop(screenshot, []) == {}
