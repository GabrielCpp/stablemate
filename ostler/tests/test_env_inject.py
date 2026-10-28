"""Running a command under an environment page: resolution, composition and the rendered dotenv."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from ostler import model
from ostler.environments import inject, page

from conftest import write
from test_environment_variables import FIXTURE, PAGE


class FakeSaddlebag:
    def __init__(self, secrets: list[dict[str, str]] | None = None, status: int = 0) -> None:
        self.secrets = [{"name": "db", "var": "DATABASE_URL"},
                        {"name": "stripe", "var": "STRIPE_KEY"},
                        {"name": "other", "var": "UNRELATED"}] if secrets is None else secrets
        self.status = status
        self.calls: list[list[str]] = []
        self.stdin: list[str | None] = []

    def __call__(self, argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        self.stdin.append(stdin)
        return subprocess.CompletedProcess(
            list(argv), self.status, "" if self.status else json.dumps({"secrets": self.secrets}),
            "the daemon is not running" if self.status else "")


def _node(root: Path):
    (root / ".git").mkdir(exist_ok=True)
    write(root / PAGE, FIXTURE)
    return model.load(root).ui_nodes_of_type("environment")[0]


def test_each_held_name_is_bound_to_the_record_tagged_for_the_page(tmp_path: Path) -> None:
    saddlebag = FakeSaddlebag()
    resolved = inject.resolve(_node(tmp_path), saddlebag)
    assert resolved.bindings == {"DATABASE_URL": "db", "STRIPE_KEY": "stripe"}
    assert resolved.literals["API_URL"] == "http://localhost:8000"
    assert saddlebag.calls == [["saddlebag", "list", "--tag", "environment=local", "--json"]]


def test_a_held_name_with_no_record_names_the_variable_and_the_slug(tmp_path: Path) -> None:
    with pytest.raises(inject.ResolutionError) as raised:
        inject.resolve(_node(tmp_path), FakeSaddlebag([{"name": "db", "var": "DATABASE_URL"}]))
    message = str(raised.value)
    assert "STRIPE_KEY" in message and "environment=local" in message
    assert "saddlebag secret create <name> --var STRIPE_KEY --tag environment=local" in message


def test_a_held_name_with_two_records_names_both(tmp_path: Path) -> None:
    records = [{"name": "db", "var": "DATABASE_URL"}, {"name": "db-old", "var": "DATABASE_URL"},
               {"name": "stripe", "var": "STRIPE_KEY"}]
    with pytest.raises(inject.ResolutionError, match="db and db-old"):
        inject.resolve(_node(tmp_path), FakeSaddlebag(records))


def test_a_list_that_fails_is_a_resolution_error_with_its_stderr(tmp_path: Path) -> None:
    with pytest.raises(inject.ResolutionError, match="the daemon is not running"):
        inject.resolve(_node(tmp_path), FakeSaddlebag(status=1))


def test_the_command_is_wrapped_only_when_there_is_something_to_bind() -> None:
    bound = inject.Resolved({"A": "1"}, {"STRIPE_KEY": "stripe", "DATABASE_URL": "db"})
    assert inject.exec_argv(bound, ["env"]) == [
        "saddlebag", "exec", "--env", "DATABASE_URL=db", "--env", "STRIPE_KEY=stripe", "--", "env"]
    assert inject.exec_argv(inject.Resolved({"A": "1"}, {}), ["env", "-0"]) == ["env", "-0"]


def test_the_page_wins_over_the_process_environment() -> None:
    resolved = inject.Resolved({"API_URL": "http://page"}, {})
    assert inject.composed_environment(resolved, {"API_URL": "http://shell", "HOME": "/h"}) == {
        "API_URL": "http://page", "HOME": "/h"}


def test_the_dotenv_keeps_page_order_and_blanks_the_held_names(tmp_path: Path) -> None:
    text = inject.render_dotenv(page.read_variables(_node(tmp_path)), PAGE.as_posix())
    assert text == (
        f"# rendered by ostler env dotenv from {PAGE.as_posix()}; edit the page, not this file\n"
        "API_URL=http://localhost:8000\nLOG_LEVEL=debug\nFEATURE_FLAGS=a,b\n"
        "DATABASE_URL=\nSTRIPE_KEY=\n")


def test_a_value_with_a_space_or_a_quote_is_double_quoted() -> None:
    variables = page.Variables((("A", "two words"), ("B", 'say "hi"'), ("C", "a#b"), ("D", "it's")))
    assert inject.render_dotenv(variables, "p.md").splitlines()[1:] == [
        'A="two words"', 'B="say \\"hi\\""', 'C="a#b"', 'D="it\'s"']


def test_a_line_is_added_to_gitignore_once_and_a_rooted_one_counts(tmp_path: Path) -> None:
    assert inject.ensure_ignored(tmp_path, ".env") is True
    assert inject.ensure_ignored(tmp_path, ".env") is False
    assert (tmp_path / ".gitignore").read_text() == ".env\n"
    (tmp_path / ".gitignore").write_text("build/\n/other.env")
    assert inject.ensure_ignored(tmp_path, "other.env") is False
    assert inject.ensure_ignored(tmp_path, "new.env") is True
    assert (tmp_path / ".gitignore").read_text() == "build/\n/other.env\nnew.env\n"


def test_the_classifier_sends_the_literals_on_stdin_and_maps_the_rules() -> None:
    def runner(argv: Sequence[str], *, capture: bool, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        assert list(argv) == ["saddlebag", "env", "classify", "-", "--json"]
        assert stdin == "A=1\nB=sk-live-x\n"
        verdicts = [{"key": "A", "secret": False, "rule": None},
                    {"key": "B", "secret": True, "rule": "token-shape"}]
        return subprocess.CompletedProcess(list(argv), 0, json.dumps({"verdicts": verdicts}), "")

    assert inject.classify_literals([("A", "1"), ("B", "sk-live-x")], runner) == {
        "A": None, "B": "token-shape"}
