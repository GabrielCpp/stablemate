"""`workhorse-<name> inbox` — read and answer the messages left for a run.

Unlike `control`, this command is file-based: there is no process to talk to, so the
tests write directly to a run dir's `inbox.jsonl` and assert on what `read`/`reply`
print and persist. The one behavior shared with `control` — resolving `--run` by id,
dir name or path, and defaulting to the newest unfinished run — is exercised again here
because the two commands must not drift on it independently.

Run: uv run python tests/test_inbox_command.py   (or via pytest)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from _fakes import fake_groom  # noqa: E402
from workhorse import inbox  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.cli import main as cli_main  # noqa: E402
from workhorse.cli.inbox import INBOX_FILE  # noqa: E402
from workhorse.pyflow.registry import Registry  # noqa: E402
from workhorse.records import PyflowCheckpoint, RunRecord  # noqa: E402


def _run_dir(runs: Path, name: str = "demo-t", *, terminal: str | None = None) -> Path:
    run_dir = runs / name
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        RunRecord(
            workflow="demo",
            run_id=name.removeprefix("demo-"),
            started_at="2026-01-01T00:00:00+00:00",
            terminal=terminal,
        ).model_dump_json()
    )
    (run_dir / ArtifactWriter.CHECKPOINT_FILE).write_text(
        PyflowCheckpoint(state="plan_story", flow="Qa", workflow="demo").model_dump_json()
    )
    return run_dir


def _inbox(*argv: str) -> None:
    cli_main(["inbox", *argv], workflow="demo", registry=Registry("demo"))


def test_an_id_groom_knows_is_read_from_the_run_dir_groom_names(capsys, monkeypatch) -> None:
    """`inbox` resolves a run the way `control` does — including through groom when
    the id is not under the cwd's runs dir — or the two commands drift on which run
    an operator's id means."""
    with tempfile.TemporaryDirectory() as tmp:
        elsewhere = Path(tmp) / "target-repo" / ".agents" / "runs"
        run_dir = _run_dir(elsewhere, "demo-ghost")
        inbox.append(run_dir / INBOX_FILE, id="m1", body="hold off", at="t0")
        empty = Path(tmp) / "runs"
        empty.mkdir()
        rows = [{"run_id": "ghost", "workflow": "demo", "run_dir": str(run_dir)}]

        with fake_groom(rows) as (url, asked):
            monkeypatch.setenv("GROOM_URL", url)
            _inbox("read", "--run", "ghost", "--runs-dir", str(empty))

        captured = capsys.readouterr()
        assert asked == ["/api/live?run=ghost"]
        assert "m1" in captured.out and "hold off" in captured.out
        assert f"resolved 'ghost' via groom: {run_dir}" in captured.err


def test_read_prints_outstanding_messages_by_default(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        inbox.append(run_dir / INBOX_FILE, id="m1", body="hold off on the migration", at="t0")
        inbox.append(run_dir / INBOX_FILE, id="m2", body="go ahead", at="t1")
        inbox.reply(run_dir / INBOX_FILE, "m2", "done", at="t2")

        _inbox("read", "--run", "t", "--runs-dir", str(runs))

        out = capsys.readouterr().out
        assert "m1" in out and "hold off on the migration" in out
        assert "m2" not in out


def test_read_all_includes_replied_messages(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        inbox.append(run_dir / INBOX_FILE, id="m1", body="go ahead", at="t0")
        inbox.reply(run_dir / INBOX_FILE, "m1", "done", at="t1")

        _inbox("read", "--all", "--run", "t", "--runs-dir", str(runs))

        out = capsys.readouterr().out
        assert "m1" in out and "done" in out


def test_read_with_no_messages_says_so_rather_than_printing_nothing(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs)

        _inbox("read", "--run", "t", "--runs-dir", str(runs))

        assert "no outstanding messages" in capsys.readouterr().out


def test_reply_persists_and_is_read_back_as_answered(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        inbox.append(run_dir / INBOX_FILE, id="m1", body="go ahead", at="t0")

        _inbox("reply", "m1", "confirmed", "--run", "t", "--runs-dir", str(runs))

        assert "replied to [m1]" in capsys.readouterr().out
        stored = inbox.all_messages(run_dir / INBOX_FILE)[0]
        assert stored.reply == "confirmed"
        assert stored.replied_at


def test_reply_to_a_missing_id_is_an_error(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        inbox.append(run_dir / INBOX_FILE, id="m1", body="go ahead", at="t0")

        with pytest.raises(SystemExit) as excinfo:
            _inbox("reply", "no-such-id", "confirmed", "--run", "t", "--runs-dir", str(runs))

        assert excinfo.value.code == 1
        assert "no inbox message" in capsys.readouterr().err


def test_reply_with_no_text_is_an_error(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs)

        with pytest.raises(SystemExit) as excinfo:
            _inbox("reply", "m1", "--run", "t", "--runs-dir", str(runs))

        assert excinfo.value.code == 1
        assert "needs an id and text" in capsys.readouterr().err


def test_a_run_is_found_by_its_id_its_dir_name_or_its_path(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        run_dir = _run_dir(runs)
        inbox.append(run_dir / INBOX_FILE, id="m1", body="go ahead", at="t0")

        for spec in ("t", "demo-t", str(run_dir)):
            _inbox("read", "--run", spec, "--runs-dir", str(runs))

        out = capsys.readouterr().out
        assert out.count("m1") == 3, out


def test_with_no_run_named_the_newest_unfinished_run_is_taken(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs, "demo-done", terminal="terminal")
        live = _run_dir(runs, "demo-live")
        inbox.append(live / INBOX_FILE, id="m1", body="go ahead", at="t0")

        _inbox("read", "--runs-dir", str(runs))

        assert "m1" in capsys.readouterr().out


def test_a_run_that_does_not_exist_is_an_error_not_a_new_directory(capsys) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        _run_dir(runs)

        with pytest.raises(SystemExit) as excinfo:
            _inbox("read", "--run", "typo", "--runs-dir", str(runs))

        assert excinfo.value.code == 1
        assert "no run dir for 'typo'" in capsys.readouterr().err
        assert not (runs / "demo-typo").exists()


if __name__ == "__main__":
    print("run with pytest: uv run python -m pytest tests/test_inbox_command.py")
