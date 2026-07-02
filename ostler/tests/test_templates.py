from __future__ import annotations

from pathlib import Path

from ostler import dynamic_registry, templates


def test_new_creates_template_with_no_kinds(tmp_path: Path):
    res = templates.new(tmp_path, "research")
    assert res.ok
    data = dynamic_registry.load_raw(tmp_path)
    assert data["research"]["kinds"] == []
    assert data["research"]["title"] == "research"


def test_new_rejects_existing_template(tmp_path: Path):
    templates.new(tmp_path, "research")
    res = templates.new(tmp_path, "research")
    assert not res.ok
    assert "already exists" in res.message


def test_new_with_kinds_creates_stubs(tmp_path: Path):
    res = templates.new(tmp_path, "research", ["program", "gate"])
    assert res.ok
    data = dynamic_registry.load_raw(tmp_path)
    names = {k["name"] for k in data["research"]["kinds"]}
    assert names == {"program", "gate"}
    program = next(k for k in data["research"]["kinds"] if k["name"] == "program")
    assert program["path_template"] == "{name}/program.md"
    assert program["required"] == ["type"]


def test_find_lists_all_templates(tmp_path: Path):
    templates.new(tmp_path, "research")
    templates.new(tmp_path, "qa")
    rows = templates.find(tmp_path)
    assert {r["name"] for r in rows} == {"research", "qa"}


def test_find_one_template_returns_full_definition(tmp_path: Path):
    templates.new(tmp_path, "research", ["program"])
    rows = templates.find(tmp_path, "research")
    assert len(rows) == 1
    assert rows[0]["kinds"][0]["name"] == "program"


def test_find_unknown_template_returns_empty(tmp_path: Path):
    assert templates.find(tmp_path, "ghost") == []


def test_delete_removes_template(tmp_path: Path):
    templates.new(tmp_path, "research")
    res = templates.delete(tmp_path, "research")
    assert res.ok
    assert templates.find(tmp_path) == []


def test_delete_unknown_template_fails(tmp_path: Path):
    res = templates.delete(tmp_path, "ghost")
    assert not res.ok


def test_edit_sets_new_kind_field(tmp_path: Path):
    templates.new(tmp_path, "research", ["program"])
    res = templates.edit(tmp_path, "research", ["program.default_path=specs"])
    assert res.ok, res.message
    data = dynamic_registry.load_raw(tmp_path)
    program = next(k for k in data["research"]["kinds"] if k["name"] == "program")
    assert program["default_path"] == "specs"


def test_edit_sets_dotted_subfield(tmp_path: Path):
    templates.new(tmp_path, "research", ["program"])
    res = templates.edit(tmp_path, "research", [
        "program.fields.status.enum=[active, complete]",
    ])
    assert res.ok, res.message
    data = dynamic_registry.load_raw(tmp_path)
    program = next(k for k in data["research"]["kinds"] if k["name"] == "program")
    assert program["fields"]["status"]["enum"] == ["active", "complete"]


def test_edit_unknown_template_fails(tmp_path: Path):
    res = templates.edit(tmp_path, "ghost", ["program.default_path=specs"])
    assert not res.ok


def test_edit_rejects_malformed_assignment(tmp_path: Path):
    templates.new(tmp_path, "research")
    res = templates.edit(tmp_path, "research", ["not-a-kv-pair"])
    assert not res.ok


def test_edit_rejects_builtin_name_collision(tmp_path: Path):
    templates.new(tmp_path, "research", ["program"])
    res = templates.edit(tmp_path, "research", [
        "program.name=epic",
        "program.doc_root=research",
        "program.default_path=specs",
        "program.path_template={name}/program.md",
    ])
    assert not res.ok
    assert "built-in" in res.message


def test_edit_rejects_leaf_shaped_parent(tmp_path: Path):
    templates.new(tmp_path, "research")
    templates.edit(tmp_path, "research", [
        "checklist.name=checklist",
        "checklist.doc_root=qa",
        "checklist.default_path=docs/qa",
        "checklist.path_template={name}.md",
    ])
    res = templates.edit(tmp_path, "research", [
        "item.name=item",
        "item.doc_root=qa",
        "item.default_path=docs/qa",
        "item.parent=checklist",
        "item.path_template={parent}/{name}.md",
    ])
    assert not res.ok
    assert "leaf-shaped" in res.message


def test_apply_scaffolds_directories(tmp_path: Path):
    templates.new(tmp_path, "research")
    templates.edit(tmp_path, "research", [
        "program.name=program",
        "program.doc_root=research",
        "program.default_path=specs",
        "program.path_template={name}/program.md",
    ])
    res = templates.apply(tmp_path, "research")
    assert res.ok
    assert (tmp_path / "specs").is_dir()


def test_apply_fails_for_unknown_template(tmp_path: Path):
    res = templates.apply(tmp_path, "ghost")
    assert not res.ok


def test_apply_fails_for_template_with_no_kinds(tmp_path: Path):
    templates.new(tmp_path, "research")
    res = templates.apply(tmp_path, "research")
    assert not res.ok
    assert "no kinds" in res.message
