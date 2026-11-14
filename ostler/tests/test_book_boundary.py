"""A book that names a record its neighbour owns, played against the stand-in todo app and the digest service in front of it."""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Iterator

import pytest

from book_todo import FIXTURE, module, run_book, runtime

BUGGY = "digest-keeps-scheduled"
HIDING = "digest-hides-missing"
DROPPING = "digest-drops-done"


@pytest.fixture
def todo_app() -> Iterator:
    server = module("app").TodoServer().start()
    yield server
    server.stop()


@pytest.fixture
def digest_app(todo_app) -> Iterator:
    server = module("digest.app").DigestServer(todo_app.url).start()
    yield server
    server.stop()


@pytest.fixture
def buggy_digest(todo_app) -> Iterator:
    server = module("digest.app").DigestServer(todo_app.url, bug=BUGGY).start()
    yield server
    server.stop()


@pytest.fixture
def hiding_digest(todo_app) -> Iterator:
    server = module("digest.app").DigestServer(todo_app.url, bug=HIDING).start()
    yield server
    server.stop()


@pytest.fixture
def dropping_digest(todo_app) -> Iterator:
    server = module("digest.app").DigestServer(todo_app.url, bug=DROPPING).start()
    yield server
    server.stop()


def play(todo_app, digest_app, out: Path, *more: str, cwd: Path = FIXTURE) -> subprocess.CompletedProcess[str]:
    return run_book(["run", "services.digest", "--no-stack", "--out", str(out), *more], todo_app.port, cwd=cwd,
                    digest=digest_app.port)


