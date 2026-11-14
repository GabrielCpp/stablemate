"""A book reached by a screen surface gets a breadth pass before the owner: the entry files it names nowhere get a skeleton screen, eight to a turn."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest
from okf_book.main.flows import book_exits, build_flow
from okf_book.support import Reply
from workhorse.pyflow import AgentTurnFailed, Await, Continue

from workhorse_workflows.okf_book.main import python_book_flow
from workhorse_workflows.okf_book.main.python_book_flow import WritePythonBook

INVENTORY = "list-book-entries"
SKELETON = "write-screen-skeletons"
PAGES = ["ledger/pages/a.tsx", "ledger/pages/b.tsx", "ledger/pages/c.tsx"]


def _inventory(*entries: str) -> Reply:
    return lambda _args: {"entries": list(entries), "how": "ledger/routes.tsx"}


def _no_reply(_args: dict[str, object]) -> dict[str, object]:
    raise AgentTurnFailed("the turn ended")


def _handed(flow: WritePythonBook, *files: str) -> None:
    folder = flow.run_dir / python_book_flow.BREADTH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "handed.txt").write_text("".join(f"{file}\n" for file in files), encoding="utf-8")


def test_a_book_reached_by_a_screen_surface_starts_with_the_survey_and_no_owner_lap(tmp_path: Path) -> None:
    flow, _runner = build_flow(tmp_path, kind="web")

    step = flow.start()

    assert isinstance(step, Continue) and step.state == "survey"
    assert step.params == {"gate": "", "lap": 0}


def test_a_book_reached_by_no_screen_surface_starts_with_the_owner(tmp_path: Path) -> None:
    flow, _runner = build_flow(tmp_path, kind="http,grpc")

    step = flow.start()

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params == {"gate": "", "lap": 1}


def test_a_survey_whose_missing_list_is_empty_sends_the_owner_its_first_lap_with_an_empty_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unnamed=[])
    flow, runner = build_flow(tmp_path, kind="web")

    step = flow.survey(gate="", lap=0)

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params == {"gate": "", "lap": 1}
    assert runner.total == 0


def test_a_survey_hands_the_skeleton_state_the_entry_files_the_inventory_named_in_its_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = book_exits(monkeypatch, unnamed=PAGES, missing=1)
    flow, runner = build_flow(tmp_path, {INVENTORY: _inventory(PAGES[2], PAGES[0])}, kind="web")

    step = flow.survey(gate="red", lap=0)

    assert isinstance(step, Continue) and step.state == "skeleton"
    assert step.params == {"module": "services.ledger", "entries": [PAGES[2], PAGES[0]], "gate": "red", "lap": 0}
    assert seen[0][3:] == ["missing", "services.ledger", "--app", str(flow.code_root), "--under", "ledger"]
    sent = runner.args_of(INVENTORY)[0]
    assert sent["unnamed"] == PAGES
    assert sent["module"] == "services.ledger"


def test_a_survey_drops_an_entry_the_missing_list_does_not_hold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unnamed=PAGES, missing=1)
    flow, _runner = build_flow(tmp_path, {INVENTORY: _inventory(PAGES[1], "ledger/pages/gone.tsx")}, kind="web")

    step = flow.survey(gate="", lap=0)

    assert isinstance(step, Continue) and step.state == "skeleton"
    assert step.params["entries"] == [PAGES[1]]


def test_a_survey_drops_an_entry_a_skeleton_turn_was_already_handed_and_with_none_left_sends_the_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unnamed=PAGES, missing=1)
    flow, _runner = build_flow(tmp_path, {INVENTORY: _inventory(PAGES[0], PAGES[1])}, kind="web")
    _handed(flow, PAGES[0], PAGES[1])

    step = flow.survey(gate="", lap=1)

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params["lap"] == 2


def test_a_survey_that_sends_the_owner_after_a_breadth_pass_points_the_gate_at_the_notes_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unnamed=PAGES, missing=1)
    flow, _runner = build_flow(tmp_path, {INVENTORY: _inventory()}, kind="web")
    _handed(flow, PAGES[0])
    notes = f"The breadth pass left its notes on the entry files it tried under {flow.run_dir / 'breadth'}/."

    bare = flow.survey(gate="", lap=0)
    red = flow.survey(gate="the book is red", lap=1)

    assert isinstance(bare, Continue) and bare.params["gate"] == notes
    assert isinstance(red, Continue) and red.params["gate"] == f"the book is red\n\n{notes}"


def test_a_failed_inventory_turn_sends_the_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unnamed=PAGES, missing=1)
    flow, runner = build_flow(tmp_path, {INVENTORY: _no_reply}, kind="web")

    step = flow.survey(gate="", lap=0)

    assert runner.turns[INVENTORY] == 1
    assert isinstance(step, Continue) and step.state == "write"
    assert step.params == {"gate": "", "lap": 1}


def test_the_skeleton_state_hands_eight_files_to_one_turn_and_comes_back_for_the_rest(tmp_path: Path) -> None:
    files = [f"ledger/pages/p{n}.tsx" for n in range(11)]
    flow, runner = build_flow(tmp_path, {SKELETON: lambda _args: {"written": ["P"], "left": [], "odd": []}}, kind="web")

    step = flow.skeleton(module="services.ledger", entries=files, gate="g", lap=1)

    assert runner.args_of(SKELETON)[0]["files"] == files[:8]
    assert runner.nodes[0].power == "medium"
    assert runner.chains[0][1] == ""
    assert isinstance(step, Continue) and step.state == "skeleton"
    assert step.params == {"module": "services.ledger", "entries": files[8:], "gate": "g", "lap": 1}
    assert (flow.run_dir / "breadth/handed.txt").read_text(encoding="utf-8").split() == sorted(files[:8])


def test_the_last_batch_goes_to_the_check_with_the_lap_it_came_with(tmp_path: Path) -> None:
    flow, _runner = build_flow(tmp_path, {SKELETON: lambda _args: {"written": [], "left": [], "odd": []}}, kind="web")

    step = flow.skeleton(module="services.ledger", entries=PAGES, gate="", lap=2)

    assert isinstance(step, Continue) and step.state == "check"
    assert step.params == {"lap": 2}


def test_a_skeleton_turns_written_left_and_odd_lines_land_in_the_notes_folder_and_the_batch_in_the_handed_list(tmp_path: Path) -> None:
    reply: dict[str, object] = {"written": ["PageA"], "left": ["ledger/pages/b.tsx: a redirect"], "odd": ["ledger/pages/a.tsx: a typo in the title"]}
    flow, _runner = build_flow(tmp_path, {SKELETON: lambda _args: reply}, kind="web")
    _handed(flow, "ledger/pages/old.tsx")

    flow.skeleton(module="services.ledger", entries=PAGES[:2], gate="", lap=0)
    flow.skeleton(module="services.ledger", entries=PAGES[:2], gate="", lap=0)

    folder = flow.run_dir / "breadth"
    note = (folder / "ledger-pages-a-tsx.md").read_text(encoding="utf-8")
    assert note == (
        "## Written\n- PageA\n\n## Left\n- ledger/pages/b.tsx: a redirect\n\n## Odd for a user\n- ledger/pages/a.tsx: a typo in the title\n"
    )
    assert sorted(path.name for path in folder.iterdir()) == ["handed.txt", "ledger-pages-a-tsx.md"]
    assert (folder / "handed.txt").read_text(encoding="utf-8").split() == sorted(["ledger/pages/old.tsx", *PAGES[:2]])


def test_a_skeleton_turn_that_ends_without_a_reply_still_records_its_batch_as_handed(tmp_path: Path) -> None:
    flow, _runner = build_flow(tmp_path, {SKELETON: _no_reply}, kind="web")

    step = flow.skeleton(module="services.ledger", entries=PAGES, gate="", lap=0)

    assert isinstance(step, Continue) and step.state == "check"
    assert (flow.run_dir / "breadth/handed.txt").read_text(encoding="utf-8").split() == sorted(PAGES)


def test_a_red_missing_on_a_screen_book_goes_through_the_survey_with_the_same_lap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, missing=1)
    flow, _runner = build_flow(tmp_path, kind="web")

    step = flow.account(lap=2)

    assert isinstance(step, Continue) and step.state == "survey"
    assert step.params["lap"] == 2
    assert "`python -m ostler.book missing services.ledger` exited 1" in cast("str", step.params["gate"])
    assert "missing said cell 7 differs" in cast("str", step.params["gate"])


def test_a_red_missing_on_a_screen_book_after_the_last_lap_waits_for_the_operator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, missing=1)
    flow, _runner = build_flow(tmp_path, kind="web")

    step = flow.account(lap=python_book_flow.MAX_LAPS)

    assert isinstance(step, Await) and step.path == flow.run_dir / python_book_flow.RED_GATE


def test_the_missing_node_reads_the_unnamed_files_out_of_what_missing_printed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unnamed=PAGES, missing=1)

    gate = python_book_flow.python_book_missing(logging.getLogger("test"), tmp_path, "services.ledger", tmp_path, "ledger")

    assert gate.exit_code == 1
    assert gate.unnamed == tuple(PAGES)
    assert "## Files no element names" in gate.output


def test_two_surfaces_one_of_them_a_screen_surface_survey_only_the_screen_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = book_exits(monkeypatch, unnamed=PAGES, missing=1)
    flow, runner = build_flow(tmp_path, {INVENTORY: _inventory(PAGES[0])}, kind="http,web")

    step = flow.survey(gate="", lap=0)

    assert flow.screen_modules == ("services.ledger.web",)
    assert [argv[4] for argv in seen] == ["services.ledger.web"]
    assert runner.args_of(INVENTORY)[0]["module"] == "services.ledger.web"
    assert isinstance(step, Continue) and step.params["module"] == "services.ledger.web"
