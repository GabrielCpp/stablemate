"""Tests for presence-based prompt *flavor* overrides in render()."""
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
    workflow_dir, ctx = _setup(tmp_path)
    out = render("prompts/write-story.md", ctx, workflow_dir)
    assert "Generic authoring instructions." in out
    assert "End of base." in out
    assert "REPO RULE" not in out


def test_override_fills_block_keeps_base(tmp_path):
    workflow_dir, ctx = _setup(tmp_path)
    _write_override(Path(ctx["_repo_root"]))
    out = render("prompts/write-story.md", ctx, workflow_dir)
    assert "Generic authoring instructions." in out
    assert "End of base." in out
    assert "REPO RULE: cite a legacy source per row." in out


def test_override_dir_without_file_for_node_is_base(tmp_path):
    workflow_dir, ctx = _setup(tmp_path)
    _write_override(Path(ctx["_repo_root"]), node="review-coverage.md", content="irrelevant")
    out = render("prompts/write-story.md", ctx, workflow_dir)
    assert "Generic authoring instructions." in out
    assert "REPO RULE" not in out


def test_no_repo_root_renders_base(tmp_path):
    workflow_dir, _ = _setup(tmp_path)
    out = render("prompts/write-story.md", {}, workflow_dir)
    assert "Generic authoring instructions." in out
    assert "REPO RULE" not in out



FLOW_OVERRIDE = (
    '{% extends "dev/prompts/write-story.md" %}\n'
    "{% block repo_authoring_rules %}FLOW RULE: dev only.{% endblock %}\n"
)


def _setup_flow(base: Path) -> tuple[Path, dict]:
    """The same workflow with the prompt inside the flow package that renders it."""
    workflow_dir, ctx = _setup(base)
    (workflow_dir / "dev" / "prompts").mkdir(parents=True)
    (workflow_dir / "dev" / "prompts" / "write-story.md").write_text(BASE)
    return workflow_dir, ctx


def test_flow_keyed_override_wins(tmp_path):
    workflow_dir, ctx = _setup_flow(tmp_path)
    flow_dir = Path(ctx["_repo_root"]) / ".agents" / "flavors" / "author" / "dev"
    flow_dir.mkdir(parents=True)
    (flow_dir / "write-story.md").write_text(FLOW_OVERRIDE)
    out = render("dev/prompts/write-story.md", ctx, workflow_dir)
    assert "Generic authoring instructions." in out
    assert "FLOW RULE: dev only." in out


def test_basename_override_still_activates_for_a_flow_prompt(tmp_path):
    workflow_dir, ctx = _setup_flow(tmp_path)
    _write_override(
        Path(ctx["_repo_root"]),
        content=FLOW_OVERRIDE.replace("FLOW RULE: dev only.", "REPO RULE: applies everywhere."),
    )
    out = render("dev/prompts/write-story.md", ctx, workflow_dir)
    assert "REPO RULE: applies everywhere." in out


def test_flow_keyed_override_beats_basename(tmp_path):
    workflow_dir, ctx = _setup_flow(tmp_path)
    repo_root = Path(ctx["_repo_root"])
    _write_override(
        repo_root,
        content=FLOW_OVERRIDE.replace("FLOW RULE: dev only.", "REPO RULE: applies everywhere."),
    )
    flow_dir = repo_root / ".agents" / "flavors" / "author" / "dev"
    flow_dir.mkdir(parents=True)
    (flow_dir / "write-story.md").write_text(FLOW_OVERRIDE)
    out = render("dev/prompts/write-story.md", ctx, workflow_dir)
    assert "FLOW RULE: dev only." in out
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
