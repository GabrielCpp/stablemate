from __future__ import annotations

from pathlib import Path

from ostler import markdown, trace
from ostler.model import load


def test_markdown_roundtrip_identity():
    text = "---\nsurface: a/b\nroute: /a/b\n---\n# Title\n\nbody\n"
    doc = markdown.split(text)
    assert doc.frontmatter is not None
    assert doc.frontmatter["surface"] == "a/b"
    assert doc.render() == text  # exact round-trip, no churn


def test_markdown_no_frontmatter():
    text = "# Just a heading\n\nbody only\n"
    doc = markdown.split(text)
    assert not doc.has_frontmatter
    assert doc.render() == text


def test_exploration_profile_when_no_epics(tmp_path: Path):
    (tmp_path / "docs/features/area").mkdir(parents=True)
    (tmp_path / "docs/features/area/note.md").write_text(
        "---\ntype: feature\nslug: note\ntitle: Note\n---\nhi\n", encoding="utf-8")
    graph = load(tmp_path)
    assert graph.profile == "exploration"
    assert graph.org_name == tmp_path.name
    assert len(graph.features) == 1


def test_org_name_override_from_config(tmp_path: Path):
    (tmp_path / "docs/features").mkdir(parents=True)
    (tmp_path / "ostler.yml").write_text(
        "organization:\n  name: custom-org\n", encoding="utf-8")
    graph = load(tmp_path)
    assert graph.org_name == "custom-org"


def test_trace_story_and_seed(repo: Path):
    graph = load(repo)
    lines, found = trace.run(graph, "01-foo")
    assert found and any("seed-a1" in ln for ln in lines)

    lines, found = trace.run(graph, "seed-a1")
    assert found and any("covered by story" in ln and "01-foo" in ln for ln in lines)

    lines, found = trace.run(graph, "does-not-exist")
    assert not found


def test_a_flags_entry_with_its_own_properties_parses_as_one_value(tmp_path: Path) -> None:
    """`flags:` is `entries=True` (`registry.BulletKey`): each direct child is one flag, and
    that flag's own `type:`/`required:`/`default:` children are its properties, not further
    flags.

    Before the `_nested_values` split, `_bullet_pairs`/`_meta_from_bullets` walked the whole
    subtree regardless of the key's grammar — `flags:` was not even marked `nested=True` in
    the registry, so a command with three flags, each carrying three property children and a
    prose paragraph, flattened to fifteen `flags` values instead of three (the shape seen in
    `docs/features/groom/groom-cli.md#serve`).
    """
    (tmp_path / "docs/features/area").mkdir(parents=True)
    (tmp_path / "docs/features/area/cli.md").write_text(
        "---\ntype: cli\nslug: c\ntitle: C\n---\n# C\n\n"
        "## Commands\n\n### serve\n"
        "- usage: `c serve [--host HOST] [--port PORT]`\n"
        "- flags:\n"
        "  - `--host HOST`\n"
        "    - type: string\n"
        "    - required: false\n"
        "    - default: `0.0.0.0`\n"
        "    - The network interface address to bind.\n"
        "  - `--port PORT`\n"
        "    - type: integer\n"
        "    - required: false\n"
        "    - default: `8787`\n"
        "    - The TCP port to listen on.\n",
        encoding="utf-8")
    graph = load(tmp_path)
    node = next(n for n in graph.ui_nodes if n.type == "command")
    assert node.meta.get("flags") == ["`--host HOST`", "`--port PORT`"]
