from __future__ import annotations

from pathlib import Path

from ostler import crud_generic
from ostler.model import load

from conftest import write

RESEARCH_TEMPLATE = """
research:
  title: Research Program
  kinds:
    - name: program
      doc_root: research
      default_path: specs
      path_template: "{name}/program.md"
      required: [type, title, status]
      fields: {status: {enum: [proposed, active, paused, complete]}}
      extra_files:
        - {path: "README.md", content: "# {title}\\n\\n## Gate Ladder\\n"}
        - {path: "log.md", content: "# Progress Log\\n"}
    - name: gate
      doc_root: research
      default_path: specs
      parent: program
      path_template: "{parent}/gates/{name}/gate.md"
      required: [type, gate, status]
      fields: {status: {enum: [pending, in-review, passed, reopened, blocked]}}
    - name: finding
      doc_root: research
      default_path: specs
      parent: gate
      path_template: "{parent}/findings/{name}.md"
      required: [type, title]
"""


def make_repo(tmp_path: Path) -> Path:
    write(tmp_path / ".agents/templates.yml", RESEARCH_TEMPLATE)
    return tmp_path


def test_create_program_writes_file_and_extra_files(tmp_path: Path):
    g = load(make_repo(tmp_path))
    res = crud_generic.create_instance(g, "program", "SMCNv3",
                                       {"title": "SMCNv3", "status": "active"})
    assert res.ok, res.message
    program_md = tmp_path / "specs/SMCNv3/program.md"
    assert program_md.exists()
    assert (tmp_path / "specs/SMCNv3/README.md").read_text() == "# SMCNv3\n\n## Gate Ladder\n"
    assert (tmp_path / "specs/SMCNv3/log.md").read_text() == "# Progress Log\n"
    fm_text = program_md.read_text()
    assert "type: program" in fm_text and "status: active" in fm_text


def test_create_program_missing_required_field_fails(tmp_path: Path):
    g = load(make_repo(tmp_path))
    res = crud_generic.create_instance(g, "program", "SMCNv3", {"title": "SMCNv3"})
    assert not res.ok
    assert "status" in res.message


def test_create_program_invalid_enum_fails(tmp_path: Path):
    g = load(make_repo(tmp_path))
    res = crud_generic.create_instance(g, "program", "SMCNv3",
                                       {"title": "SMCNv3", "status": "bogus"})
    assert not res.ok
    assert "invalid status" in res.message


def test_create_program_already_exists_fails(tmp_path: Path):
    g = load(make_repo(tmp_path))
    crud_generic.create_instance(g, "program", "SMCNv3", {"title": "SMCNv3", "status": "active"})
    res = crud_generic.create_instance(load(tmp_path), "program", "SMCNv3",
                                       {"title": "SMCNv3", "status": "active"})
    assert not res.ok
    assert "already exists" in res.message


def test_create_gate_requires_parent_field(tmp_path: Path):
    g = load(make_repo(tmp_path))
    res = crud_generic.create_instance(g, "gate", "G0", {"gate": "G0", "status": "pending"})
    assert not res.ok
    assert "program" in res.message


def test_create_gate_missing_parent_instance_fails(tmp_path: Path):
    g = load(make_repo(tmp_path))
    res = crud_generic.create_instance(g, "gate", "G0",
                                       {"program": "ghost", "gate": "G0", "status": "pending"})
    assert not res.ok
    assert "no program 'ghost'" in res.message


def test_full_three_level_nested_path_resolution(tmp_path: Path):
    g = load(make_repo(tmp_path))
    r1 = crud_generic.create_instance(g, "program", "SMCNv3",
                                      {"title": "SMCNv3", "status": "active"})
    assert r1.ok, r1.message
    g = load(tmp_path)
    r2 = crud_generic.create_instance(g, "gate", "G0",
                                      {"program": "SMCNv3", "gate": "G0", "status": "pending"})
    assert r2.ok, r2.message
    assert (tmp_path / "specs/SMCNv3/gates/G0/gate.md").exists()

    g = load(tmp_path)
    # finding only needs its immediate parent (gate=G0), not the full ancestor chain
    r3 = crud_generic.create_instance(g, "finding", "f1",
                                      {"gate": "G0", "title": "near-miss on inversion depth"})
    assert r3.ok, r3.message
    finding_path = tmp_path / "specs/SMCNv3/gates/G0/findings/f1.md"
    assert finding_path.exists()
    assert "near-miss on inversion depth" in finding_path.read_text()

    # gate=G0's frontmatter must not have been polluted with the parent-scoping field
    gate_fm = (tmp_path / "specs/SMCNv3/gates/G0/gate.md").read_text()
    assert "program:" not in gate_fm


