"""`ostler scaffold` — hierarchy-respecting node creation (docs/okf-ui-support §9)."""

from __future__ import annotations

from pathlib import Path

from ostler import fmt, scaffold
from ostler.cli import main
from ostler.model import load

from conftest import write


def test_scaffold_file_level_screen_placement(repo: Path):
    res = scaffold.scaffold(load(repo), "screen", "changes-view", service="groom")
    assert res.ok
    path = repo / "docs/features/groom/gui/screens/changes-view.md"
    assert path.exists()
    text = path.read_text()
    assert text.startswith("---\ntype: screen\nslug: changes-view\ntitle: changes-view\n---\n")
    # loads back as a screen node
    assert load(repo).ui_nodes_of_type("screen")[0].id.endswith("changes-view.md")


def test_scaffold_cli_emits_required_section_and_bullets(repo: Path):
    scaffold.scaffold(load(repo), "cli", "workhorse", service="workhorse", title="workhorse")
    text = (repo / "docs/features/workhorse/workhorse.md").read_text()
    assert "- binary:" in text
    assert "- code:" in text
    assert "## Commands" in text          # required_sections skeleton


def test_scaffold_file_requires_service(repo: Path):
    res = scaffold.scaffold(load(repo), "screen", "x")
    assert not res.ok and "requires --service" in res.message


def test_scaffold_section_inserts_under_heading(repo: Path):
    scaffold.scaffold(load(repo), "screen", "changes-view", service="groom")
    res = scaffold.scaffold(load(repo), "interaction", "click-file",
                            in_file="groom/gui/screens/changes-view.md")
    assert res.ok
    graph = load(repo)
    inter = graph.ui_nodes_of_type("interaction")
    assert [i.anchor for i in inter] == ["click-file"]
    # ordered required bullet stubs present
    text = (repo / "docs/features/groom/gui/screens/changes-view.md").read_text()
    assert "## Interactions" in text
    assert "- on:" in text and "- trigger:" in text and "- does:" in text


def test_scaffold_section_creates_heading_if_absent(repo: Path):
    write(repo / "docs/features/groom/http/server.md",
          "---\ntype: server\nslug: s\ntitle: S\n---\n# S\n\n- code: `app.py`\n")
    res = scaffold.scaffold(load(repo), "endpoint", "get-worker",
                            in_file="groom/http/server.md")
    assert res.ok
    text = (repo / "docs/features/groom/http/server.md").read_text()
    assert "## Endpoints" in text and "### get-worker" in text


def test_scaffold_section_requires_in(repo: Path):
    res = scaffold.scaffold(load(repo), "interaction", "x")
    assert not res.ok and "requires --in" in res.message


def test_scaffold_duplicate_section_refused(repo: Path):
    scaffold.scaffold(load(repo), "screen", "cv", service="groom")
    scaffold.scaffold(load(repo), "component", "row", in_file="groom/gui/screens/cv.md")
    res = scaffold.scaffold(load(repo), "component", "row", in_file="groom/gui/screens/cv.md")
    assert not res.ok and "already exists" in res.message


def test_scaffold_output_is_already_canonical(repo: Path):
    scaffold.scaffold(load(repo), "cli", "wh", service="workhorse")
    scaffold.scaffold(load(repo), "command", "run", in_file="workhorse/wh.md")
    # scaffolded shape must already pass `fmt --check` (no reformat needed)
    result = fmt.run_fmt(load(repo), [], check=True)
    assert result.changed == []


def test_scaffold_unknown_type(repo: Path):
    res = scaffold.scaffold(load(repo), "epic", "x", service="s")
    assert not res.ok and "not a UI-profile type" in res.message


def test_scaffold_cli_command_roundtrip(repo: Path):
    assert main(["-C", str(repo), "scaffold", "concept", "diff", "--service", "groom"]) == 0
    assert (repo / "docs/features/groom/concepts/diff.md").exists()


def test_scaffold_runbook_emits_steps_section_and_driver(repo: Path):
    res = scaffold.scaffold(load(repo), "runbook", "web", service="groom")
    assert res.ok
    text = (repo / "docs/features/groom/ops/web.md").read_text()
    assert text.startswith("---\ntype: runbook\n")
    assert "- driver:" in text and "- surfaces:" in text
    assert "## Steps" in text                  # required_sections skeleton
    assert load(repo).ui_nodes_of_type("runbook")[0].id.endswith("ops/web.md")


def test_scaffold_step_inserts_under_steps_heading(repo: Path):
    scaffold.scaffold(load(repo), "runbook", "web", service="groom")
    res = scaffold.scaffold(load(repo), "step", "serve", in_file="groom/ops/web.md")
    assert res.ok
    text = (repo / "docs/features/groom/ops/web.md").read_text()
    assert "### serve" in text and "- kind:" in text
    assert [s.anchor for s in load(repo).ui_nodes_of_type("step")] == ["serve"]


def test_scaffold_runbook_trio_is_canonical(repo: Path):
    scaffold.scaffold(load(repo), "environment", "local", service="groom")
    scaffold.scaffold(load(repo), "runbook", "web", service="groom")
    scaffold.scaffold(load(repo), "step", "prepare", in_file="groom/ops/web.md")
    result = fmt.run_fmt(load(repo), [], check=True)
    assert result.changed == []
