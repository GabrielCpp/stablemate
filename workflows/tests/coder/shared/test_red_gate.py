"""Unit tests for the deterministic red gate's two judgements: purity, and the red.

Every test drives `run_red_gate` against a real git repo with a real suite command, because
both halves of the gate are made of things a fake would have to re-implement — `git status
--porcelain -uall` and the exit code and stdout of a process. What is faked is only the
suite itself, a shell script that prints the output a stack would print and exits how the
test wants.

Three behaviours are regression tests for gates observed misfiring on live runs, and each
names what it saw:

* the agent CLI's own session file, tracked in the target repo and rewritten every turn, was
  charged to the tests turn as an impure change — on every lap of every packet, so the gate
  could never pass on that backend;
* purity rejected anything that was not a test file, which made a fixture or a note as fatal
  as an implementation and spent a rework lap on it;
* a pre-existing failure elsewhere in the suite supplied the non-zero exit, so the gate
  reported a red the new tests had not caused and the code turn was told it had a contract
  it did not have.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest
from workhorse_workflows.coder.shared.red_gate import run_red_gate

LOGGER = logging.getLogger("test.red_gate")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A committed git repo with one production file and one test file already in it."""
    repo = tmp_path / "svc"
    (repo / "tests").mkdir(parents=True)
    (repo / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "tests" / "test_app.py").write_text("def test_add():\n    assert True\n", encoding="utf-8")
    _git(repo.parent, "init", "svc")
    _git(repo, "config", "user.email", "gate@example.com")
    _git(repo, "config", "user.name", "Gate")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    return repo


def _suite(repo: Path, output: str, code: int) -> str:
    """A fake suite command printing `output` and exiting `code`, as a shell one-liner."""
    script = repo / "fake-suite.sh"
    script.write_text(f"cat <<'OUT'\n{output}\nOUT\nexit {code}\n", encoding="utf-8")
    script.chmod(0o755)
    return "sh ./fake-suite.sh"


def _gate(repo: Path, command: str = "", baseline: list[str] | None = None):
    return run_red_gate(
        LOGGER,
        cwd=str(repo),
        service="svc",
        baseline=baseline if baseline is not None else [],
        test_command=command,
    )


# --- purity -----------------------------------------------------------------------------


def test_the_harness_own_session_file_is_not_the_tests_turn_diff(repo: Path) -> None:
    """A tracked `.opencode/` session file rewritten every turn is invisible to the gate.

    The failure this replaces: opencode writes `ses_*.json` under `.opencode/opencode-loop/`
    and that path was already tracked in the target repo, so `git status` reported it, the
    gate charged it to the agent, and three laps in a row came back `impure` for a file the
    agent never chose to write.
    """
    loop = repo / ".opencode" / "opencode-loop"
    loop.mkdir(parents=True)
    (loop / "ses_ff43550eaffec.json").write_text('{"turns": 1}\n', encoding="utf-8")
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n", encoding="utf-8")

    outcome = _gate(repo)

    assert outcome.status == "skipped", outcome.reason
    assert outcome.non_test_files == []
    assert outcome.changed_files == ["tests/test_new.py"]


def test_non_code_files_are_pure(repo: Path) -> None:
    """Fixtures, data and docs are a tests turn's business; only code is the code turn's."""
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n", encoding="utf-8")
    (repo / "fixtures.json").write_text('{"seed": []}\n', encoding="utf-8")
    (repo / "NOTES.md").write_text("why these scenarios\n", encoding="utf-8")

    outcome = _gate(repo)

    assert outcome.status == "skipped", outcome.reason
    assert outcome.non_test_files == []
    assert sorted(outcome.changed_files) == ["NOTES.md", "fixtures.json", "tests/test_new.py"]


