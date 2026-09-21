from __future__ import annotations

from pathlib import Path

from ostler import doctor, markdown, model, trace
from ostler.model import load

from conftest import write


BULLET_CODE_SPAN_DOC = """# Section

## Notes

- `GET /a:b` is the route
- does: fetch `https://x` and render it
- The `:443` counterpart: same TLS setup as before
- answers `200` with `{"status": "ok"}` as soon as the process is serving
"""


def test_bullet_pairs_skips_a_bullet_whose_only_colon_is_inside_a_code_span():
    section = markdown.split(BULLET_CODE_SPAN_DOC).section("Notes")
    pairs = model._bullet_pairs(section)
    assert pairs == [
        ("does", "fetch `https://x` and render it", 1),
        ("the `:443` counterpart", "same TLS setup as before", 2),
    ]


def test_meta_from_bullets_skips_bullets_with_no_key_outside_a_code_span():
    section = markdown.split(BULLET_CODE_SPAN_DOC).section("Notes")
    meta = model._meta_from_bullets(section)
    assert meta == {
        "does": "fetch `https://x` and render it",
        "the `:443` counterpart": "same TLS setup as before",
    }


def test_markdown_roundtrip_identity():
    text = "---\nsurface: a/b\nroute: /a/b\n---\n# Title\n\nbody\n"
    doc = markdown.split(text)
    assert doc.frontmatter is not None
    assert doc.frontmatter["surface"] == "a/b"
    assert doc.render() == text


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


def test_a_typeless_prose_file_under_features_is_not_a_feature_record(repo: Path):
    """Membership in the OKF book is a claim the file makes (a declared `type:`), not a property of sitting under `docs/features/` -- the same rule `_load_milestones` already applies via `registry.base_type(registry.type_of(fm))`, and the same rule `doctor._check_conformance` enforces independently as `okf-missing-type`."""
    write(repo / "docs/features/area/scratch-note.md",
          "# Just some notes\n\nNo frontmatter here, plain prose scratch note.\n")
    graph = load(repo)
    slugs = {r.slug for r in graph.features}
    assert "scratch-note" not in slugs
    assert not any("scratch-note" in str(n.path) for n in graph.ui_nodes)
    assert {"rec", "rec2"} <= slugs

    report = doctor.run(graph)
    missing_type = {f.path for f in report.findings if f.code == "okf-missing-type"}
    assert "docs/features/area/scratch-note.md" in missing_type


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
    """`flags:` is `entries=True` (`registry.BulletKey`): each direct child is one flag, and that flag's own `type:`/`required:`/`default:` children are its properties, not further flags."""
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


def test_an_entrys_properties_land_on_the_entry_and_not_in_meta(tmp_path: Path) -> None:
    """Stopping at the entry kept the two shapes apart; it also dropped the properties."""
    (tmp_path / "docs/features/area").mkdir(parents=True)
    (tmp_path / "docs/features/area/cli.md").write_text(
        "---\ntype: cli\nslug: c\ntitle: C\n---\n# C\n\n"
        "## Commands\n\n### serve\n"
        "- usage: `c serve [--host HOST] [--port PORT]`\n"
        "- flags:\n"
        "  - `--host HOST`\n"
        "    - type: string\n"
        "    - default: `0.0.0.0`\n"
        "  - `--port PORT`\n"
        "    - type: integer\n"
        "    - required: false\n"
        "    - default: `8787`\n"
        "    - The TCP port to listen on.\n",
        encoding="utf-8")
    graph = load(tmp_path)
    node = next(n for n in graph.ui_nodes if n.type == "command")

    host, port = node.entries["flags"]
    assert host.properties == {"type": "string", "default": "`0.0.0.0`"}
    assert port.headline == "`--port PORT`"
    assert port.properties == {"type": "integer", "required": "false", "default": "`8787`"}

    assert node.meta["flags"] == [entry.headline for entry in node.entries["flags"]]
    assert "type" not in node.meta and "default" not in node.meta


def test_a_nested_key_that_is_not_an_entries_key_keeps_its_whole_subtree(tmp_path: Path) -> None:
    """`does:` is `nested=True` and *not* `entries=True`: its children are claims all the way down, so every descendant is a value and none of them is a property of another."""
    (tmp_path / "docs/features/area").mkdir(parents=True)
    (tmp_path / "docs/features/area/screen.md").write_text(
        "---\ntype: screen\nslug: s\ntitle: S\nroute: /s\n---\n# S\n\n"
        "## Interactions\n\n### submit\n"
        "- trigger: click [go](#go)\n"
        "- does:\n"
        "  - the form is submitted\n"
        "    - and the row appears\n",
        encoding="utf-8")
    graph = load(tmp_path)
    node = next(n for n in graph.ui_nodes if n.type == "interaction")
    assert node.meta["does"] == ["the form is submitted", "and the row appears"]
    assert node.entries == {}
