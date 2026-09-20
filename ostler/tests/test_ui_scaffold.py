"""`ostler scaffold` — hierarchy-respecting node creation (docs/okf-ui-support §9)."""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest
from ostler import doctor, fmt, registry, scaffold
from ostler.cli import main
from ostler.model import load

from conftest import write

#: Every `kind == "section"` type in the registry, mapped to a file-level type whose page
#: can host it. A section scaffolds into an existing file, so the host has to be created
#: first; `registry.UI_TYPES` names eight such types, where `scaffold.py`'s own module
#: docstring lists five.
_SECTION_HOSTS: dict[str, str] = {
    "component": "screen",
    "interaction": "screen",
    "command": "cli",
    "endpoint": "server",
    "invocation": "server",
    "method": "concept",
    "field": "format",
    "step": "runbook",
}

#: Every scaffoldable type, read off the registry rather than listed here, so a type added
#: later is covered without anyone remembering this file. `untyped` is excluded because it
#: is not authorable: it is what a heading naming no type is called, not something
#: `scaffold` can be asked for.
SCAFFOLDABLE_TYPES = sorted(t.name for t in registry.UI_TYPES if t.name != "untyped")


def _scaffold_type(repo: Path, name: str) -> Path:
    """Scaffold one instance of `name`, creating a host file first if it is section-level.

    Returns the path of the file the type's own content landed in, so the caller can diff
    exactly that file against what `fmt` would make of it.
    """
    uitype = registry.ui_type(name)
    assert uitype is not None
    if uitype.kind == "file":
        res = scaffold.scaffold(load(repo), name, name, service="acme")
        assert res.ok, res.message
        return res.paths[0]
    host = _SECTION_HOSTS[name]
    host_res = scaffold.scaffold(load(repo), host, host, service="acme")
    assert host_res.ok, host_res.message
    in_file = host_res.paths[0].relative_to(load(repo).doc_roots["features"]).as_posix()
    res = scaffold.scaffold(load(repo), name, name, in_file=in_file)
    assert res.ok, res.message
    return host_res.paths[0]


@pytest.mark.parametrize("type_name", SCAFFOLDABLE_TYPES)
def test_scaffold_output_is_canonical_for_every_type(repo: Path, type_name: str):
    """The claim in `scaffold.py`'s module docstring — scaffolded output already matches
    `ostler fmt` — is a guarantee held *by construction* across two separate modules
    (`scaffold.py` composes, `fmt.py` canonicalises) and nothing forces them to agree.
    `scaffold.py`'s own `_bullet_stubs` docstring records that the guarantee already failed
    once, for a subset of stub families. This asserts it for every type the registry
    declares, deriving the list from `registry.UI_TYPES` rather than naming types by hand,
    so a type added later is covered automatically.
    """
    target = _scaffold_type(repo, type_name)
    before = target.read_text(encoding="utf-8")
    after = fmt.format_text(before)
    if after != before:
        diff = "\n".join(difflib.unified_diff(
            before.splitlines(), after.splitlines(),
            fromfile="scaffolded", tofile="fmt-canonical", lineterm="",
        ))
        pytest.fail(f"scaffolded '{type_name}' is not fmt-canonical:\n{diff}")


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


def test_scaffold_endpoints_bare_channel_and_message_raise_no_new_finding(repo: Path):
    """The corpus shape today: every book's `channel:`/`message:` is a bare scaffold stub with
    no value, so widening their grammar (locator/address on `channel:`, entries/normative on
    `message:`) must be invisible until a book actually writes content into one. `doctor` finds
    the same two unrelated things it always did — nothing naming `channel` or `message`."""
    write(repo / "docs/features/acme/server.md",
          "---\ntype: server\ntitle: API\n---\n# API\n\n- code: `app/server.py`\n")
    write(repo / "app/server.py", "x = 1\n")
    res = scaffold.scaffold(load(repo), "endpoint", "get-worker", in_file="acme/server.md")
    assert res.ok

    report = doctor.run(load(repo))

    assert {f.code for f in report.findings} == {
        "unstamped-citation", "runbook-missing", "unclassified-seed",
    }
    assert not any("channel" in f.message or "message" in f.message for f in report.findings)


def test_scaffold_section_requires_in(repo: Path):
    res = scaffold.scaffold(load(repo), "interaction", "x")
    assert not res.ok and "requires --in" in res.message


def test_scaffold_duplicate_section_refused(repo: Path):
    scaffold.scaffold(load(repo), "screen", "cv", service="groom")
    scaffold.scaffold(load(repo), "component", "row", in_file="groom/gui/screens/cv.md")
    res = scaffold.scaffold(load(repo), "component", "row", in_file="groom/gui/screens/cv.md")
    assert not res.ok and "already exists" in res.message


def test_scaffold_fixture_writes_to_the_path_a_book_loads_fixtures_from(repo: Path):
    """`context="fixtures"` (fixed from a stray `qa/fixtures`) must place the file where the
    fixture node grammar's own id convention says: `docs/features/<surface>/fixtures/<name>.md`,
    no `qa/` segment — and the book must find it back there as a `fixture` node.
    """
    res = scaffold.scaffold(load(repo), "fixture", "seeded-acme", service="acme")
    assert res.ok
    path = repo / "docs/features/acme/fixtures/seeded-acme.md"
    assert path.exists()
    graph = load(repo)
    [node] = graph.ui_nodes_of_type("fixture")
    assert node.id.endswith("acme/fixtures/seeded-acme.md")


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