def copied(into: Path) -> Path:
    copy = into / "book_todo"
    shutil.copytree(FIXTURE, copy, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
    return copy


def test_a_derivation_with_no_docstring_is_refused_where_it_is_declared():
    from ostler.book import BookError, Passes

    def derived(answer):
        return answer

    with pytest.raises(BookError, match="docstring"):
        Passes(asks=lambda step: None, derived=derived)


def test_the_id_of_a_needed_record_cannot_be_read_before_the_given_is_arranged():
    from ostler.book import BookError, Foreign, Needs

    record = module("services.api.model.todo").TodoRecord
    needed = Needs(Foreign(record, owner="services.api", reads=("id",)), "overdue")
    with pytest.raises(BookError, match="not arranged"):
        needed.id
    with pytest.raises(BookError, match="not arranged"):
        needed.record


def test_a_journey_that_needs_a_neighbours_record_in_a_state_gets_a_record_the_owners_book_made_in_that_state(
        todo_app, digest_app, tmp_path: Path):
    done = play(todo_app, digest_app, tmp_path / "out")
    assert "PASS  AnOverdueTodoIsInTheDigest" in done.stdout, done.stdout + done.stderr
    assert [todo.title for todo in todo_app.store.todos] == ["Fix the gate", "Fix the gate"]
    overdue, scheduled = (todo_app.store.view(todo) for todo in todo_app.store.todos)
    assert (overdue["status"], scheduled["status"]) == ("overdue", "scheduled")
    answer = digest_app.url + "/digest/" + overdue["id"]
    from urllib.request import Request, urlopen

    with urlopen(Request(answer, headers={"Authorization": "Bearer test-token"})) as reply:
        assert reply.status == 200


def test_a_read_that_passes_the_owners_answer_on_passes_when_the_app_derives_what_the_book_states(
        todo_app, digest_app, tmp_path: Path):
    done = play(todo_app, digest_app, tmp_path / "out")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "3 pass, 0 known defects, 0 fail" in done.stdout


def test_with_the_digest_keeping_scheduled_todos_the_journey_fails_and_the_note_holds_both_answers(
        todo_app, buggy_digest, tmp_path: Path):
    done = play(todo_app, buggy_digest, tmp_path / "out")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "FAIL  AnOverdueTodoIsInTheDigest" in done.stdout
    assert "at: GET /digest" in done.stdout
    assert "ReadDigest" in done.stdout
    assert "the overdue todos the owner lists" in done.stdout
    assert '"count": 2' in done.stdout
    assert '"count": 1' in done.stdout


def test_the_owners_book_changes_how_its_scene_is_reached_and_the_digest_book_untouched_still_plays_green(
        todo_app, digest_app, tmp_path: Path):
    copy = copied(tmp_path)
    lifecycle = copy / "services" / "api" / "model" / "lifecycle.py"
    before = lifecycle.read_text()
    after = before.replace("(AddTodo(scheduled(today, 2, title=CHORE)), SetClock(Clock(today + timedelta(days=3))))",
                           "(AddTodo(scheduled(today, 1, title=CHORE)), SetClock(Clock(today + timedelta(days=8))))")
    assert after != before
    lifecycle.write_text(after)
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", "AnOverdueTodoIsInTheDigest", "--partial", cwd=copy)
    assert "PASS  AnOverdueTodoIsInTheDigest" in done.stdout, done.stdout + done.stderr
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_state_the_owners_matrices_do_not_have_fails_the_given_and_names_the_states_they_have(
        todo_app, digest_app, tmp_path: Path):
    copy = copied(tmp_path)
    journey = copy / "services" / "digest" / "journeys" / "an_overdue_todo_is_in_the_digest.py"
    journey.write_text(journey.read_text().replace('Needs(TODO, "overdue")', 'Needs(TODO, "archived")'))
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", "AnOverdueTodoIsInTheDigest", "--partial", cwd=copy)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "FAIL  AnOverdueTodoIsInTheDigest" in done.stdout
    assert "services.api" in done.stdout and "archived" in done.stdout
    for known in ("(none)", "unscheduled", "scheduled", "overdue", "Serving", "StoreDown"):
        assert known in done.stdout


def owners_after(arguments: list[str], port: int, digest: int | None = None) -> subprocess.CompletedProcess[str]:
    code = ("import sys; from ostler.book.cli import main; from ostler.book.owners import Owners; "
            "code = main(sys.argv[1:]); print('OWNERS', sorted(Owners.loaded)); sys.exit(code)")
    return subprocess.run([sys.executable, "-c", code, *arguments], cwd=FIXTURE, env=runtime(port, digest=digest),
                          capture_output=True, text=True, check=False)


def test_a_book_with_no_reference_to_a_neighbour_loads_no_other_book(todo_app, digest_app, tmp_path: Path):
    done = owners_after(["run", "services.api", "--no-stack", "--out", str(tmp_path / "api")], todo_app.port, digest_app.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "OWNERS []" in done.stdout
    other = owners_after(["run", "services.digest", "--no-stack", "--out", str(tmp_path / "digest")], todo_app.port,
                         digest_app.port)
    assert "OWNERS ['services.api']" in other.stdout, other.stdout + other.stderr


def test_the_digest_book_holds_no_lifecycle_rule_or_action():
    from ostler.book.search import actions_of

    service = module("services.digest.service").service
    assert service.matrices == ()
    assert service.outside == ()
    assert service.records == ()
    assert actions_of(service, "services.digest") == []
    assert all(endpoint.carries is None for endpoint in service.endpoints)
    model = service.new_model(date.today())
    assert model.rules == ()
    assert not model.collections()


def edited(copy: Path, relative: str, before: str, after: str) -> None:
    file = copy / relative
    text = file.read_text()
    assert before in text, before
    file.write_text(text.replace(before, after))


REFUSALS = "TheTodoApiTurnsACallerAway"
FINISHING = "AnOverdueTodoIsFinishedFromTheDigest"


def test_an_owners_refusal_comes_back_as_the_book_maps_it_and_the_step_passes(todo_app, digest_app, tmp_path: Path):
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", REFUSALS, "--partial")
    assert f"PASS  {REFUSALS}" in done.stdout, done.stdout + done.stderr
    assert done.returncode == 0, done.stdout + done.stderr


def test_with_the_digest_hiding_a_missing_todo_the_journey_fails_and_the_note_holds_the_three_statuses(
        todo_app, hiding_digest, tmp_path: Path):
    done = play(todo_app, hiding_digest, tmp_path / "out", "--journey", REFUSALS, "--partial")
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"FAIL  {REFUSALS}" in done.stdout
    assert "with 404" in done.stdout
    assert "maps it to 404" in done.stdout
    assert "the app answered 500" in done.stdout


def test_a_claim_that_the_owner_refuses_fails_when_the_owner_answers(todo_app, digest_app, tmp_path: Path):
    copy = copied(tmp_path)
    journey = "services/digest/journeys/an_overdue_todo_is_in_the_digest.py"
    edited(copy, journey, "import Journey, Needs", "import Journey, Needs, OwnerRefused")
    edited(copy, journey, "        yield ReadDigestEntry(self.chore)\n",
           "        yield ReadDigestEntry(self.chore)\n        yield OwnerRefused(ReadDigestEntry(self.chore))\n")
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", "AnOverdueTodoIsInTheDigest", "--partial", cwd=copy)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "FAIL  AnOverdueTodoIsInTheDigest" in done.stdout
    assert "answered 200" in done.stdout and "did not refuse" in done.stdout


def test_a_claim_that_the_owner_refuses_fails_when_the_map_names_no_such_status(todo_app, digest_app, tmp_path: Path):
    copy = copied(tmp_path)
    edited(copy, "services/digest/foreign.py", "AS_IS = {401: 401, 404: 404}", "AS_IS = {401: 401}")
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", REFUSALS, "--partial", cwd=copy)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"FAIL  {REFUSALS}" in done.stdout
    assert "404" in done.stdout and "names no such status" in done.stdout and "401" in done.stdout


def test_a_claim_that_the_owner_refuses_on_a_step_that_passes_nothing_on_is_refused_where_it_is_taken(
        todo_app, digest_app, tmp_path: Path):
    copy = copied(tmp_path)
    journey = "services/digest/journeys/the_todo_api_turns_a_caller_away.py"
    edited(copy, journey, "yield OwnerRefused(ReadDigest(by=None))", "yield OwnerRefused(ReadTodo(\"nobody-added-this\"))")
    edited(copy, journey, "from ..endpoints import", "from ..endpoints import ReadTodo\nfrom ..endpoints import")
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", REFUSALS, "--partial", cwd=copy)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "the book contradicts itself" in done.stdout
    assert "ReadTodo passes nothing on" in done.stdout


def test_a_write_that_reaches_the_owners_call_passes_and_the_owners_book_then_expects_the_todo_done(
        todo_app, digest_app, tmp_path: Path):
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", FINISHING, "--partial")
    assert f"PASS  {FINISHING}" in done.stdout, done.stdout + done.stderr
    assert list(todo_app.store.todos) == []


def test_with_the_digest_dropping_the_write_the_journey_fails_at_the_write_and_names_the_owners_call(
        todo_app, dropping_digest, tmp_path: Path):
    done = play(todo_app, dropping_digest, tmp_path / "out", "--journey", FINISHING, "--partial")
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"FAIL  {FINISHING}" in done.stdout
    assert "at: POST /digest/" in done.stdout
    assert "DELETE /todos/" in done.stdout
    assert "Fix the gate" in done.stdout


def test_a_write_the_owners_book_expects_refused_fails_and_says_to_claim_the_refusal(todo_app, digest_app, tmp_path: Path):
    copy = copied(tmp_path)
    edited(copy, "services/digest/endpoints.py", "RemoveTodo(step.of)", "RemoveTodo(stranger())")
    edited(copy, "services/digest/endpoints.py", "from .foreign import",
           "from ..api.fixtures import stranger\nfrom .foreign import")
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", FINISHING, "--partial", cwd=copy)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"FAIL  {FINISHING}" in done.stdout
    assert "OwnerRefused" in done.stdout and "expects a refusal" in done.stdout


def test_a_needed_state_that_two_records_of_the_owner_have_is_taken_from_the_named_records_matrix(
        todo_app, digest_app, tmp_path: Path):
    copy = copied(tmp_path)
    edited(copy, "services/api/model/lifecycle.py", "MATRICES = (\n",
           "MATRICES = (\n    Axes[TodoApp](\"decoy\", TODAY, (Scene(\"overdue\", \"a decoy\", lambda today: (AddTodo(todo(CHORE)),)),), "
           "{}, lambda m: \"decoy\", state_of=lambda m, e: \"overdue\", entities=lambda m: [\"decoy\" for _ in m.todos]),\n")
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", "AnOverdueTodoIsInTheDigest", "--partial", cwd=copy)
    assert "PASS  AnOverdueTodoIsInTheDigest" in done.stdout, done.stdout + done.stderr
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_call_that_is_no_endpoint_of_its_book_is_refused(todo_app, digest_app, tmp_path: Path):
    copy = copied(tmp_path)
    stray = (
        "\n\nclass Stray(Endpoint):\n    method = \"GET\"\n    path = \"/strays/{id}\"\n    auth = CREDENTIALS\n    params = BY_ID\n"
        "    answers = (Answer(404, ERROR, \"none\"), NO_CREDENTIAL)\n    carries = None\n"
    )
    todos = copy / "services" / "api" / "endpoints" / "todos.py"
    todos.write_text(todos.read_text() + stray)
    edited(copy, "services/digest/endpoints.py", "from ..api.endpoints import", "from ..api.endpoints.todos import Stray\nfrom ..api.endpoints import")
    edited(copy, "services/digest/endpoints.py", "ReadTodo(step.of)", "Stray(step.of)")
    done = play(todo_app, digest_app, tmp_path / "out", "--journey", "AnOverdueTodoIsInTheDigest", "--partial", cwd=copy)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "Stray is no endpoint of services.api" in done.stdout


def test_walking_a_scene_of_the_digest_book_arranges_the_records_it_needs(todo_app, digest_app, tmp_path: Path):
    copy = copied(tmp_path)
    service = copy / "services" / "digest" / "service.py"
    service.write_text(service.read_text() + (
        "\nimport dataclasses\nfrom datetime import date\nfrom ostler.book import Axes, Needs, Scene\nfrom .foreign import TODO\n"
        "service = dataclasses.replace(service, matrices=(Axes(\"digest\", date(2026, 11, 4), "
        "(Scene(\"late\", \"a late todo\", lambda today: (Needs(TODO, \"overdue\"),)),), {}, lambda m: \"late\"),))\n"))
    done = run_book(["walk", "services.digest", "--scene", "late", "--no-stack", "--out", str(tmp_path / "out")], todo_app.port,
                    cwd=copy, digest=digest_app.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "needs TodoRecord of services.api in overdue" in done.stdout
    assert "FAIL" not in done.stdout
    assert [todo.title for todo in todo_app.store.todos] == ["Fix the gate"]
