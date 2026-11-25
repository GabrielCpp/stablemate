"""No tracked Python file hand-writes a list of harness names the registry already holds."""

from __future__ import annotations

import ast
import shutil
import subprocess
from pathlib import Path

import pytest

from stablemate_core.harness import names

DEFINITION = "core/stablemate_core/harness.py"
EXCLUDED_FILES = frozenset(
    {"test_harness_coverage.py", "test_no_harness_name_lists.py"}
)
ALLOWED: dict[str, tuple[str, list[str]]] = {
    "core/stablemate_core/schema/home.py": (
        "schema examples show two sample values",
        ["claude, opencode", "claude, opencode"],
    ),
    "core/tests/test_harness.py": (
        "the registry's own tests pin its order",
        [
            "antigravity, claude, codex, copilot, pi",
            "antigravity, claude, codex, copilot, pi",
            "antigravity, claude, codex, copilot, opencode, pi",
        ],
    ),
    "farrier/tests/test_render_groups.py": (
        "render group fixtures name the harnesses that share a folder",
        ["codex, copilot"],
    ),
    "groom/tests/_dispatch_support.py": (
        "a select param fixture with two options",
        ["claude, codex"],
    ),
    "groom/tests/test_dispatch.py": (
        "a select param fixture with two options",
        ["claude, codex", "claude, codex"],
    ),
    "groom/tests/test_dispatch_cli_options.py": (
        "an explicit option list fixture",
        ["claude, codex", "claude, codex"],
    ),
    "groom/tests/test_tui_dispatch_enqueue.py": (
        "a select param fixture with two options",
        ["claude, codex"],
    ),
    "groom/tests/test_profile.py": (
        "a usage summary fixture with two backends",
        ["claude, opencode"],
    ),
    "paddock/tests/test_sandbox.py": (
        "a config that names two CLIs on purpose",
        ["claude, opencode"],
    ),
}


def _excluded(path: str) -> bool:
    parts = Path(path).parts
    return path == DEFINITION or "_vendor" in parts or parts[-1] in EXCLUDED_FILES


def _root() -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is absent")
    done = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        pytest.skip("not inside a git checkout")
    return Path(done.stdout.strip())


def _hits(root: Path, registry: frozenset[str], paths: list[str]) -> list[str]:
    found: list[str] = []
    for path in paths:
        file = root / path
        if _excluded(path) or file.is_symlink() or not file.is_file():
            continue
        try:
            tree = ast.parse(file.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, SyntaxError):
            continue
        listed: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Tuple | ast.List | ast.Set):
                continue
            named = sorted(
                {
                    element.value
                    for element in node.elts
                    if isinstance(element, ast.Constant)
                    and isinstance(element.value, str)
                    and element.value in registry
                }
            )
            if len(named) >= 2:
                listed.append((node.lineno, ", ".join(named)))
        allowed = sorted(ALLOWED.get(path, ("", []))[1])
        if sorted(names for _, names in listed) == allowed:
            continue
        found.extend(f"{path}:{line} {names}" for line, names in sorted(listed))
    return found


def test_no_tracked_file_hand_writes_a_list_of_harness_names() -> None:
    root = _root()
    listed = subprocess.run(
        ["git", "ls-files", "-z", "*.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    hits = _hits(
        root, frozenset(names()), [path for path in listed.split("\0") if path]
    )
    assert not hits, "a list of harness names is written by hand at:\n" + "\n".join(
        hits
    )


def test_a_list_of_two_registry_names_is_flagged_and_dict_keys_are_not(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.py").write_text(
        'X = ("a", "b", "z")\nY = {"a": 1, "b": 2}\nZ = ["a", 1]\nW = {"b", "a"}\n',
        encoding="utf-8",
    )
    assert _hits(tmp_path, frozenset({"a", "b"}), ["a.py"]) == [
        "a.py:1 a, b",
        "a.py:4 a, b",
    ]


def test_an_allowed_file_that_gains_a_list_is_flagged(tmp_path: Path) -> None:
    path = "paddock/tests/test_sandbox.py"
    (tmp_path / path).parent.mkdir(parents=True)
    (tmp_path / path).write_text(
        'X = ("claude", "opencode")\nY = ("claude", "opencode")\n', encoding="utf-8"
    )
    assert _hits(tmp_path, frozenset({"claude", "opencode"}), [path]) == [
        f"{path}:1 claude, opencode",
        f"{path}:2 claude, opencode",
    ]


def test_the_registry_definition_and_vendored_copies_are_not_searched(
    tmp_path: Path,
) -> None:
    for path in (DEFINITION, "x/_vendor/m.py"):
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('X = ("a", "b")\n', encoding="utf-8")
    assert _hits(tmp_path, frozenset({"a", "b"}), [DEFINITION, "x/_vendor/m.py"]) == []
