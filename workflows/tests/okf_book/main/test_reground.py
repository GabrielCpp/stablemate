"""A book whose cited file changed is read against the change before any repair: the nodes the change bears on reach the writer, and every other citation of the file is stamped on the file as it is now."""
from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter
from okf_book.main.tally import PAGE, TALLY, App
from okf_book.support import ScriptedRunner, always, commits, git
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import AgentTurnFailed
from workhorse.pyflow.driver import drive
from workhorse.pyflow.engine import RunEnv

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main.nodes.gate import RunFailures, keep_failures, take_failures
from workhorse_workflows.okf_book.main.nodes.stale_citations import Regrounded, stale_files
from workhorse_workflows.okf_book.main.reground_book_flow import RESTAMP_DESCRIPTION, RegroundBook
from workhorse_workflows.okf_book.shared.citations import cites_changed_file
from workhorse_workflows.okf_book.shared.page_check import PageProblem
from workhorse_workflows.okf_book.workflow import OkfBook, workflow

LEDGER = "tally/ledger.py"
LEDGER_PAGE = "docs/features/tally/concepts/ledger-file.md"
CHANGE = "\n\ndef archive(path):\n    return path\n"
SAID = "`merge` now keeps the newer of two entries with one id, and the node says the older"


def _change(repo: Path) -> None:
    source = repo / LEDGER
    _ = source.write_text(source.read_text(encoding="utf-8") + CHANGE, encoding="utf-8")
    _ = git(repo, "commit", "-q", "-m", "change the ledger", "--", LEDGER)


def _reground(tmp_path: Path, repo: Path, runner: ScriptedRunner) -> Regrounded:
    writer = ArtifactWriter("okf-book", tmp_path / "runs", run_id=f"t{runner.total}")
    env = RunEnv(writer=writer, workflow_dir=Path(okf_book.__file__).parent, session_id_path=writer.run_dir / ".session_id",
                 config=RunConfig(), nodes=workflow.nodes, agent_runner=runner)
    flow = RegroundBook(repo_dir=str(repo), parent_records_dir=str(tmp_path / "records"), service="tally")
    return Regrounded.model_validate(drive(flow, env))


def _naming_merge(args: dict[str, object]) -> dict[str, object]:
    nodes = TypeAdapter(list[dict[str, int | str]]).validate_python(args["nodes"])
    [number] = [cited["number"] for cited in nodes if cited["symbol"] == "merge"]
    return {"affected": [{"node": number, "instruction": SAID}]}


def test_a_book_stamped_on_its_source_cites_no_changed_file(app: App) -> None:
    repo = app("tally-cli")

    assert not cites_changed_file(repo, "tally")
    assert stale_files(repo, "tally") == ()


def test_the_node_a_change_bears_on_reaches_the_writer_and_the_rest_are_stamped(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    _change(repo)
    runner = ScriptedRunner({"reground-file": _naming_merge})

    regrounded = _reground(tmp_path, repo, runner)

    [args] = runner.args_of("reground-file")
    assert args["path"] == LEDGER
    assert "+def archive(path):" in str(args["diff"]).splitlines()
    assert Path(str(args["old_version"])).is_relative_to(repo)
    assert Path(str(args["old_version"])).read_text(encoding="utf-8") + CHANGE == (repo / LEDGER).read_text(encoding="utf-8")
    [(page, [problem])] = [(page, list(problems)) for page, problems in regrounded.failures.items()]
    assert page == PAGE
    assert problem.text.endswith(f"`{LEDGER}` changed since this node cited it, and the change bears on the node: {SAID}")
    assert regrounded.stamped > 0
    [left] = stale_files(repo, "tally")
    assert [cited.symbol for cited in left.nodes] == ["merge"]
    assert commits(repo)[0] == f"docs(tally): {RESTAMP_DESCRIPTION}"
    assert git(repo, "status", "--porcelain") == ""


def test_a_stamped_version_no_commit_holds_sends_every_citing_node_to_the_writer(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    source = repo / LEDGER
    _ = source.write_text(source.read_text(encoding="utf-8") + CHANGE, encoding="utf-8")
    _ = git(repo, "commit", "-q", "--amend", "-m", "fixture", "--", LEDGER)
    [stale] = stale_files(repo, "tally")
    runner = ScriptedRunner({})

    regrounded = _reground(tmp_path, repo, runner)

    assert runner.total == 0
    assert sum(len(problems) for problems in regrounded.failures.values()) == len(stale.nodes)
    assert set(regrounded.failures) == {PAGE, LEDGER_PAGE}
    assert regrounded.stamped == 0
    assert stale_files(repo, "tally") == (stale,)


def test_a_reading_that_ends_without_a_verdict_leaves_the_stamps(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    _change(repo)
    before = commits(repo)

    def _fails(_args: dict[str, object]) -> dict[str, object]:
        raise AgentTurnFailed("the model returned nothing")

    regrounded = _reground(tmp_path, repo, ScriptedRunner({"reground-file": _fails}))

    assert regrounded == Regrounded()
    assert commits(repo) == before
    assert len(stale_files(repo, "tally")) == 1


def test_what_the_reading_turn_wrote_is_put_back(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    _change(repo)

    def _edits(_args: dict[str, object]) -> dict[str, object]:
        _ = (repo / PAGE).write_text("rewritten\n", encoding="utf-8")
        return {"affected": [{"node": number, "instruction": ""} for number in range(1, 40)]}

    regrounded = _reground(tmp_path, repo, ScriptedRunner({"reground-file": _edits}))

    assert regrounded.stamped == 0
    assert git(repo, "status", "--porcelain") == ""


def test_a_book_citing_a_changed_file_is_regrounded_before_it_is_routed(app: App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = app("tally-cli")
    _change(repo)
    said: RunFailures = {PAGE: (PageProblem(PAGE, SAID),)}
    earlier: RunFailures = {PAGE: (PageProblem(PAGE, "a check of the last run failed"),)}

    def _handoff(_self: OkfBook, _flow: object, **_params: object) -> Regrounded:
        return Regrounded(failures=said, stamped=3)

    monkeypatch.setattr(OkfBook, "handoff", _handoff)
    book = OkfBook(repo_dir=str(repo), parent_records_dir=str(tmp_path), surfaces=(TALLY,))
    _ = book.start()
    keep_failures(tmp_path, "tally", earlier)

    routed = book.route_book(index=0)
    again = book.reground_book(index=0)

    assert routed.state == "reground_book"
    assert (again.state, again.params["regrounded"]) == ("route_book", True)
    assert book.route_book(index=0, regrounded=True).state == "copy_source"
    assert take_failures(tmp_path, "tally") == {}


def test_failures_kept_twice_for_a_page_are_both_read(tmp_path: Path) -> None:
    keep_failures(tmp_path, "tally", {PAGE: (PageProblem(PAGE, "first"),)})
    keep_failures(tmp_path, "tally", {PAGE: (PageProblem(PAGE, "second"),), LEDGER_PAGE: (PageProblem(LEDGER_PAGE, "third"),)})

    kept = take_failures(tmp_path, "tally")

    assert [problem.text for problem in kept[PAGE]] == ["first", "second"]
    assert [problem.text for problem in kept[LEDGER_PAGE]] == ["third"]


def test_a_scripted_reply_that_names_nothing_stamps_every_citation(app: App, tmp_path: Path) -> None:
    repo = app("tally-cli")
    _change(repo)

    regrounded = _reground(tmp_path, repo, ScriptedRunner({"reground-file": always({"affected": []})}))

    assert regrounded.failures == {}
    assert not cites_changed_file(repo, "tally")
