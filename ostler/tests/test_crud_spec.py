from __future__ import annotations

from pathlib import Path

import pytest

from ostler import crud, doctor, markdown, registry
from ostler.model import load

from conftest import write


def _fm(path: Path) -> dict:
    return markdown.split(path.read_text(encoding="utf-8")).frontmatter or {}


@pytest.mark.parametrize(("name", "expected"), [
    ("plan.md", "spec.plan"),
    ("review.md", "spec.review"),
    ("qa.md", "spec.qa"),
    # The stem is carried through verbatim rather than collapsed — these are the types
    # already on disk in real repos, and the subtype is descriptive, not dispatched on.
    ("plan-web.md", "spec.plan-web"),
    ("plan-go.md", "spec.plan-go"),
    ("qa-plan.md", "spec.qa-plan"),
    ("executive.md", "spec.executive"),
    ("vet.md", "spec.vet"),
    ("setup-fix.md", "spec.setup-fix"),
    ("implementation-notes.md", "spec.implementation-notes"),
    ("PLAN.md", "spec.plan"),          # case-normalized
])
def test_spec_type_for_maps_filename(name: str, expected: str):
    assert registry.spec_type_for(name) == expected


@pytest.mark.parametrize("name", ["plan.md", "executive.md", "vet.md", "some-new-doc.md"])
def test_spec_type_for_always_conforms(name: str):
    # Whatever the stem, the base type must resolve to the registered 'spec' EntityType —
    # that is the property doctor actually checks.
    assert registry.base_type(registry.spec_type_for(name)) == "spec"


def test_create_spec_writes_typed_doc(tmp_path: Path):
    g = load(tmp_path)
    res = crud.create_spec(g, "01-fix-login", "plan.md", title="Fix login")
    assert res.ok
    path = tmp_path / "docs/specs/01-fix-login/plan.md"
    assert _fm(path)["type"] == "spec.plan"
    assert path.read_text().endswith("# Fix login\n\n")


def test_create_spec_stamps_an_existing_untyped_doc_preserving_body(tmp_path: Path):
    body = "# Review: 01-fix-login\n\nThe login handler drops the session.\n"
    write(tmp_path / "docs/specs/01-fix-login/review.md", body)

    res = crud.create_spec(load(tmp_path), "01-fix-login", "review.md")
    assert res.ok and "stamped" in res.message
    path = tmp_path / "docs/specs/01-fix-login/review.md"
    assert _fm(path)["type"] == "spec.review"
    assert markdown.split(path.read_text()).body == body


def test_create_spec_stamps_over_a_blank_type_key(tmp_path: Path):
    # A present-but-blank `type:` is what okf-missing-type fires on, and it must not
    # shadow the stamp when the existing frontmatter is merged back in.
    write(tmp_path / "docs/specs/01-fix-login/qa.md", "---\ntype:\nslug: 01-fix-login\n---\n# QA\n")

    assert crud.create_spec(load(tmp_path), "01-fix-login", "qa.md").ok
    fm = _fm(tmp_path / "docs/specs/01-fix-login/qa.md")
    assert fm["type"] == "spec.qa"
    assert fm["slug"] == "01-fix-login"   # unrelated keys survive


def test_create_spec_leaves_an_already_typed_doc_alone(tmp_path: Path):
    original = "---\ntype: spec.plan\nowner: gabriel\n---\n# Plan\n"
    write(tmp_path / "docs/specs/01-fix-login/plan.md", original)

    res = crud.create_spec(load(tmp_path), "01-fix-login", "plan.md", title="Ignored")
    assert res.ok and "already typed" in res.message
    assert (tmp_path / "docs/specs/01-fix-login/plan.md").read_text() == original


def test_create_spec_is_idempotent(tmp_path: Path):
    g = load(tmp_path)
    crud.create_spec(g, "01-fix-login", "qa.md", title="QA")
    before = (tmp_path / "docs/specs/01-fix-login/qa.md").read_text()
    crud.create_spec(load(tmp_path), "01-fix-login", "qa.md", title="QA")
    assert (tmp_path / "docs/specs/01-fix-login/qa.md").read_text() == before


def test_create_spec_appends_md_suffix(tmp_path: Path):
    assert crud.create_spec(load(tmp_path), "01-fix-login", "plan").ok
    assert (tmp_path / "docs/specs/01-fix-login/plan.md").is_file()


def test_create_spec_rejects_reserved_files(tmp_path: Path):
    res = crud.create_spec(load(tmp_path), "01-fix-login", "index.md")
    assert not res.ok
    assert not (tmp_path / "docs/specs/01-fix-login/index.md").exists()


def test_create_spec_rejects_nested_paths(tmp_path: Path):
    # The spec glob is '*/*.md' — one level deep. A nested doc would never be scanned,
    # so it must not be mintable either.
    assert not crud.create_spec(load(tmp_path), "01-fix-login", "qa/report.md").ok
    assert not crud.create_spec(load(tmp_path), "nested/slug", "plan.md").ok


def test_stamped_specs_clear_the_doctor_error(repo: Path):
    write(repo / "docs/specs/01-fix-login/plan.md", "# Plan\n")
    write(repo / "docs/specs/01-fix-login/executive.md", "# Executive\n")
    before = doctor.run(load(repo))
    assert "okf-missing-type" in {f.code for f in before.findings if f.severity == "error"}

    for doc in ("plan.md", "executive.md"):
        assert crud.create_spec(load(repo), "01-fix-login", doc).ok

    after = doctor.run(load(repo))
    assert "okf-missing-type" not in {f.code for f in after.findings if f.severity == "error"}
    assert after.errors == 0, [f.message for f in after.findings if f.severity == "error"]
