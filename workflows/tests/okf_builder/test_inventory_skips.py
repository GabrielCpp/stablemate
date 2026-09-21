"""What the source inventory leaves out (`main/nodes/coverage.py::skipped`)."""
from __future__ import annotations

from pathlib import Path

import pytest

from workhorse_workflows.okf_builder.main.nodes.coverage import skipped


@pytest.mark.parametrize(
    "rel",
    [
        "tests/test_activity.py",
        "pkg/test_units.py",
        "pkg/conftest.py",
        "pkg/__tests__/widget.tsx",
        "internal/test/helpers.go",
        "pkg/_vendor/core/config.py",
        "pkg/units_test.py",
        "pkg/widget.test.tsx",
    ],
)
def test_a_test_or_vendored_file_is_not_a_unit(tmp_path: Path, rel: str) -> None:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    assert skipped(path, tmp_path, [])


@pytest.mark.parametrize("rel", ["pkg/activity.py", "pkg/testing.py", "pkg/contest.py"])
def test_a_source_file_is_a_unit(tmp_path: Path, rel: str) -> None:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    assert not skipped(path, tmp_path, [])