def test_find_instance_returns_rows(tmp_path: Path):
    g = load(make_repo(tmp_path))
    crud_generic.create_instance(g, "program", "SMCNv3", {"title": "SMCNv3", "status": "active"})
    crud_generic.create_instance(load(tmp_path), "program", "Other",
                                 {"title": "Other", "status": "paused"})
    rows = crud_generic.find_instance(load(tmp_path), "program")
    assert {r["name"] for r in rows} == {"SMCNv3", "Other"}
    one = crud_generic.find_instance(load(tmp_path), "program", "SMCNv3")
    assert len(one) == 1 and one[0]["status"] == "active"


def test_edit_instance_updates_fields(tmp_path: Path):
    g = load(make_repo(tmp_path))
    crud_generic.create_instance(g, "program", "SMCNv3", {"title": "SMCNv3", "status": "active"})
    res = crud_generic.edit_instance(load(tmp_path), "program", "SMCNv3", {"status": "complete"})
    assert res.ok
    row = crud_generic.find_instance(load(tmp_path), "program", "SMCNv3")[0]
    assert row["status"] == "complete"


def test_edit_instance_invalid_enum_fails(tmp_path: Path):
    g = load(make_repo(tmp_path))
    crud_generic.create_instance(g, "program", "SMCNv3", {"title": "SMCNv3", "status": "active"})
    res = crud_generic.edit_instance(load(tmp_path), "program", "SMCNv3", {"status": "bogus"})
    assert not res.ok


def test_edit_instance_missing_fails(tmp_path: Path):
    g = load(make_repo(tmp_path))
    res = crud_generic.edit_instance(g, "program", "ghost", {"status": "active"})
    assert not res.ok
    assert "no program 'ghost'" in res.message


def test_delete_bundle_shaped_instance_removes_whole_directory(tmp_path: Path):
    g = load(make_repo(tmp_path))
    crud_generic.create_instance(g, "program", "SMCNv3", {"title": "SMCNv3", "status": "active"})
    crud_generic.create_instance(load(tmp_path), "gate", "G0",
                                 {"program": "SMCNv3", "gate": "G0", "status": "pending"})
    res = crud_generic.delete_instance(load(tmp_path), "gate", "G0")
    assert res.ok
    assert not (tmp_path / "specs/SMCNv3/gates/G0").exists()
    # parent program untouched
    assert (tmp_path / "specs/SMCNv3/program.md").exists()


def test_delete_leaf_shaped_instance_removes_only_file(tmp_path: Path):
    g = load(make_repo(tmp_path))
    crud_generic.create_instance(g, "program", "SMCNv3", {"title": "SMCNv3", "status": "active"})
    crud_generic.create_instance(load(tmp_path), "gate", "G0",
                                 {"program": "SMCNv3", "gate": "G0", "status": "pending"})
    crud_generic.create_instance(load(tmp_path), "finding", "f1",
                                 {"gate": "G0", "title": "x"})
    res = crud_generic.delete_instance(load(tmp_path), "finding", "f1")
    assert res.ok
    assert not (tmp_path / "specs/SMCNv3/gates/G0/findings/f1.md").exists()
    assert (tmp_path / "specs/SMCNv3/gates/G0/gate.md").exists()


def test_delete_instance_missing_fails(tmp_path: Path):
    g = load(make_repo(tmp_path))
    res = crud_generic.delete_instance(g, "program", "ghost")
    assert not res.ok


def test_id_allocated_kind_mints_id(tmp_path: Path):
    write(tmp_path / ".agents/templates.yml", """
research:
  title: Research
  kinds:
    - name: program
      doc_root: research
      default_path: specs
      path_template: "{name}/program.md"
      id: true
      required: [type, title]
""")
    g = load(tmp_path)
    res = crud_generic.create_instance(g, "program", "SMCNv3", {"title": "SMCNv3"})
    assert res.ok
    assert res.entity_id
    fm_text = (tmp_path / "specs/SMCNv3/program.md").read_text()
    assert f"id: {res.entity_id}" in fm_text
