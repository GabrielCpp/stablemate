"""Test utilities for workflow authors."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

__all__ = [
    "make_git_repo",
    "assert_file",
    "assert_file_contains",
    "assert_json_file",
]



def make_git_repo(path: Path, *, name: str = "test") -> Path:
    """Initialise a minimal real git repo at ``path`` with one commit."""
    path.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "t"],
    ):
        subprocess.run(cmd, cwd=str(path), check=True, capture_output=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-qm", "init"], cwd=str(path), check=True, capture_output=True
    )
    return path



def assert_file(sandbox: Path, rel: str) -> None:
    """Assert that ``sandbox / rel`` exists."""
    path = sandbox / rel
    assert path.exists(), f"Expected file {rel!r} to exist in sandbox, but it does not"


def assert_file_contains(sandbox: Path, rel: str, text: str) -> None:
    """Assert that ``sandbox / rel`` exists and contains ``text``."""
    path = sandbox / rel
    assert path.exists(), f"Expected file {rel!r} to exist in sandbox, but it does not"
    content = path.read_text(encoding="utf-8")
    assert text in content, (
        f"Expected {rel!r} to contain {text!r}\n"
        f"Actual content:\n{content}"
    )


def assert_json_file(sandbox: Path, rel: str, subset: dict | list) -> None:
    """Assert that ``sandbox / rel`` is valid JSON matching ``subset``."""
    path = sandbox / rel
    assert path.exists(), f"Expected JSON file {rel!r} to exist in sandbox, but it does not"
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AssertionError(f"File {rel!r} is not valid JSON: {e}") from e
    if isinstance(subset, list):
        assert actual == subset, (
            f"Expected {rel!r} to equal {subset!r}\nActual: {actual!r}"
        )
    else:
        for key, expected_val in subset.items():
            assert key in actual, (
                f"Expected key {key!r} in {rel!r}\nActual keys: {list(actual)}"
            )
            assert actual[key] == expected_val, (
                f"Expected {rel!r}[{key!r}] == {expected_val!r}\nActual: {actual[key]!r}"
            )
