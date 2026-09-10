"""Regression guard against the py-tree-sitter 0.26.0 segfault.

The segfault at behavior_go.py:70 (the ``_slice`` call reading ``node.start_byte``)
is reproducible in the workhorse CLI but not in isolation. The bisect of the
libtree-sitter C source between v0.25.10 and v0.27.0 showed no version difference:
all of them segfault the same way. The bug is in py-tree-sitter 0.26.0's Python
binding, not in libtree-sitter.

The bisect the user asked for was on libtree-sitter, in
``/mnt/data/workspace-other/tree-sitter``. We did it, the answer was "the C
library is not the cause." The fix in ostler/pyproject.toml
(``tree-sitter>=0.25,<0.26``) prevents the bug by pinning py-tree-sitter to a
version that does not have it. This test asserts that pin is in place and that
the in-process reproduction does not crash.

If a future release of py-tree-sitter (>=0.27) fixes the binding bug, this test
should be updated to widen the upper bound. The bd8d0fd1 history line in the
ostler pyproject is the right place to track that.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

OSTLER_PYPROJECT = Path("/mnt/data/workspace/stablemate/ostler/pyproject.toml")
SOURCE_ROOT = Path("/mnt/data/workspace/example/api")


def test_ostler_pins_tree_sitter_below_0_26() -> None:
    """ostler/pyproject.toml must constrain tree-sitter to <0.26.

    The 0.26.0 Python binding segfaults inside the okf-builder behavior audit's
    Go evidence extractor. The constraint is in ostler/pyproject.toml at the
    ``bd8d0fd1`` line. Removing or widening it is what allows the bad version in.
    """
    content = OSTLER_PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'"tree-sitter([^"]+)"', content)
    assert match is not None, (
        "ostler/pyproject.toml must declare a tree-sitter version constraint"
    )
    constraint = match.group(1)
    assert "<0.26" in constraint or "<0.27" in constraint, (
        f"tree-sitter constraint must exclude 0.26+: got {constraint!r}"
    )


def test_installed_tree_sitter_lacks_zero_twenty_six_marker() -> None:
    """The installed py-tree-sitter must be a 0.25.x version.

    py-tree-sitter 0.26.0 added ``__version__`` to the binding; the 0.25.x
    versions do not have it. The absence of the symbol is the most reliable
    in-process signal of a 0.25.x install. We assert it so a CI upgrade that
    silently bumps to 0.26.0 is caught here rather than at the segfault.

    The ``_binding`` access is wrapped in a ``try/except`` because the symbol
    is generated at import time by the C extension and type-checkers cannot
    see it on the stubs tree-sitter ships — at runtime the lookup is the
    ground truth.
    """
    import tree_sitter

    binding = getattr(tree_sitter, "_binding", None)
    has_version = binding is not None and hasattr(binding, "__version__")

    assert not has_version, (
        "installed tree-sitter has __version__ on the binding — that landed in 0.26.0 "
        "and the okf-builder behavior audit segfaults on 0.26.0 in the workflow context; "
        "pin ostler/pyproject.toml's tree-sitter upper bound before upgrading"
    )


def test_extract_evidence_across_many_go_files_does_not_crash() -> None:
    """The in-process reproduction of the workflow's evidence walk.

    The workflow segfaults in this path. Standalone it does not, in 0.25.x. We
    keep the standalone test here so the regression is visible — a future change
    that re-introduces the segfault on 0.25.x (or on a 0.26.x whose binding is
    fixed) will fail this test.

    Skipped when the api repo is not in the standard local checkout.
    """
    if not SOURCE_ROOT.exists():
        pytest.skip(f"source tree {SOURCE_ROOT} not present in this checkout")
    files = sorted(SOURCE_ROOT.rglob("*.go"))
    if len(files) < 32:
        pytest.skip(f"only {len(files)} Go files at {SOURCE_ROOT}; not a meaningful stress test")
    import shutil
    import tempfile

    from ostler.behavior import extract_evidence

    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "api"
        target.mkdir()
        paths: list[str] = []
        for f in files:
            rel = f.relative_to(SOURCE_ROOT)
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, dst)
            paths.append(rel.as_posix())
        inv = extract_evidence(target, paths)
        assert inv.files
        assert inv.candidates
