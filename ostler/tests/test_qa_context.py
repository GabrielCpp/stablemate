from __future__ import annotations

import subprocess
from pathlib import Path

from ostler.qa.context import build_context, validate_context


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def test_context_maps_base_grounding_and_preserves_repeated_refs(tmp_path: Path):
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    feature = tmp_path / "docs/features/demo/item.md"
    feature.write_text(
        """---
type: concept
title: Item
---
# Item

- code: app/service.py::create_item
- code: app/service.py::read_item
- verify: tests/test_service.py::test_create
- verify: tests/test_service.py::test_read
""",
        encoding="utf-8",
    )
    source = tmp_path / "app/service.py"
    source.write_text(
        "def create_item():\n    return 'old'\n\ndef read_item():\n    return 'item'\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    # Removing the head grounding cannot hide impact because the base graph is unioned.
    feature.write_text(feature.read_text(encoding="utf-8").replace("- code: app/service.py::create_item\n", ""), encoding="utf-8")
    source.write_text(source.read_text(encoding="utf-8").replace("return 'old'", "return 'new'"), encoding="utf-8")

    packet = build_context(
        tmp_path,
        base=base,
        source_roots={"demo": ["app"]},
    )

    assert validate_context(packet) == []
    assert packet["changedCode"][0]["headSymbols"] == ["create_item"]
    assert packet["directNodes"]
    assert packet["obligations"]
    refs = {item["ref"] for item in packet["verificationRefs"]}
    assert "tests/test_service.py::test_create" in refs
    assert "tests/test_service.py::test_read" in refs


def test_context_reports_unmapped_production_change(tmp_path: Path):
    (tmp_path / "docs/features/demo").mkdir(parents=True)
    (tmp_path / "docs/features/demo/item.md").write_text(
        "---\ntype: concept\ntitle: Item\n---\n# Item\n",
        encoding="utf-8",
    )
    (tmp_path / "unknown").mkdir()
    source = tmp_path / "unknown/service.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "qa@example.com")
    _git(tmp_path, "config", "user.name", "QA")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text("VALUE = 2\n", encoding="utf-8")

    packet = build_context(tmp_path, base=base, source_roots={"other": ["unknown"]})

    assert packet["healthFindings"][0]["kind"] == "unmapped-change"
