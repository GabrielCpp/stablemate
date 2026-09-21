"""Tests for the envelope/body split in render()."""
from __future__ import annotations

from pathlib import Path

from workhorse.templates import render

ENVELOPE = (
    "# Contract\n"
    "Provided: {{ story }}\n"
    "{% include body_template %}\n"
    "Return JSON.\n"
)


def _setup(base: Path) -> tuple[Path, Path]:
    workflow_dir = base / "lib" / "workflows" / "coder"
    (workflow_dir / "prompts").mkdir(parents=True)
    (workflow_dir / "prompts" / "dev-fix.md").write_text(ENVELOPE)
    body_dir = base / "library" / "prompts" / "coder"
    body_dir.mkdir(parents=True)
    (body_dir / "dev-fix.md").write_text("BODY for {{ story }}\n")
    return workflow_dir, body_dir


def test_the_envelope_includes_a_body_it_does_not_ship(tmp_path):
    workflow_dir, body_dir = _setup(tmp_path)
    ctx = {
        "story": "expense-list",
        "_body_dir": str(body_dir),
        "body_template": "body/dev-fix.md",
    }

    out = render("prompts/dev-fix.md", ctx, workflow_dir)

    assert "Provided: expense-list" in out
    assert "BODY for expense-list" in out
    assert out.index("Provided") < out.index("BODY") < out.index("Return JSON.")


def test_a_body_cannot_shadow_a_template_the_workflow_ships(tmp_path):
    """The body lives under its own `body/` namespace, so a library file named like one of the workflow's own prompts is inert rather than an override nobody declared."""
    workflow_dir, body_dir = _setup(tmp_path)
    (body_dir / "prompts").mkdir()
    (body_dir / "prompts" / "dev-fix.md").write_text("HIJACKED\n")
    ctx = {"story": "s", "_body_dir": str(body_dir), "body_template": "body/dev-fix.md"}

    out = render("prompts/dev-fix.md", ctx, workflow_dir)

    assert "HIJACKED" not in out
    assert "Contract" in out


def test_a_body_named_for_its_envelope_does_not_include_the_envelope(tmp_path):
    """The body is named for the role, and so is the envelope."""
    workflow_dir, body_dir = _setup(tmp_path)
    ctx = {"story": "s", "_body_dir": str(body_dir), "body_template": "body/dev-fix.md"}

    out = render(workflow_dir / "prompts" / "dev-fix.md", ctx, workflow_dir)

    assert "BODY for s" in out
    assert out.count("Return JSON.") == 1


def test_no_body_dir_leaves_rendering_exactly_as_it_was(tmp_path):
    workflow_dir, _ = _setup(tmp_path)
    (workflow_dir / "prompts" / "plain.md").write_text("just the envelope\n")

    assert render("prompts/plain.md", {}, workflow_dir) == "just the envelope\n"
