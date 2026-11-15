"""A reasons pass follows the skeletons: the screens no decision names get their reasons written, five to a turn, and a screen handed once is never handed again."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
from okf_book.main.flows import book_exits, build_flow
from okf_book.support import Reply, ScriptedRunner, install_book_skill
from workhorse import templates
from workhorse.pyflow import AgentTurnFailed, Continue

from workhorse_workflows import okf_book
from workhorse_workflows.okf_book.main import python_book_flow
from workhorse_workflows.okf_book.main.python_book_flow import WritePythonBook

SKELETON = "write-screen-skeletons"
REASONS = "write-screen-reasons"
PAGES = ["ledger/pages/a.tsx", "ledger/pages/b.tsx"]
SCREENS = ["Home", "Detail", "Settings", "Billing", "Invoices", "Receipts", "Profile"]
NOTHING: dict[str, object] = {"written": [], "open": []}


def _skeletons(_args: dict[str, object]) -> dict[str, object]:
    return {"written": [], "left": [], "odd": []}


def _reasons(_args: dict[str, object]) -> dict[str, object]:
    return NOTHING


def _no_reply(_args: dict[str, object]) -> dict[str, object]:
    raise AgentTurnFailed("the turn ended")


def _handed(flow: WritePythonBook, *screens: str) -> None:
    folder = flow.run_dir / python_book_flow.REASONS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "handed.txt").write_text("".join(f"{screen}\n" for screen in screens), encoding="utf-8")


def _flow(tmp_path: Path, replies: dict[str, Reply] | None = None) -> tuple[WritePythonBook, ScriptedRunner]:
    return build_flow(tmp_path, {SKELETON: _skeletons, REASONS: _reasons, **(replies or {})}, kind="web")


def test_the_last_skeleton_batch_goes_to_the_reasons_state_when_a_screen_has_no_decision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unexplained=SCREENS[:2])
    flow, _runner = _flow(tmp_path)

    step = flow.skeleton(module="services.ledger", entries=PAGES, gate="", lap=2)

    assert isinstance(step, Continue) and step.state == "reasons"
    assert step.params == {"module": "services.ledger", "screens": SCREENS[:2], "lap": 2}


def test_the_last_skeleton_batch_goes_to_the_check_when_every_screen_is_explained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unexplained=[])
    flow, _runner = _flow(tmp_path)

    step = flow.skeleton(module="services.ledger", entries=PAGES, gate="", lap=2)

    assert isinstance(step, Continue) and step.state == "check"
    assert step.params == {"lap": 2}


def test_a_survey_with_no_entry_left_and_screens_to_explain_goes_to_the_reasons_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unnamed=[], unexplained=SCREENS[:3])
    flow, _runner = _flow(tmp_path)

    step = flow.survey(gate="", lap=1)

    assert isinstance(step, Continue) and step.state == "reasons"
    assert step.params == {"module": "services.ledger", "screens": SCREENS[:3], "lap": 1}


def test_a_survey_with_no_entry_left_and_nothing_to_explain_sends_the_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unnamed=[], unexplained=[])
    flow, runner = _flow(tmp_path)

    step = flow.survey(gate="", lap=1)

    assert isinstance(step, Continue) and step.state == "write"
    assert step.params == {"gate": "", "lap": 2}
    assert runner.total == 0


def test_the_reasons_state_hands_five_screens_to_one_turn_and_comes_back_for_the_rest(tmp_path: Path) -> None:
    flow, runner = _flow(tmp_path)

    step = flow.reasons(module="services.ledger", screens=SCREENS, lap=1)

    sent = runner.args_of(REASONS)[0]
    assert sent["screens"] == SCREENS[:5]
    assert sent["module_dir"] == "services/ledger"
    assert runner.nodes[0].power == "medium"
    assert runner.chains[0][1] == ""
    assert isinstance(step, Continue) and step.state == "reasons"
    assert step.params == {"module": "services.ledger", "screens": SCREENS[5:], "lap": 1}


def test_the_last_reasons_batch_goes_to_the_check_with_the_lap_it_came_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unexplained=[])
    flow, _runner = _flow(tmp_path)

    step = flow.reasons(module="services.ledger", screens=SCREENS[:2], lap=2)

    assert isinstance(step, Continue) and step.state == "check"
    assert step.params == {"lap": 2}


def test_a_screen_a_reasons_turn_was_already_handed_is_not_handed_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unexplained=SCREENS[:3])
    flow, _runner = _flow(tmp_path)
    _handed(flow, SCREENS[0])

    step = flow.reasons(module="services.ledger", screens=SCREENS[1:2], lap=1)

    assert isinstance(step, Continue) and step.state == "reasons"
    assert step.params["screens"] == [SCREENS[2]]


def test_a_reasons_turns_written_and_open_lines_land_in_the_notes_folder_and_the_batch_in_the_handed_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unexplained=[])
    reply: dict[str, object] = {"written": ["home-exists"], "open": ["Detail: who may open it?"]}
    flow, _runner = _flow(tmp_path, {REASONS: lambda _args: reply})
    _handed(flow, "Old")

    flow.reasons(module="services.ledger", screens=SCREENS[:2], lap=0)

    folder = flow.run_dir / "reasons"
    note = (folder / "Home.md").read_text(encoding="utf-8")
    assert note == "## Written\n- home-exists\n\n## Open questions\n- Detail: who may open it?\n"
    assert sorted(path.name for path in folder.iterdir()) == ["Home.md", "handed.txt"]
    assert (folder / "handed.txt").read_text(encoding="utf-8").split() == sorted(["Old", *SCREENS[:2]])


def test_a_reasons_turn_that_ends_without_a_reply_still_records_its_batch_as_handed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unexplained=[])
    flow, _runner = _flow(tmp_path, {REASONS: _no_reply})

    step = flow.reasons(module="services.ledger", screens=SCREENS[:2], lap=0)

    assert isinstance(step, Continue) and step.state == "check"
    assert (flow.run_dir / "reasons/handed.txt").read_text(encoding="utf-8").split() == sorted(SCREENS[:2])


def test_python_book_unexplained_asks_the_book_for_its_unexplained_screens_and_returns_the_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = book_exits(monkeypatch, unexplained=["Home", "Detail"])

    found = python_book_flow.python_book_unexplained(logging.getLogger("test"), tmp_path, "services.ledger")

    assert found == ["Home", "Detail"]
    assert seen[0][3:] == ["decisions", "services.ledger", "--unexplained", "--kind", "screen"]


def test_a_book_command_that_fails_gives_no_screen_to_explain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unexplained=["Home"], decisions=2)

    found = python_book_flow.python_book_unexplained(logging.getLogger("test"), tmp_path, "services.ledger")

    assert found == []


def test_the_reasons_prompt_renders_with_the_batch_the_module_folder_and_the_reply_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    book_exits(monkeypatch, unexplained=[])
    flow, runner = _flow(tmp_path)
    flow.reasons(module="services.ledger", screens=SCREENS[:2], lap=0)
    install_book_skill(tmp_path / "home", monkeypatch)

    rendered = templates.render(python_book_flow.REASONS_PROMPT, runner.args_of(REASONS)[0], Path(okf_book.__file__).parent)

    assert "- Home\n- Detail\n" in rendered
    assert "under `services/ledger/decisions/`" in rendered
    assert "python -m ostler.book check services.ledger --app " in rendered
    assert '"written"' in rendered and '"open"' in rendered
