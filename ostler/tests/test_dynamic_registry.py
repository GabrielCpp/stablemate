from __future__ import annotations

from pathlib import Path

from ostler import dynamic_registry
from ostler.dynamic_registry import TemplateKind
from conftest import present, write


def parse(template_name: str, raw: dict) -> TemplateKind:
    """`parse_kind` on a spec the test wrote to be well-formed.

    `parse_kind` returns ``None`` for a spec it rejects, and the tests that are *about*
    rejection call it directly and assert on that ``None``. Everywhere else the spec is a
    fixture and the parse is setup, so ruling the ``None`` out once here keeps a regression
    legible — this line, naming the call — instead of an attribute lookup on ``None``
    inside whichever assertion happened to run first.
    """
    return present(dynamic_registry.parse_kind(template_name, raw))


def test_load_kinds_empty_when_absent(tmp_path: Path):
    assert dynamic_registry.load_kinds(tmp_path) == ()


def test_load_kinds_empty_when_malformed(tmp_path: Path):
    write(tmp_path / ".agents/templates.yml", "not: [valid, yaml: :::")
    assert dynamic_registry.load_kinds(tmp_path) == ()


def test_load_kinds_parses_single_template(tmp_path: Path):
    write(tmp_path / ".agents/templates.yml", """
research:
  title: Research Program
  kinds:
    - name: program
      doc_root: research
      default_path: specs
      path_template: "{name}/program.md"
      required: [type, title]
""")
    kinds = dynamic_registry.load_kinds(tmp_path)
    assert len(kinds) == 1
    k = kinds[0]
    assert k.name == "program" and k.doc_root == "research" and k.default_path == "specs"
    assert k.required == ("type", "title")
    assert k.is_bundle is True


def test_load_kinds_parses_multiple_templates(tmp_path: Path):
    write(tmp_path / ".agents/templates.yml", """
research:
  title: Research
  kinds:
    - {name: program, doc_root: research, default_path: specs, path_template: "{name}/program.md"}
qa:
  title: QA
  kinds:
    - {name: checklist, doc_root: qa, default_path: docs/qa, path_template: "{name}.md"}
""")
    kinds = dynamic_registry.load_kinds(tmp_path)
    assert {k.name for k in kinds} == {"program", "checklist"}


def test_load_kinds_drops_builtin_name_collision(tmp_path: Path):
    write(tmp_path / ".agents/templates.yml", """
bogus:
  title: Bogus
  kinds:
    - {name: epic, doc_root: research, default_path: specs, path_template: "{name}/x.md"}
    - {name: program, doc_root: research, default_path: specs, path_template: "{name}/program.md"}
""")
    kinds = dynamic_registry.load_kinds(tmp_path)
    assert {k.name for k in kinds} == {"program"}


def test_load_kinds_drops_cross_template_name_collision(tmp_path: Path):
    write(tmp_path / ".agents/templates.yml", """
a:
  title: A
  kinds:
    - {name: program, doc_root: a, default_path: specs-a, path_template: "{name}/program.md"}
b:
  title: B
  kinds:
    - {name: program, doc_root: b, default_path: specs-b, path_template: "{name}/program.md"}
""")
    kinds = dynamic_registry.load_kinds(tmp_path)
    assert len(kinds) == 1
    assert kinds[0].doc_root == "a"


def test_load_kinds_drops_kind_missing_required_field(tmp_path: Path):
    write(tmp_path / ".agents/templates.yml", """
research:
  title: Research
  kinds:
    - {name: program, doc_root: research, path_template: "{name}/program.md"}
""")
    assert dynamic_registry.load_kinds(tmp_path) == ()


def test_location_glob_bundle_shape():
    k = parse("t", {
        "name": "program", "doc_root": "research", "default_path": "specs",
        "path_template": "{name}/program.md",
    })
    assert k.location == "*/program.md"
    assert k.is_bundle is True