@pytest.mark.parametrize("path", ["feature.py", "web/print.css", "db/0001_add.sql", "main.tf"])
def test_production_code_is_impure(repo: Path, path: str) -> None:
    """Source, styles, SQL and terraform are all implementation the code turn owes."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n", encoding="utf-8")
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n", encoding="utf-8")

    outcome = _gate(repo)

    assert outcome.status == "impure"
    assert outcome.non_test_files == [path]
    assert path in outcome.reason


def test_a_pre_existing_change_is_not_charged_to_the_tests_turn(repo: Path) -> None:
    """The baseline is what makes the gate judge the turn rather than the worktree."""
    (repo / "feature.py").write_text("already dirty\n", encoding="utf-8")
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n", encoding="utf-8")

    outcome = _gate(repo, baseline=["feature.py"])

    assert outcome.status == "skipped", outcome.reason


def test_a_turn_that_wrote_only_prose_has_no_tests(repo: Path) -> None:
    """Non-code purity must not let an empty turn through: `no_tests` counts test files."""
    (repo / "NOTES.md").write_text("I thought about it\n", encoding="utf-8")

    outcome = _gate(repo, command=_suite(repo, "irrelevant", 1))

    assert outcome.status == "no_tests"
    assert "no test files" in outcome.reason


# --- the red ----------------------------------------------------------------------------


def test_a_failure_naming_the_new_test_is_the_red(repo: Path) -> None:
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n", encoding="utf-8")
    output = "FAILED tests/test_new.py::test_new - AssertionError\n1 failed, 11 passed"

    outcome = _gate(repo, command=_suite(repo, output, 1))

    assert outcome.status == "red", outcome.reason
    assert outcome.failing_files == ["tests/test_new.py"]


def test_someone_elses_red_does_not_satisfy_the_gate(repo: Path) -> None:
    """The failure this replaces: a broken test in another package supplied the exit code.

    The suite *did* report on the new tests here — they were collected and passed — so the
    red is somebody else's and the turn owes a rework: its scenarios exercise nothing
    missing. That the run also failed elsewhere does not certify them.
    """
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n", encoding="utf-8")
    output = (
        "tests/test_new.py .                                                      [ 50%]\n"
        "FAILED tests/test_console_script.py::test_every_flag - AssertionError\n1 failed"
    )

    outcome = _gate(repo, command=_suite(repo, output, 2))

    assert outcome.status == "unattributed_red"
    assert outcome.failing_files == []
    assert "tests/test_new.py" in outcome.reason


def test_a_suite_that_never_reached_the_new_tests_stands_aside(repo: Path) -> None:
    """The live incident: `make test` walks the subprojects and halts at the first failure.

    `test_console_script.py` fails only under the run's own worktree layout, in a package
    several steps before the packet's, so the new tests are never collected — the output
    does not mention them at all. There is no verdict to give, and no rework the tests turn
    could perform would change that, so the gate stands aside instead of charging one.
    """
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n", encoding="utf-8")
    output = "FAILED tests/test_console_script.py::test_every_flag - AssertionError\n1 failed"

    outcome = _gate(repo, command=_suite(repo, output, 2))

    assert outcome.status == "unreached", outcome.reason
    assert outcome.failing_files == []
    assert "tests/test_new.py" in outcome.reason


def test_output_the_gate_cannot_read_still_proceeds(repo: Path) -> None:
    """Fail-open: an unrecognised failure format is silence, and silence is not evidence."""
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n", encoding="utf-8")

    outcome = _gate(repo, command=_suite(repo, "something went wrong, somewhere", 1))

    assert outcome.status == "red", outcome.reason
    assert outcome.failing_files == []


def test_a_green_suite_is_rejected(repo: Path) -> None:
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert True\n", encoding="utf-8")

    outcome = _gate(repo, command=_suite(repo, "12 passed", 0))

    assert outcome.status == "all_green"


def test_the_red_run_is_logged_where_the_code_turn_can_read_it(repo: Path, tmp_path: Path) -> None:
    (repo / "tests" / "test_new.py").write_text("def test_new():\n    assert False\n", encoding="utf-8")
    spec = tmp_path / "spec"

    outcome = run_red_gate(
        LOGGER,
        cwd=str(repo),
        service="svc",
        spec_dir=str(spec),
        baseline=[],
        test_command=_suite(repo, "FAILED tests/test_new.py::test_new", 1),
    )

    assert outcome.status == "red", outcome.reason
    assert Path(outcome.log_path) == spec / "red-gate-svc.log"
    assert "test_new" in Path(outcome.log_path).read_text(encoding="utf-8")
