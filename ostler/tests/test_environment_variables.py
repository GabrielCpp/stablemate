"""An environment page's `variables:` bullet: reading it, finding the page, and the doctor's checks on it."""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import doctor, model
from ostler.environments import inject, page

from conftest import write

PAGE = Path("docs") / "services" / "app" / "ops" / "local.md"

FIXTURE = """---
type: environment
slug: local
title: Local
---
# Local

- selector: the developer's machine
- variables:
  - API_URL: http://localhost:8000
  - LOG_LEVEL: debug
  - FEATURE_FLAGS: a,b
  - DATABASE_URL: secret
  - STRIPE_KEY: secret
- local-only: true
"""


def _book(root: Path, text: str = FIXTURE) -> model.Graph:
    (root / ".git").mkdir(exist_ok=True)
    write(root / PAGE, text)
    return model.load(root)


def _with_variables(*children: str) -> str:
    return FIXTURE.split("- variables:")[0] + "- variables:\n" + "".join(f"  - {c}\n" for c in children)


def _node(root: Path, text: str = FIXTURE):
    return _book(root, text).ui_nodes_of_type("environment")[0]


def test_the_page_gives_its_literals_and_its_held_names_in_page_order(tmp_path: Path) -> None:
    variables = page.read_variables(_node(tmp_path))
    assert list(variables.literals.items()) == [
        ("API_URL", "http://localhost:8000"), ("LOG_LEVEL", "debug"), ("FEATURE_FLAGS", "a,b")]
    assert variables.held == {"DATABASE_URL", "STRIPE_KEY"}
    assert [name for name, _ in variables.entries] == [
        "API_URL", "LOG_LEVEL", "FEATURE_FLAGS", "DATABASE_URL", "STRIPE_KEY"]


def test_a_value_in_backticks_is_kept_without_them(tmp_path: Path) -> None:
    variables = page.read_variables(_node(tmp_path, _with_variables("GREETING: `hello there`")))
    assert variables.literals == {"GREETING": "hello there"}


@pytest.mark.parametrize("child", ["1BAD: x", "BAD-NAME: x", "no colon here"])
def test_a_child_that_is_no_name_and_value_is_refused(tmp_path: Path, child: str) -> None:
    with pytest.raises(page.VariableError):
        page.read_variables(_node(tmp_path, _with_variables(child)))


def test_a_name_listed_twice_is_refused(tmp_path: Path) -> None:
    with pytest.raises(page.VariableError, match="listed twice") as raised:
        page.read_variables(_node(tmp_path, _with_variables("A: 1", "A: secret")))
    assert raised.value.name == "A"


def test_an_environment_is_found_by_slug_and_by_id(tmp_path: Path) -> None:
    graph = _book(tmp_path)
    assert page.find_environment(graph, "local").id == PAGE.as_posix()
    assert page.find_environment(graph, PAGE.as_posix()).id == PAGE.as_posix()


def test_a_page_of_another_type_or_none_is_not_an_environment(tmp_path: Path) -> None:
    graph = _book(tmp_path)
    write(tmp_path / "docs" / "services" / "app" / "ops" / "web.md",
          "---\ntype: runbook\ntitle: Web\n---\n\n# Web\n\n- driver: web\n\n## Steps\n\n"
          "### serve\n\n- kind: service\n- run: make\n")
    graph = model.load(tmp_path)
    with pytest.raises(LookupError, match="not an environment"):
        page.find_environment(graph, "docs/services/app/ops/web.md")
    with pytest.raises(LookupError, match="no environment"):
        page.find_environment(graph, "staging")


def _codes(graph: model.Graph, classify: doctor.Classifier) -> dict[str, str]:
    return {fd.code: fd.message for fd in doctor.run(graph, classify=classify).findings
            if fd.code.startswith("environment-variable")}


def test_the_doctor_passes_a_page_whose_literals_are_plain(tmp_path: Path) -> None:
    seen: list[list[tuple[str, str]]] = []

    def classify(entries: list[tuple[str, str]]) -> dict[str, str | None]:
        seen.append(entries)
        return {name: None for name, _ in entries}

    assert _codes(_book(tmp_path), classify) == {}
    assert seen == [[("API_URL", "http://localhost:8000"), ("LOG_LEVEL", "debug"),
                     ("FEATURE_FLAGS", "a,b")]]


def test_the_doctor_refuses_a_literal_that_is_a_secret(tmp_path: Path) -> None:
    found = _codes(_book(tmp_path), lambda entries: {"LOG_LEVEL": "token-shape"})
    assert list(found) == ["environment-variable-secret"]
    assert "LOG_LEVEL holds a secret value (token-shape)" in found["environment-variable-secret"]
    assert "--tag environment=local" in found["environment-variable-secret"]


def test_the_doctor_warns_when_the_classifier_cannot_run(tmp_path: Path) -> None:
    def classify(entries: list[tuple[str, str]]) -> dict[str, str | None]:
        raise inject.ClassifyError("the daemon is not running")

    found = _codes(_book(tmp_path), classify)
    assert list(found) == ["environment-variables-unchecked"]
    assert "the daemon is not running" in found["environment-variables-unchecked"]


def test_the_doctor_refuses_a_name_no_environment_can_hold(tmp_path: Path) -> None:
    graph = _book(tmp_path, _with_variables("1BAD: x"))
    assert list(_codes(graph, lambda entries: {})) == ["environment-variable-name"]


def test_a_page_with_only_held_names_is_never_classified(tmp_path: Path) -> None:
    def classify(entries: list[tuple[str, str]]) -> dict[str, str | None]:
        raise AssertionError("nothing to classify")

    assert _codes(_book(tmp_path, _with_variables("A: secret")), classify) == {}
