from __future__ import annotations

from pathlib import Path

from ostler import templates


def test_apply_mkdirs_each_declared_doc_root(tmp_path: Path):
    templates.new(tmp_path, "research")
    templates.edit(tmp_path, "research", [
        "program.name=program",
        "program.doc_root=research",
        "program.default_path=specs",
        "program.path_template={name}/program.md",
    ])
    res = templates.apply(tmp_path, "research")
    assert res.ok, res.message
    assert (tmp_path / "specs").is_dir()


def test_apply_dedupes_shared_doc_root(tmp_path: Path):
    templates.new(tmp_path, "research")
    templates.edit(tmp_path, "research", [
        "program.name=program", "program.doc_root=research",
        "program.default_path=specs", "program.path_template={name}/program.md",
        "gate.name=gate", "gate.doc_root=research", "gate.parent=program",
        "gate.default_path=specs", "gate.path_template={parent}/gates/{name}/gate.md",
    ])
    res = templates.apply(tmp_path, "research")
    assert res.ok
    assert "1 dir(s) scaffolded" in res.message


def test_apply_injects_claude_md_section(tmp_path: Path):
    templates.new(tmp_path, "research", ["program"])
    templates.edit(tmp_path, "research", ["program.default_path=specs"])
    templates.apply(tmp_path, "research")
    text = (tmp_path / "CLAUDE.md").read_text()
    assert "<!-- ostler:template:research:start -->" in text
    assert "<!-- ostler:template:research:end -->" in text
    assert "`program`" in text


def test_apply_twice_is_idempotent_single_section(tmp_path: Path):
    templates.new(tmp_path, "research", ["program"])
    templates.edit(tmp_path, "research", ["program.default_path=specs"])
    templates.apply(tmp_path, "research")
    first = (tmp_path / "CLAUDE.md").read_text()
    templates.apply(tmp_path, "research")
    second = (tmp_path / "CLAUDE.md").read_text()
    assert first == second
    assert second.count("<!-- ostler:template:research:start -->") == 1


def test_apply_reflects_kind_changes_in_place_on_reapply(tmp_path: Path):
    templates.new(tmp_path, "research", ["program"])
    templates.edit(tmp_path, "research", ["program.default_path=specs"])
    templates.apply(tmp_path, "research")
    templates.edit(tmp_path, "research", ["program.note=updated"])
    templates.apply(tmp_path, "research")
    text = (tmp_path / "CLAUDE.md").read_text()
    assert text.count("<!-- ostler:template:research:start -->") == 1


def test_apply_preserves_existing_claude_md_content(tmp_path: Path):
    (tmp_path / "CLAUDE.md").write_text("# Project notes\n\nSome existing guidance.\n")
    templates.new(tmp_path, "research", ["program"])
    templates.edit(tmp_path, "research", ["program.default_path=specs"])
    templates.apply(tmp_path, "research")
    text = (tmp_path / "CLAUDE.md").read_text()
    assert "Some existing guidance." in text
    assert "<!-- ostler:template:research:start -->" in text


def test_two_templates_claude_md_sections_coexist(tmp_path: Path):
    templates.new(tmp_path, "research", ["program"])
    templates.edit(tmp_path, "research", ["program.default_path=specs"])
    templates.new(tmp_path, "qa", ["checklist"])
    templates.edit(tmp_path, "qa", ["checklist.default_path=docs/qa"])
    templates.apply(tmp_path, "research")
    templates.apply(tmp_path, "qa")
    text = (tmp_path / "CLAUDE.md").read_text()
    assert "<!-- ostler:template:research:start -->" in text
    assert "<!-- ostler:template:qa:start -->" in text

    # re-applying research must not disturb qa's section
    templates.edit(tmp_path, "research", ["program.note=updated"])
    templates.apply(tmp_path, "research")
    text2 = (tmp_path / "CLAUDE.md").read_text()
    assert "<!-- ostler:template:qa:start -->" in text2
    assert text2.count("<!-- ostler:template:qa:start -->") == 1
