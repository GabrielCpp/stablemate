from __future__ import annotations

from pathlib import Path

import pytest

from ostler import api, crud, doctor, markdown, registry
from ostler.model import Graph, load
from ostler.path import specs_root_in

from conftest import write


def _fm(path: Path) -> dict:
    return markdown.split(path.read_text(encoding="utf-8")).frontmatter or {}


@pytest.mark.parametrize(("name", "expected"), [
    ("plan.md", "spec.plan"),
    ("review.md", "spec.review"),
    ("qa.md", "spec.qa"),
    ("plan-web.md", "spec.plan-web"),
    ("plan-go.md", "spec.plan-go"),
    ("qa-plan.md", "spec.qa-plan"),
    ("executive.md", "spec.executive"),
    ("vet.md", "spec.vet"),
    ("setup-fix.md", "spec.setup-fix"),
    ("implementation-notes.md", "spec.implementation-notes"),
    ("PLAN.md", "spec.plan"),
])
def test_spec_type_for_maps_filename(name: str, expected: str):
    assert registry.spec_type_for(name) == expected


@pytest.mark.parametrize("name", ["plan.md", "executive.md", "vet.md", "some-new-doc.md"])
def test_spec_type_for_always_conforms(name: str):
    assert registry.base_type(registry.spec_type_for(name)) == "spec"


def test_create_spec_writes_typed_doc(tmp_path: Path):
    res = crud.create_spec(specs_root_in(tmp_path), "01-fix-login", "plan.md", title="Fix login")
    assert res.ok
    path = tmp_path / "docs/specs/01-fix-login/plan.md"
    assert _fm(path)["type"] == "spec.plan"
    assert path.read_text().endswith("# Fix login\n\n")


def test_create_spec_stamps_an_existing_untyped_doc_preserving_body(tmp_path: Path):
    body = "# Review: 01-fix-login\n\nThe login handler drops the session.\n"
    write(tmp_path / "docs/specs/01-fix-login/review.md", body)

    res = crud.create_spec(specs_root_in(tmp_path), "01-fix-login", "review.md")
    assert res.ok and "stamped" in res.message
    path = tmp_path / "docs/specs/01-fix-login/review.md"
    assert _fm(path)["type"] == "spec.review"
    assert markdown.split(path.read_text()).body == body


def test_create_spec_stamps_over_a_blank_type_key(tmp_path: Path):
    write(tmp_path / "docs/specs/01-fix-login/qa.md", "---\ntype:\nslug: 01-fix-login\n---\n# QA\n")

    assert crud.create_spec(specs_root_in(tmp_path), "01-fix-login", "qa.md").ok
    fm = _fm(tmp_path / "docs/specs/01-fix-login/qa.md")
    assert fm["type"] == "spec.qa"
    assert fm["slug"] == "01-fix-login"


def test_create_spec_leaves_an_already_typed_doc_alone(tmp_path: Path):
    original = "---\ntype: spec.plan\nowner: gabriel\n---\n# Plan\n"
    write(tmp_path / "docs/specs/01-fix-login/plan.md", original)

    res = crud.create_spec(specs_root_in(tmp_path), "01-fix-login", "plan.md", title="Ignored")
    assert res.ok and "already typed" in res.message
    assert (tmp_path / "docs/specs/01-fix-login/plan.md").read_text() == original


def test_create_spec_is_idempotent(tmp_path: Path):
    crud.create_spec(specs_root_in(tmp_path), "01-fix-login", "qa.md", title="QA")
    before = (tmp_path / "docs/specs/01-fix-login/qa.md").read_text()
    crud.create_spec(specs_root_in(tmp_path), "01-fix-login", "qa.md", title="QA")
    assert (tmp_path / "docs/specs/01-fix-login/qa.md").read_text() == before


def test_create_spec_appends_md_suffix(tmp_path: Path):
    assert crud.create_spec(specs_root_in(tmp_path), "01-fix-login", "plan").ok
    assert (tmp_path / "docs/specs/01-fix-login/plan.md").is_file()


def test_create_spec_rejects_reserved_files(tmp_path: Path):
    res = crud.create_spec(specs_root_in(tmp_path), "01-fix-login", "index.md")
    assert not res.ok
    assert not (tmp_path / "docs/specs/01-fix-login/index.md").exists()


def test_create_spec_rejects_nested_paths(tmp_path: Path):
    assert not crud.create_spec(specs_root_in(tmp_path), "01-fix-login", "qa/report.md").ok
    assert not crud.create_spec(specs_root_in(tmp_path), "nested/slug", "plan.md").ok


def test_facade_create_spec_loads_no_graph(repo: Path, monkeypatch: pytest.MonkeyPatch):
    def _boom(*args: object, **kwargs: object) -> Graph:
        raise AssertionError("create_spec loaded the graph")

    monkeypatch.setattr(api, "load", _boom)
    okf = api.Ostler(repo)
    assert okf.create_spec("01-fix-login", "plan.md").ok
    assert _fm(repo / "docs/specs/01-fix-login/plan.md")["type"] == "spec.plan"


def test_stamped_specs_clear_the_doctor_error(repo: Path):
    write(repo / "docs/specs/01-fix-login/plan.md", "# Plan\n")
    write(repo / "docs/specs/01-fix-login/executive.md", "# Executive\n")
    before = doctor.run(load(repo))
    assert "okf-missing-type" in {f.code for f in before.findings if f.severity == "error"}

    for doc in ("plan.md", "executive.md"):
        assert crud.create_spec(specs_root_in(repo), "01-fix-login", doc).ok

    after = doctor.run(load(repo))
    assert "okf-missing-type" not in {f.code for f in after.findings if f.severity == "error"}
    assert after.errors == 0, [f.message for f in after.findings if f.severity == "error"]
