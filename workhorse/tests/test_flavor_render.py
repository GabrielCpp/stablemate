"""Tests for presence-based prompt *flavor* overrides in render().

A consuming repo extends a base node prompt by dropping a same-named file at
``<repo_root>/.agents/flavors/<workflow>/<node>.md``. It ``{% extends %}`` the base
and fills the base's named blocks; with no such file the base renders unchanged
(its blocks extend to nothing). The engine resolves the override across a
multi-root Jinja loader (flavor dir + workflow dir) so the ``{% extends %}`` finds
the base prompt.

Run: ./.venv/bin/python tests/test_flavor_render.py   (or via pytest)
"""
from __future__ import annotations

from pathlib import Path

from workhorse.templates import render


BASE = (
    "# Write the story\n"
    "Generic authoring instructions.\n"
    "{% block repo_authoring_rules %}{% endblock %}\n"
    "End of base.\n"
)

OVERRIDE = (
    '{% extends "prompts/write-story.md" %}\n'
    "{% block repo_authoring_rules %}REPO RULE: cite a legacy source per row.{% endblock %}\n"
)


def _setup(base: Path) -> tuple[Path, dict]:
    """Create a workflow dir named 'author' with a base prompt; return (workflow_dir, ctx)."""
    workflow_dir = base / "lib" / "workflows" / "author"
    (workflow_dir / "prompts").mkdir(parents=True)
    (workflow_dir / "prompts" / "write-story.md").write_text(BASE)
    repo_root = base / "repo"
    repo_root.mkdir(parents=True)
    return workflow_dir, {"_repo_root": str(repo_root)}


def _write_override(repo_root: Path, node: str = "write-story.md", content: str = OVERRIDE) -> None:
    d = repo_root / ".agents" / "flavors" / "author"
    d.mkdir(parents=True, exist_ok=True)
    (d / node).write_text(content)


def test_plain_renders_base_unchanged(tmp_path):
    # No override dir at all -> base renders; empty block extends to nothing.
    workflow_dir, ctx = _setup(tmp_path)
    out = render("prompts/write-story.md", ctx, workflow_dir)
    assert "Generic authoring instructions." in out
    assert "End of base." in out
    assert "REPO RULE" not in out


def test_override_fills_block_keeps_base(tmp_path):
    # Override present -> base body intact AND the named block is filled.
    workflow_dir, ctx = _setup(tmp_path)
    _write_override(Path(ctx["_repo_root"]))
    out = render("prompts/write-story.md", ctx, workflow_dir)
    assert "Generic authoring instructions." in out  # base body intact
    assert "End of base." in out
    assert "REPO RULE: cite a legacy source per row." in out  # block filled via {% extends %}


def test_override_dir_without_file_for_node_is_base(tmp_path):
    # A flavor file exists for a DIFFERENT node only -> this node renders the base.
    workflow_dir, ctx = _setup(tmp_path)
    _write_override(Path(ctx["_repo_root"]), node="review-coverage.md", content="irrelevant")
    out = render("prompts/write-story.md", ctx, workflow_dir)
    assert "Generic authoring instructions." in out
    assert "REPO RULE" not in out


def test_no_repo_root_renders_base(tmp_path):
    # Without _repo_root in context the engine cannot look up overrides -> base.
    workflow_dir, _ = _setup(tmp_path)
    out = render("prompts/write-story.md", {}, workflow_dir)
    assert "Generic authoring instructions." in out
    assert "REPO RULE" not in out


if __name__ == "__main__":
    import tempfile

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(Path(td))
                print(f"PASS  {fn.__name__}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
