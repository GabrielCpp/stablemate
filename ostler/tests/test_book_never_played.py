"""The run records which plays exercised each stated element and reports the ones nobody did."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ostler.book import cli
from ostler.book.runner import Deliveries

from book_desk import Tap
from book_fakes import Arrives, Ghost, Haunting, MISSING, Remove, Shelf, Stocking, Sweep, TAKEN, shelf_book, shelf_matrices, run_shelf
from ostler.book import Because, Defect, Unseen
from ostler.book.journey import StepResult

TITLE = "Stated and never played"


@pytest.fixture(autouse=True)
def untapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Deliveries, "role", None)


def section_of(out: str) -> list[str]:
    lines = out.splitlines()
    start = lines.index(TITLE)
    end = next(n for n in range(start + 1, len(lines)) if not lines[n].startswith(("-", " ")))
    return lines[start + 1:end]


def played_by(out_dir: Path) -> dict[str, dict[str, list[str]]]:
    return json.loads((out_dir / "shelf-played.json").read_text())


def full(monkeypatch, tmp_path, capsys, **book):
    code, out = run_shelf(monkeypatch, shelf_book(matrices=shelf_matrices(), **book), tmp_path, capsys)
    return code, out, played_by(tmp_path)


def declaring(*unseen: Unseen):
    matrices = shelf_matrices()
    return matrices, shelf_book(matrices=matrices, unseen=unseen)


def everything_declared():
    matrices = shelf_matrices()
    return matrices, (Unseen(Ghost, Because.RUNTIME, "the runtime cannot arrange a haunting"),
                      Unseen(Sweep, Because.OUTSIDE, "a broom outside the app sweeps"),
                      Unseen(Remove, Because.NO_ACCOUNT, "no account can remove"),
                      Unseen(MISSING, Because.RUNTIME, "the runtime cannot read the refusal"),
                      Unseen(matrices[1].scenes[0], Because.OUTSIDE, "nobody can reach the closet"))


def verdict_of(out: str) -> list[str]:
    lines = out.splitlines()
    return lines[lines.index("verdict"):]


def test_an_outside_happening_a_step_arranged_is_played_by_the_journey(monkeypatch, tmp_path, capsys):
    _, out, played = full(monkeypatch, tmp_path, capsys)
    assert played["outside happening"]["Arrives"] == ["Stocking"]
    assert not any("outside happening Arrives" in line for line in section_of(out))


def test_an_outside_happening_no_play_arranges_is_listed_with_what_closes_it(monkeypatch, tmp_path, capsys):
    _, out, played = full(monkeypatch, tmp_path, capsys)
    assert played["outside happening"]["Ghost"] == []
    [line] = [line for line in section_of(out) if line.startswith("- outside happening Ghost: ")]
    assert "no step, cell or given arranges it; arrange it in a journey or a matrix; it carries Haunt; or declare it: " in line


def test_an_action_carried_only_by_an_unplayed_happening_is_reported_on_its_line_alone(monkeypatch, tmp_path, capsys):
    _, out, played = full(monkeypatch, tmp_path, capsys)
    assert played["action"]["Haunt"] == []
    assert not any(line.startswith("- action Haunt") for line in section_of(out))


def test_an_action_nothing_carries_is_listed_on_its_own_line(monkeypatch, tmp_path, capsys):
    _, out, _ = full(monkeypatch, tmp_path, capsys)
    assert any(line.startswith("- action Sweep: ") for line in section_of(out))


def test_an_action_a_step_took_and_the_model_accepted_is_played(monkeypatch, tmp_path, capsys):
    _, out, played = full(monkeypatch, tmp_path, capsys)
    assert played["action"]["Put"] == ["Stocking", "shelf:empty x put", "shelf:stocked x put"]
    assert played["action"]["Restock"] == ["Stocking"]
    assert not any(line.startswith("- action Put") for line in section_of(out))


def test_a_rule_drawn_through_two_actions_is_one_rule_with_the_plays_once_each(monkeypatch, tmp_path, capsys):
    _, _, played = full(monkeypatch, tmp_path, capsys)
    assert list(played["rule"]).count("already-on-the-shelf") == 1
    assert played["rule"]["already-on-the-shelf"] == ["Stocking"]


def test_a_rule_no_play_drew_is_listed(monkeypatch, tmp_path, capsys):
    _, out, played = full(monkeypatch, tmp_path, capsys)
    assert played["rule"]["not-on-the-shelf"] == []
    assert any(line.startswith("- rule not-on-the-shelf: ") for line in section_of(out))


def test_a_scene_a_cell_arranged_is_played_and_one_no_cell_reached_is_listed(monkeypatch, tmp_path, capsys):
    _, out, played = full(monkeypatch, tmp_path, capsys)
    assert played["scene"]["shelf:stocked"] == ["shelf:stocked x put"]
    assert played["scene"]["shelf:empty"] == ["shelf:empty x put"]
    assert played["scene"]["closet:never"] == []
    assert any(line.startswith("- scene closet:never: ") for line in section_of(out))


def test_the_played_by_file_has_the_four_kinds_with_sorted_keys_and_the_unplayed_as_empty_lists(monkeypatch, tmp_path, capsys):
    _, _, played = full(monkeypatch, tmp_path, capsys)
    text = (tmp_path / "shelf-played.json").read_text()
    assert list(played) == sorted(played) == ["action", "outside happening", "rule", "scene"]
    assert all(list(kind) == sorted(kind) for kind in played.values())
    assert json.loads(text) == played
    assert played["action"]["Sweep"] == []


def test_the_section_comes_before_the_verdict_and_an_undeclared_element_makes_the_run_red_under_never_played(monkeypatch, tmp_path, capsys):
    code, out, _ = full(monkeypatch, tmp_path, capsys)
    lines = out.splitlines()
    assert lines.index(TITLE) < lines.index("verdict")
    assert code == 1
    assert "red: never played" in lines


def test_each_kind_that_no_play_exercised_and_the_book_leaves_undeclared_is_a_red_line_with_the_form_to_declare_it(monkeypatch, tmp_path, capsys):
    _, out, _ = full(monkeypatch, tmp_path, capsys)
    lines = section_of(out)
    want = {"outside happening Ghost": "Unseen(Ghost, Because.RUNTIME | OUTSIDE | NO_ACCOUNT, \"why\")",
            "action Sweep": "Unseen(Sweep, Because.RUNTIME | OUTSIDE | NO_ACCOUNT, \"why\")",
            "rule not-on-the-shelf": "Unseen(<rule variable>, Because.RUNTIME | OUTSIDE | NO_ACCOUNT, \"why\")",
            "scene closet:never": "Unseen(<scene variable>, Because.RUNTIME | OUTSIDE | NO_ACCOUNT, \"why\")"}
    for head, form in want.items():
        [line] = [line for line in lines if line.startswith(f"- {head}: ")]
        assert line.endswith(f"or declare it: {form}")


def test_the_streaming_and_no_tap_lines_never_make_the_run_red(monkeypatch, tmp_path, capsys):
    matrices, unseen = everything_declared()
    monkeypatch.setattr(cli, "unplayed_lines", lambda service: ["not played: Teams/WatchOne streams its answer"])
    code, out = run_shelf(monkeypatch, shelf_book(matrices=matrices, unseen=unseen), tmp_path, capsys)
    assert any("no tap" in line for line in section_of(out))
    assert "- not played: Teams/WatchOne streams its answer" in section_of(out)
    assert code == 0
    assert verdict_of(out)[-1] == "green"


def test_a_declared_element_is_listed_with_its_reason_and_is_not_red(monkeypatch, tmp_path, capsys):
    matrices, unseen = everything_declared()
    code, out = run_shelf(monkeypatch, shelf_book(matrices=matrices, unseen=unseen), tmp_path, capsys)
    lines = section_of(out)
    assert "- outside happening Ghost declared unseen (RUNTIME): the runtime cannot arrange a haunting" in lines
    assert "- action Sweep declared unseen (OUTSIDE): a broom outside the app sweeps" in lines
    assert "- action Remove declared unseen (NO_ACCOUNT): no account can remove" in lines
    assert "- rule not-on-the-shelf declared unseen (RUNTIME): the runtime cannot read the refusal" in lines
    assert "- scene closet:never declared unseen (OUTSIDE): nobody can reach the closet" in lines
    assert not any("or declare it" in line for line in lines)
    assert code == 0
    assert verdict_of(out)[-1] == "green"


def test_a_declaration_the_run_contradicts_is_red_as_stale(monkeypatch, tmp_path, capsys):
    matrices, unseen = everything_declared()
    stale = (*unseen, Unseen(Arrives, Because.RUNTIME, "no step arranges it"), Unseen(TAKEN, Because.OUTSIDE, "no play draws it"))
    code, out = run_shelf(monkeypatch, shelf_book(matrices=matrices, unseen=stale), tmp_path, capsys)
    lines = section_of(out)
    assert ("- outside happening Arrives: declared unseen but played by Stocking; delete the declaration (fails the run)"
            in lines)
    assert any(line.startswith("- rule already-on-the-shelf: declared unseen but played by Stocking") for line in lines)
    assert code == 1
    assert "red: never played" in verdict_of(out)


def test_a_declaration_of_a_scene_the_book_does_not_state_is_red_as_stale(monkeypatch, tmp_path, capsys):
    matrices, unseen = everything_declared()
    other = Unseen(shelf_matrices()[1].scenes[0], Because.OUTSIDE, "a scene of no matrix of the book")
    code, out = run_shelf(monkeypatch, shelf_book(matrices=matrices, unseen=(*unseen, other)), tmp_path, capsys)
    assert "- scene never: declared unseen but the book states no such scene; delete the declaration (fails the run)" in section_of(out)
    assert code == 1


def test_declaring_the_happening_covers_the_action_it_carries_and_lists_it_once(monkeypatch, tmp_path, capsys):
    matrices, unseen = everything_declared()
    code, out = run_shelf(monkeypatch, shelf_book(matrices=matrices, unseen=unseen), tmp_path, capsys)
    assert sum("Haunt" in line.split(":")[0] for line in section_of(out)) == 0
    assert code == 0


def test_an_undeclared_happening_is_the_only_red_line_for_the_action_it_carries(monkeypatch, tmp_path, capsys):
    matrices, unseen = everything_declared()
    code, out = run_shelf(monkeypatch, shelf_book(matrices=matrices, unseen=unseen[1:]), tmp_path, capsys)
    red = [line for line in section_of(out) if "or declare it" in line]
    assert [line.split(":")[0] for line in red] == ["- outside happening Ghost"]
    assert code == 1


def test_a_rule_a_known_defect_covers_is_not_reported(monkeypatch, tmp_path, capsys):
    defect = Defect[str, Shelf]("removes nothing", lambda a, s, by: False, status=200, over=MISSING)
    monkeypatch.setattr(Remove, "defects", (defect,))
    _, out, _ = full(monkeypatch, tmp_path, capsys)
    assert not any("not-on-the-shelf" in line for line in section_of(out))


def test_a_streaming_call_is_a_group_of_the_section_with_its_wording(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "unplayed_lines", lambda service: ["not played: Teams/WatchOne streams its answer"])
    _, out, _ = full(monkeypatch, tmp_path, capsys)
    assert "- not played: Teams/WatchOne streams its answer" in section_of(out)
    assert out.count("not played: Teams/WatchOne") == 1


def test_an_environment_with_no_tap_gets_one_line_naming_the_events_the_played_actions_emit(monkeypatch, tmp_path, capsys):
    _, out, _ = full(monkeypatch, tmp_path, capsys)
    [line] = [line for line in section_of(out) if "no tap" in line]
    assert "shelf.stocked (Put)" in line
    assert "shelf.haunted" not in line
    assert "a delivery that taps closes it" in line


def test_an_environment_with_a_tap_gets_no_such_line():
    from ostler.book.played import PlayedBy, never_played

    found = PlayedBy()
    found.add("action", "Put", "Stocking")
    book = shelf_book(delivery=Tap())
    Deliveries.begin(book.environments["local"].delivery)
    assert not [line for line in never_played(book, found, [], scoped=False, skipped=set()).lines if "no tap" in line]


def test_a_book_with_everything_played_says_so_in_one_line():
    from ostler.book.played import PlayedBy, never_played

    found = PlayedBy()
    found.add("rule", "already-on-the-shelf", "Stocking")
    assert never_played(shelf_book(), found, [], scoped=False, skipped=set()).lines == [f"{TITLE}: nothing"]


def test_a_scoped_run_says_it_judged_nothing_and_still_writes_the_file(monkeypatch, tmp_path, capsys):
    code, out = run_shelf(monkeypatch, shelf_book(matrices=shelf_matrices()), tmp_path, capsys, "--partial", "--journey", "Stocking")
    assert f"{TITLE}: not judged on a partial run" in out.splitlines()
    assert TITLE not in out.splitlines()
    assert "never played" not in " ".join(verdict_of(out))
    assert played_by(tmp_path)["outside happening"]["Arrives"] == ["Stocking"]


def test_what_a_skipped_play_could_have_exercised_is_not_judged_and_the_rest_is(monkeypatch, tmp_path, capsys):
    service = shelf_book(journeys=(Stocking, Haunting), cannot=(Ghost,))
    code, out = run_shelf(monkeypatch, service, tmp_path, capsys)
    lines = section_of(out)
    assert not any(line.startswith("- outside happening Ghost") for line in lines)
    start = lines.index("  not judged here:")
    judged = lines[start + 1:]
    assert "    - outside happening Ghost" in judged
    assert "    - rule not-on-the-shelf" in judged
    assert any(line.startswith("- action Sweep: ") for line in lines)
    assert not any("Ghost" in line or "not-on-the-shelf" in line for line in lines[:start])


def test_a_skipped_play_leaves_what_it_could_have_exercised_out_of_the_red(monkeypatch, tmp_path, capsys):
    matrices, unseen = everything_declared()
    service = shelf_book(journeys=(Stocking, Haunting), cannot=(Ghost,), matrices=matrices,
                         unseen=tuple(u for u in unseen if u.of not in (Ghost, MISSING)))
    code, out = run_shelf(monkeypatch, service, tmp_path, capsys)
    assert "  not judged here:" in section_of(out)
    assert "never played" not in " ".join(verdict_of(out))


def test_a_play_of_an_input_class_that_drew_a_refusal_and_passed_plays_the_rule():
    from ostler.book.inputs import InputClass, Sent
    from ostler.book.outcome import Done, Refusal
    from ostler.book.played import PlayedBy

    from book_fakes import Puts, TAKEN

    class Probe:
        pass

    taken = StepResult(Puts("a"), Refusal("already on the shelf", 400, TAKEN), Refusal("already on the shelf", 400), (), (), True)
    sent = Sent(Probe, InputClass("body", "id empty", "", None, False), True, taken=taken)
    found = PlayedBy()
    found.step(sent.text, taken)
    assert found.by["rule"] == {"already-on-the-shelf": [sent.text]}
    ok = StepResult(Puts("a"), Done(), Done(), (), (), True)
    found.step("Probe fine", ok)
    assert found.by["action"] == {"Put": ["Probe fine"]}


def test_a_rule_a_known_defect_covers_is_played_when_the_run_met_the_defect():
    from ostler.book import Defect
    from ostler.book.outcome import Flawed, Refusal
    from ostler.book.played import PlayedBy

    from book_fakes import Puts, TAKEN

    defect = Defect[str, Shelf]("accepted twice", lambda a, s, by: True, status=200, over=TAKEN)
    meant = Refusal("already on the shelf", 400)
    result = StepResult(Puts("a"), Flawed(defect, meant), None, (), (), True, known=defect)
    found = PlayedBy()
    found.step("Stocking", result)
    assert found.by["rule"] == {"already-on-the-shelf": ["Stocking"]}


def test_an_action_other_actions_extend_is_a_base_and_is_not_stated_as_unplayed(monkeypatch, tmp_path, capsys):
    _, out, played = full(monkeypatch, tmp_path, capsys)
    assert "Shelver" not in played["action"]
    assert "Put" in played["action"]
    assert not any("Shelver" in line for line in section_of(out))


def test_an_action_only_a_streaming_call_carries_is_left_to_the_streaming_line():
    import dataclasses

    from book_fakes import RemoveItem
    from ostler.book.played import PlayedBy, never_played

    class WatchShelf(RemoveItem):
        streams = "answer"
        carries = Sweep

    found = PlayedBy()
    found.stated("action", "Sweep")
    found.stated("action", "Remove")
    book = dataclasses.replace(shelf_book(), endpoints=(WatchShelf, RemoveItem))
    judged = never_played(book, found, [], scoped=False, skipped=set(), streaming=["not played: Shelf/Watch streams its answer"])
    assert judged.red == ["action Remove"]
    assert not any(line.startswith("- action Sweep") for line in judged.lines)
