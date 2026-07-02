from __future__ import annotations

import json
from pathlib import Path

from ostler.vet.manifest import load_manifest


def _write(path: Path, data) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_entries_parse_with_defaults(tmp_path: Path):
    path = _write(tmp_path / "manifest.json", [
        {"selector": "#nav", "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
    ])
    result = load_manifest(path)
    assert not result.errors
    assert len(result.elements) == 1
    el = result.elements[0]
    assert el.selector == "#nav"
    assert el.role == ""
    assert el.visible is True
    assert el.state is None


def test_malformed_entry_is_skipped_and_recorded(tmp_path: Path):
    path = _write(tmp_path / "manifest.json", [
        {"selector": "#nav", "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}},
        {"selector": "#broken"},  # missing required bbox
    ])
    result = load_manifest(path)
    assert len(result.elements) == 1
    assert len(result.errors) == 1
    assert "entry 1" in result.errors[0]


def test_unreadable_manifest_returns_empty_with_error(tmp_path: Path):
    path = tmp_path / "missing.json"
    result = load_manifest(path)
    assert result.elements == []
    assert result.errors and "missing.json" in result.errors[0]


def test_non_list_manifest_errors(tmp_path: Path):
    path = _write(tmp_path / "manifest.json", {"not": "a list"})
    result = load_manifest(path)
    assert result.elements == []
    assert "not a JSON list" in result.errors[0]


def test_explicit_fields_override_defaults(tmp_path: Path):
    path = _write(tmp_path / "manifest.json", [
        {"selector": "#modal", "role": "dialog", "visible": False, "state": "open",
         "bbox": {"x": 1, "y": 2, "width": 3, "height": 4}},
    ])
    el = load_manifest(path).elements[0]
    assert el.role == "dialog"
    assert el.visible is False
    assert el.state == "open"
