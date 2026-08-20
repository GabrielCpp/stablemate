"""A skill's `references/` and `scripts/` ship with it instead of becoming skills.

Before this, the library could express exactly one thing per skill: a single SKILL.md.
That forced two workarounds on authors. Long-form material a body should *point at*
had to become a sibling skill (`go-service` + `go-service-examples`), burning a
library-wide-unique name on half a topic and loading a `applyTo` of its own. And a
procedure's commands had to be retyped by the agent from a fenced block, because a
script beside the skill was never copied into the repo at all.

So the loader has to skip these directories (or every reference fragment registers as a
top-level skill and starts colliding with real names), the renderer has to emit them
beside the generated SKILL.md at the same relative path the library uses (or a link
that resolves in the library breaks once installed), and scripts have to arrive
verbatim and executable (or `./scripts/check.sh` fails at the shell).

    uv run pytest tests/test_skill_assets.py
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from farrier.install import (
    Renderer,
    Source,
    asset_owner,
    check_outputs,
    install_outputs,
    load_sources,
    skill_assets,
)


def _library(tmp_path: Path) -> Path:
    root = tmp_path / "library" / "skills"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _skill(root: Path, name: str, body: str = "Rules.\n") -> Path:
    """A library skill directory with a minimal SKILL.md, returned for asset writes."""
    skill_dir = root / "stack" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: A {name} skill\n---\n\n# {name}\n\n{body}",
        encoding="utf-8",
    )
    return skill_dir


def _write(skill_dir: Path, rel: str, content: str) -> Path:
    path = skill_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


def _renderer(tmp_path: Path, root: Path, names: list[str]) -> Renderer:
    skills = [s for s in load_sources(root, "skill") if s.id.split("/")[-1] in names]
    return Renderer(
        repo=tmp_path,
        prefix="demo",
        repo_config={},
        template_values={},
        skills=skills,
        prompts=[],
    )


# --- the loader: assets are not skills -------------------------------------------


def test_reference_markdown_does_not_register_as_its_own_skill(tmp_path):
    root = _library(tmp_path)
    skill_dir = _skill(root, "go-service")
    _write(skill_dir, "references/examples.md", "# Examples\n")

    ids = {source.id for source in load_sources(root, "skill")}
    assert ids == {"stack/go-service"}


def test_readme_does_not_register_as_a_source(tmp_path):
    """A tree's README is prose for a human, not a skill named `readme`.

    It sits at the root of a kind's directory, so nothing about a skill's own layout
    excludes it — and once loaded it takes a library-wide-unique name that a pack glob
    can select and every "unknown name; here is what exists" catalog advertises.
    """
    root = _library(tmp_path)
    _skill(root, "go-service")
    (root / "README.md").write_text("# Skills\n\nWhat lives here.\n", encoding="utf-8")

    assert {source.id for source in load_sources(root, "skill")} == {"stack/go-service"}


def test_scripts_are_not_loaded_as_sources(tmp_path):
    root = _library(tmp_path)
    skill_dir = _skill(root, "qa")
    _write(skill_dir, "scripts/notes.md", "# Not a skill\n")

    assert {source.id for source in load_sources(root, "skill")} == {"stack/qa"}


def test_a_references_dir_outside_a_skill_still_holds_skills(tmp_path):
    """`references/` only means *assets* directly inside a skill.

    Elsewhere it is an ordinary library directory, and the name alone must not
    disqualify a SKILL.md sitting under it from being a skill.
    """
    root = _library(tmp_path)
    stray = root / "references" / "docs-style"
    stray.mkdir(parents=True)
    (stray / "SKILL.md").write_text("---\nname: docs-style\n---\n\n# Style\n", "utf-8")

    assert asset_owner(root, stray / "SKILL.md") is None
    assert {source.id for source in load_sources(root, "skill")} == {
        "references/docs-style"
    }


def test_nested_skill_dirs_do_not_swallow_each_others_assets(tmp_path):
    root = _library(tmp_path)
    skill_dir = _skill(root, "go")
    asset = _write(skill_dir, "references/deep/nested.md", "# Deep\n")

    assert asset_owner(root, asset) == skill_dir
    assert [a.rel for a in skill_assets(next(iter(load_sources(root, "skill"))))] == [
        "references/deep/nested.md"
    ]


def test_running_a_bundled_script_does_not_bundle_its_bytecode(tmp_path):
    """A script asset is meant to be run, and running it writes `__pycache__` beside it.

    Nobody authored those bytes and they are not text, so treating them as an asset takes
    the whole install pipeline down — or, in `--check`, downgrades the generated-file
    guard to a skip on exactly the machines where the scripts get used.
    """
    root = _library(tmp_path)
    skill_dir = _skill(root, "go")
    _write(skill_dir, "scripts/check.py", "print('ok')\n")
    cache = skill_dir / "scripts" / "__pycache__"
    cache.mkdir()
    (cache / "check.cpython-312.pyc").write_bytes(b"\x00\x01binary")

    assert [a.rel for a in skill_assets(next(iter(load_sources(root, "skill"))))] == [
        "scripts/check.py"
    ]


def test_a_flat_source_bundles_nothing(tmp_path):
    """Bundling is a property of the directory form — a flat `foo.md` has no directory."""
    root = _library(tmp_path)
    flat = root / "legacy.md"
    flat.write_text("# Legacy\n", encoding="utf-8")
    source = Source(kind="skill", path=flat, rel="legacy.md", id="legacy")

    assert skill_assets(source) == []


# --- the renderer: assets land beside the generated SKILL.md ----------------------


def test_reference_installs_next_to_the_skill_under_every_adapter(tmp_path):
    root = _library(tmp_path)
    skill_dir = _skill(root, "go-service")
    _write(skill_dir, "references/examples.md", "# Examples\n\nA service looks like…\n")
    renderer = _renderer(tmp_path, root, ["go-service"])

    outputs = renderer.render(
        agents={"claude": True, "codex": True, "copilot": True}, roots=set()
    )

    for adapter in (".claude/skills", ".agents/skills", ".github/skills"):
        path = tmp_path / adapter / "demo-go-service" / "references" / "examples.md"
        assert path in outputs, f"reference missing from {adapter}"
        assert "A service looks like" in outputs[path]


def test_a_reference_keeps_the_path_the_library_author_wrote(tmp_path):
    """The link in a SKILL.md body is the same string in the library and installed.

    This is the whole ergonomic claim of bundling: an author writes
    `references/examples.md` because that is what they see on disk, and it resolves
    without farrier having to rewrite links or the author having to guess an adapter.
    """
    root = _library(tmp_path)
    skill_dir = _skill(root, "go", body="See [examples](references/examples.md).\n")
    _write(skill_dir, "references/examples.md", "# Examples\n")
    renderer = _renderer(tmp_path, root, ["go"])

    outputs = renderer.render(agents={"claude": True}, roots=set())
    skill_path = tmp_path / ".claude" / "skills" / "demo-go" / "SKILL.md"
    linked = skill_path.parent / "references" / "examples.md"

    assert "references/examples.md" in outputs[skill_path]
    assert linked in outputs


def test_markdown_references_are_templated_from_their_own_location(tmp_path):
    root = _library(tmp_path)
    skill_dir = _skill(root, "go")
    _skill(root, "testing")
    _write(skill_dir, "references/x.md", 'See {{ instruction_file("testing") }}.\n')
    renderer = _renderer(tmp_path, root, ["go", "testing"])

    outputs = renderer.render(agents={"claude": True}, roots=set())
    rendered = outputs[
        tmp_path / ".claude" / "skills" / "demo-go" / "references" / "x.md"
    ]

    # Relative to the reference's own directory, not the skill's — one level deeper.
    assert "../../demo-testing/SKILL.md" in rendered


def test_a_markdown_reference_carries_resolvable_provenance(tmp_path):
    """A generated copy must redirect edits to the library, references included."""
    root = _library(tmp_path)
    skill_dir = _skill(root, "go")
    _write(skill_dir, "references/x.md", "# X\n")
    renderer = _renderer(tmp_path, root, ["go"])

    outputs = renderer.render(agents={"claude": True}, roots=set())
    rendered = outputs[
        tmp_path / ".claude" / "skills" / "demo-go" / "references" / "x.md"
    ]

    assert rendered.startswith("<!--")
    assert "DO NOT EDIT" in rendered
    assert "library/skills/stack/go/references/x.md" in rendered
    assert "farrier source .claude/skills/demo-go/references/x.md" in rendered


def test_scripts_and_non_markdown_references_are_copied_untouched(tmp_path):
    """A `{{` in a script is its own syntax, and its trailing bytes are its own too."""
    root = _library(tmp_path)
    skill_dir = _skill(root, "qa")
    _write(skill_dir, "scripts/check.sh", '#!/bin/sh\necho "{{ not_a_template }}"\n\n')
    _write(skill_dir, "references/fixture.json", '{"a": 1}\n\n')
    renderer = _renderer(tmp_path, root, ["qa"])

    outputs = renderer.render(agents={"claude": True}, roots=set())
    base = tmp_path / ".claude" / "skills" / "demo-qa"

    assert outputs[base / "scripts" / "check.sh"] == '#!/bin/sh\necho "{{ not_a_template }}"\n\n'
    assert outputs[base / "references" / "fixture.json"] == '{"a": 1}\n\n'


def test_a_binary_asset_is_rejected_by_name(tmp_path):
    root = _library(tmp_path)
    skill_dir = _skill(root, "qa")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
    renderer = _renderer(tmp_path, root, ["qa"])

    with pytest.raises(SystemExit) as excinfo:
        renderer.render(agents={"claude": True}, roots=set())
    assert "diagram.png" in str(excinfo.value)


# --- the write side: verbatim, executable, and checkable --------------------------


def test_an_installed_script_is_executable_and_byte_faithful(tmp_path):
    root = _library(tmp_path)
    skill_dir = _skill(root, "qa")
    _write(skill_dir, "scripts/check.sh", "#!/bin/sh\nexit 0\n\n")
    renderer = _renderer(tmp_path, root, ["qa"])
    outputs = renderer.render(agents={"claude": True}, roots=set())

    install_outputs(tmp_path, outputs)
    installed = tmp_path / ".claude" / "skills" / "demo-qa" / "scripts" / "check.sh"

    assert installed.read_text(encoding="utf-8") == "#!/bin/sh\nexit 0\n\n"
    assert installed.stat().st_mode & 0o111, "script installed without the +x bit"


def test_check_is_clean_right_after_install(tmp_path, capsys):
    root = _library(tmp_path)
    skill_dir = _skill(root, "qa")
    _write(skill_dir, "scripts/check.sh", "#!/bin/sh\nexit 0\n\n")
    _write(skill_dir, "references/notes.md", "# Notes\n")
    renderer = _renderer(tmp_path, root, ["qa"])
    outputs = renderer.render(agents={"claude": True}, roots=set())
    install_outputs(tmp_path, outputs)

    assert check_outputs(tmp_path, outputs) == 0, capsys.readouterr().out


def test_check_flags_a_script_that_lost_its_executable_bit(tmp_path):
    """Identical text but unrunnable is still broken — --check must not call it current."""
    root = _library(tmp_path)
    skill_dir = _skill(root, "qa")
    _write(skill_dir, "scripts/check.sh", "#!/bin/sh\nexit 0\n")
    renderer = _renderer(tmp_path, root, ["qa"])
    outputs = renderer.render(agents={"claude": True}, roots=set())
    install_outputs(tmp_path, outputs)

    installed = tmp_path / ".claude" / "skills" / "demo-qa" / "scripts" / "check.sh"
    installed.chmod(0o644)

    assert check_outputs(tmp_path, outputs) == 1


def test_a_removed_reference_is_reported_as_extra(tmp_path, capsys):
    """Assets live under a scanned target dir, so a deleted one must surface, not linger."""
    root = _library(tmp_path)
    skill_dir = _skill(root, "qa")
    _write(skill_dir, "references/notes.md", "# Notes\n")
    renderer = _renderer(tmp_path, root, ["qa"])
    install_outputs(tmp_path, renderer.render(agents={"claude": True}, roots=set()))

    (skill_dir / "references" / "notes.md").unlink()
    stale = _renderer(tmp_path, root, ["qa"]).render(
        agents={"claude": True}, roots=set()
    )

    assert check_outputs(tmp_path, stale) == 1
    assert "extra: .claude/skills/demo-qa/references/notes.md" in capsys.readouterr().out


# --- the template gate ------------------------------------------------------------


def test_raw_tags_are_honoured_in_a_file_that_names_no_helper(tmp_path):
    """`{% raw %}` is the only way to protect a literal `{{ }}`, so it must open the gate.

    Rendering is skipped for content naming no helper — otherwise every `{{ }}` in a code
    sample is a Jinja syntax error. But a skipped file never strips its own raw tags, so
    an author escaping a Helm/Actions/mockery template would see `{% raw %}` land in the
    installed skill verbatim.
    """
    root = _library(tmp_path)
    _skill(root, "helm", body="Use `{% raw %}{{ .Values.arn }}{% endraw %}` in the chart.\n")
    renderer = _renderer(tmp_path, root, ["helm"])

    outputs = renderer.render(agents={"claude": True}, roots=set())
    rendered = outputs[tmp_path / ".claude" / "skills" / "demo-helm" / "SKILL.md"]

    assert "{{ .Values.arn }}" in rendered
    assert "raw" not in rendered