def test_location_glob_leaf_shape():
    k = parse("t", {
        "name": "checklist", "doc_root": "qa", "default_path": "docs/qa",
        "path_template": "{name}.md",
    })
    assert k.location == "*.md"
    assert k.is_bundle is False


def test_location_glob_nested_parent_expands_to_double_star():
    k = parse("t", {
        "name": "gate", "doc_root": "research", "default_path": "specs", "parent": "program",
        "path_template": "{parent}/gates/{name}/gate.md",
    })
    assert k.location == "**/gates/*/gate.md"
    assert k.is_bundle is True


def test_location_glob_three_level_nesting_from_worked_example():
    finding = parse("t", {
        "name": "finding", "doc_root": "research", "default_path": "specs", "parent": "gate",
        "path_template": "{parent}/findings/{name}.md",
    })
    assert finding.location == "**/findings/*.md"
    assert finding.is_bundle is False


def test_location_glob_mixed_literal_and_placeholder():
    k = parse("t", {
        "name": "gate", "doc_root": "research", "default_path": "specs",
        "path_template": "G{name}/gate.md",
    })
    assert k.location == "G*/gate.md"


def test_validate_kinds_rejects_builtin_collision():
    new_kind = parse("t", {
        "name": "epic", "doc_root": "research", "default_path": "specs",
        "path_template": "{name}/x.md",
    })
    errors = dynamic_registry.validate_kinds((), [new_kind])
    assert any("built-in" in e for e in errors)


def test_validate_kinds_rejects_cross_template_duplicate():
    existing = parse("a", {
        "name": "program", "doc_root": "a", "default_path": "specs-a",
        "path_template": "{name}/program.md",
    })
    new_kind = parse("b", {
        "name": "program", "doc_root": "b", "default_path": "specs-b",
        "path_template": "{name}/program.md",
    })
    errors = dynamic_registry.validate_kinds((existing,), [new_kind])
    assert any("already declared" in e for e in errors)


def test_validate_kinds_rejects_leaf_shaped_parent():
    leaf = parse("t", {
        "name": "checklist", "doc_root": "qa", "default_path": "docs/qa",
        "path_template": "{name}.md",
    })
    child = parse("t", {
        "name": "item", "doc_root": "qa", "default_path": "docs/qa", "parent": "checklist",
        "path_template": "{parent}/{name}.md",
    })
    errors = dynamic_registry.validate_kinds((leaf,), [child])
    assert any("leaf-shaped" in e for e in errors)


def test_validate_kinds_rejects_unknown_parent():
    child = parse("t", {
        "name": "item", "doc_root": "qa", "default_path": "docs/qa", "parent": "ghost",
        "path_template": "{parent}/{name}.md",
    })
    errors = dynamic_registry.validate_kinds((), [child])
    assert any("not a declared kind" in e for e in errors)


def test_validate_kinds_rejects_extra_files_on_leaf_shaped_kind():
    leaf = parse("t", {
        "name": "checklist", "doc_root": "qa", "default_path": "docs/qa",
        "path_template": "{name}.md",
        "extra_files": [{"path": "README.md", "content": "# hi\n"}],
    })
    errors = dynamic_registry.validate_kinds((), [leaf])
    assert any("extra_files requires a bundle-shaped" in e for e in errors)


def test_validate_kinds_accepts_valid_three_level_hierarchy():
    program = parse("research", {
        "name": "program", "doc_root": "research", "default_path": "specs",
        "path_template": "{name}/program.md",
    })
    gate = parse("research", {
        "name": "gate", "doc_root": "research", "default_path": "specs", "parent": "program",
        "path_template": "{parent}/gates/{name}/gate.md",
    })
    finding = parse("research", {
        "name": "finding", "doc_root": "research", "default_path": "specs", "parent": "gate",
        "path_template": "{parent}/findings/{name}.md",
    })
    errors = dynamic_registry.validate_kinds((), [program, gate, finding])
    assert errors == []
