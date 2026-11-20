"""The argument list of a book run names calls with `--only` only when it has some, because an empty `--only` is refused."""

from __future__ import annotations

from workhorse_workflows.coder.book_qa.nodes import _run_argv


def test_a_run_of_no_named_calls_leaves_the_only_flag_out() -> None:
    assert "--only" not in _run_argv("services.api", [], "copy", "out")


def test_a_run_of_named_calls_joins_them_after_the_only_flag() -> None:
    argv = _run_argv("services.api", ["AddTodo", "FindTodos"], "copy", "out")
    assert argv[argv.index("--only") + 1] == "AddTodo,FindTodos"


def test_a_fresh_run_reloads_the_data_first() -> None:
    assert "--fresh-data" in _run_argv("services.api", [], "copy", "out", fresh=True)
    assert "--fresh-data" not in _run_argv("services.api", [], "copy", "out")


def test_journeys_with_no_named_calls_run_partial_one_flag_each() -> None:
    argv = _run_argv("services.api", [], "copy", "out", journeys=["One", "Two words"])

    assert "--only" not in argv and "--partial" in argv
    assert [argv[i + 1] for i, arg in enumerate(argv) if arg == "--journey"] == ["One", "Two words"]


def test_named_calls_win_over_journeys_in_one_argument_list() -> None:
    argv = _run_argv("services.api", ["AddTodo"], "copy", "out", journeys=["One"])

    assert "--journey" not in argv and "--partial" not in argv


def test_a_play_carries_the_holder_of_the_copy_so_it_may_reset_its_data(monkeypatch, tmp_path) -> None:
    from workhorse_workflows.coder.book_qa import nodes

    seen: dict[str, str] = {}

    def run(argv, cwd=None, env=None, timeout=None):
        seen.update(env or {})
        return type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(nodes, "run_tool", run)
    monkeypatch.setattr(nodes, "stack_env", lambda root, near="", lease="": {"STABLEMATE_LEASE": lease, "STABLEMATE_LEASE_HOLDER": "41"})
    nodes._play(["x"], tmp_path, 5, nodes.stack_env(tmp_path, lease="story-7"))
    assert (seen["STABLEMATE_LEASE_HOLDER"], seen["STABLEMATE_LEASE"]) == ("41", "story-7")
