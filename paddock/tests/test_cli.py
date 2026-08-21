"""What `paddock` resolves before it runs anything."""

from pathlib import Path

from paddock import paths
from paddock.cli import _project


def test_the_project_is_the_repo_root_not_the_data_dir_s_parent(tmp_path: Path) -> None:
    """The data directory is nested two deep, and the pin is only real if this walks up.

    `DATA_DIRNAME` is `paddock/data`, so the parent of the data directory is `paddock/` —
    a subdirectory, not a repository. `pin()` degrades on a source it cannot clone, so
    getting this wrong does not raise: it runs every round unpinned and unfenced, and
    says so only in a log line. The test pins the walk rather than the arithmetic so that
    moving the data directory again cannot quietly re-open it.
    """
    root = tmp_path / "workspace"
    (root / ".git").mkdir(parents=True)
    data_dir = root / paths.DATA_DIRNAME
    data_dir.mkdir(parents=True)

    assert _project(data_dir) == root
    assert data_dir.parent != root, "the fixture must be deeper than one level, or it proves nothing"


def test_a_data_dir_outside_a_repo_resolves_to_itself(tmp_path: Path) -> None:
    """Tolerant, not fatal: `--data-dir` may name a directory with no repo above it, and
    `pin()` degrades from there with a caveat rather than the CLI refusing to start."""
    loose = tmp_path / "loose"
    loose.mkdir()
    assert _project(loose) == loose
