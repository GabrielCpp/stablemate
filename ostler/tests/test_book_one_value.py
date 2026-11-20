"""The run lists each answer field with a value domain that it only ever saw in one value."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from book_todo import module, run_book
from ostler.book import Answer, Endpoint
from ostler.book.http import Bool, Bytes, Enum, Field, Id, Int, List, Num, Object, Str, Token, Witness
from ostler.book.witness import Because, Unseen, report


class Thing:
    pass


class Show(Endpoint):
    path = "/show"
    answers = (
        Answer(200, Object(
            "Show",
            name=Field(Str()),
            when=Field(Str(format="date")),
            id=Field(Id(Thing, Str())),
            cursor=Field(Token("page"), required=False),
            blob=Field(Bytes(), required=False),
            colour=Field(Enum(("red", "blue"))),
            live=Field(Bool()),
            count=Field(Int()),
            price=Field(Num()),
            hidden=Field(Enum(("a", "b")), opaque="the app picks it"),
            sorted_by=Field(Enum(("a", "b")), ignores=("order",), why="the app may reorder"),
        ), "the thing"),
    )


class Rows(Endpoint):
    path = "/rows"
    answers = (Answer(200, Object("Rows", items=Field(List(Object("Row", status=Field(Enum(("open", "done"))))))), "the rows"),)


def _show(**changed: object) -> dict[str, object]:
    body: dict[str, object] = {"name": "n", "when": "2026-01-01", "id": "i1", "cursor": "tok", "blob": "AA==", "colour": "red",
                               "live": True, "count": 3, "price": 1.5, "hidden": "a", "sorted_by": "a"}
    return {**body, **changed}


def _seen(endpoint: type[Endpoint], *bodies: object) -> Witness:
    seen = Witness()
    for body in bodies:
        seen.see(endpoint, endpoint.answers[0], body)
    return seen


def _listed(seen: Witness, unseen: tuple[Unseen, ...] = ()) -> list[str]:
    return report([Show, Rows], seen, unseen).single_lines()


def test_an_enum_seen_with_one_value_is_listed_with_that_value():
    assert "- Show 200: colour was always 'red'; read it in a second value (a fixture or a scene that differs), or it proves nothing" in _listed(_seen(Show, _show()))


def test_an_enum_seen_with_two_values_is_not_listed():
    lines = _listed(_seen(Show, _show(), _show(colour="blue")))
    assert not any("colour" in line for line in lines)


def test_a_bool_an_int_and_a_num_are_listed_in_one_value_and_not_in_two():
    one = "\n".join(_listed(_seen(Show, _show())))
    assert "live was always True" in one
    assert "count was always 3" in one
    assert "price was always 1.5" in one
    two = "\n".join(_listed(_seen(Show, _show(), _show(live=False, count=4, price=2.5))))
    assert "live" not in two and "count" not in two and "price" not in two


def test_a_falsy_value_is_a_value():
    lines = "\n".join(_listed(_seen(Show, _show(live=False, count=0))))
    assert "live was always False" in lines
    assert "count was always 0" in lines


def test_a_str_an_id_a_token_and_bytes_field_is_never_listed():
    lines = "\n".join(_listed(_seen(Show, _show())))
    for name in ("name", "when", "id", "cursor", "blob"):
        assert f" {name} was" not in lines


def test_a_field_not_compared_is_never_listed():
    lines = "\n".join(_listed(_seen(Show, _show())))
    assert "hidden" not in lines
    assert "sorted_by" not in lines


def test_a_field_under_a_list_pools_its_items():
    one = _listed(_seen(Rows, {"items": [{"status": "open"}, {"status": "open"}]}))
    assert "- Rows 200: items[].status was always 'open'; read it in a second value (a fixture or a scene that differs), or it proves nothing" in one
    assert not any("Rows" in line for line in _listed(_seen(Rows, {"items": [{"status": "open"}, {"status": "done"}]})))


def test_values_pool_across_separate_answers():
    assert not any("Rows" in line for line in _listed(_seen(Rows, {"items": [{"status": "open"}]}, {"items": [{"status": "done"}]})))


def test_a_field_never_seen_with_a_real_value_is_not_listed():
    assert not any("Rows" in line for line in _listed(_seen(Rows, {"items": []})))
    assert not any("colour" in line for line in _listed(_seen(Show, _show(colour=None))))


def test_a_field_declared_unseen_is_not_listed():
    unseen = (Unseen(Show, "200: colour", Because.NEVER_FILLED, "the app never varies it"),)
    lines = "\n".join(_listed(_seen(Show, _show()), unseen))
    assert "colour" not in lines
    assert "live" in lines


def test_enums_and_bools_come_before_numbers_within_an_endpoint():
    lines = _listed(_seen(Show, _show()))
    assert [line.split(" ")[3] for line in lines] == ["colour", "live", "count", "price"]


def test_the_endpoints_follow_the_order_the_book_declares_them():
    seen = _seen(Rows, {"items": [{"status": "open"}]})
    seen.merge(_seen(Show, _show()))
    lines = _listed(seen)
    assert lines[0].startswith("- Show ")
    assert lines[-1].startswith("- Rows ")


def test_no_value_domain_field_with_one_value_reads_nothing():
    assert report([Show], Witness()).single_lines() == []


def test_merge_keeps_the_values_of_both_witnesses():
    left = _seen(Show, _show())
    left.merge(_seen(Show, _show(colour="blue")))
    assert not any("colour" in line for line in report([Show], left).single_lines())
    assert left.values[(Show, 200)]["colour"] == {"red", "blue"}


def test_a_witness_keeps_at_most_two_values_of_a_field():
    seen = _seen(Show, *(_show(count=n) for n in range(50)))
    assert len(seen.values[(Show, 200)]["count"]) == 2


@pytest.fixture
def todo_app() -> Iterator:
    server = module("app").TodoServer().start()
    yield server
    server.stop()


def test_a_full_run_prints_the_section_and_the_file_carries_it_without_changing_the_exit_code(todo_app, tmp_path: Path):
    out = tmp_path / "out"
    done = run_book(["run", "services.api", "--no-stack", "--out", str(out)], todo_app.port)
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    head = next(i for i, line in enumerate(lines) if line.startswith("Seen with one value only"))
    assert any("answers and" in line and "fields witnessed" in line for line in lines[:head])
    assert head < len(lines) - 1
    written = (out / "api-witness.md").read_text()
    assert "## Seen with one value only" in written


def test_a_scoped_run_says_the_section_is_not_judged(todo_app, tmp_path: Path):
    out = tmp_path / "out"
    done = run_book(["run", "services.api", "--no-stack", "--partial", "--out", str(out)], todo_app.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Seen with one value only: not judged on a partial run" in done.stdout
    assert "not judged on a partial run" in (out / "api-witness.md").read_text()


def test_endpoints_that_showed_a_field_in_the_same_single_value_share_a_line():
    seen = _seen(Show, _show())
    seen.see(Rows, Rows.answers[0], {"items": [{"status": "open"}]})

    class Again(Show):
        pass

    seen.see(Again, Again.answers[0], _show())
    lines = report([Show, Again, Rows], seen, ()).single_lines()
    assert "- Show, Again 200: colour was always 'red'; read it in a second value (a fixture or a scene that differs), or it proves nothing" in lines
    assert sum("colour" in line for line in lines) == 1
