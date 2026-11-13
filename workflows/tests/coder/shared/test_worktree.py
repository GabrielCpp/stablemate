"""The folders no proof is reopened by: the artifacts dir, and nothing the book owns."""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse_workflows.coder.shared.worktree import is_product, not_product_roots


@pytest.fixture
def artifacts(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The artifacts dir inside the one repo, as the paddock layout puts it."""
    inside = repo / "artifacts"
    monkeypatch.setenv("STABLEMATE_ARTIFACTS_DIR", str(inside))
    return inside


def test_the_artifacts_dir_is_the_only_folder_that_is_not_product(repo: Path, artifacts: Path) -> None:
    assert not_product_roots(str(repo)) == [artifacts.resolve()]


def test_a_service_book_file_is_product_and_a_spec_file_is_not(repo: Path, artifacts: Path) -> None:
    excluded = not_product_roots(str(repo))

    assert is_product(repo, "services/app/journeys/x.py", excluded)
    assert not is_product(repo, "artifacts/specs/STORY-1/qa_plan.py", excluded)
    assert not is_product(repo, "test-results/trace.zip", excluded)
