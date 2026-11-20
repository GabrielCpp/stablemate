"""The argument list of a book run names calls with `--only` only when it has some, because an empty `--only` is refused."""

from __future__ import annotations

from workhorse_workflows.coder.book_qa.nodes import _run_argv


def test_a_run_of_no_named_calls_leaves_the_only_flag_out() -> None:
    assert "--only" not in _run_argv("services.api", [], None, "copy", "out")


def test_a_run_of_named_calls_joins_them_after_the_only_flag() -> None:
    argv = _run_argv("services.api", ["AddTodo", "FindTodos"], None, "copy", "out")
    assert argv[argv.index("--only") + 1] == "AddTodo,FindTodos"
