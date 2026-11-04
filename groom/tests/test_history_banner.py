from __future__ import annotations

import json
import shlex
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from litestar.testing import TestClient
from test_history import refresh, seed
from test_run_clock import _DB, span, turn

from groom import activity, banner, docker_io, history, state, store
from groom import app as groom_app
from groom.models import WorkflowContainer

ARGV = ["workhorse-coder", "run", "--resume-run", "/srv/runs/billing-export-3", "--cli", "codex", "--config", "/etc/coder.toml"]


def launched(run_dir: Path, argv: list[str] = ARGV, container: bool = False, cwd: str = "") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "launch.json").write_text(json.dumps({"argv": ["workhorse-coder", "run"], "resume_argv": argv, "cwd": cwd, "container": container}))


def broken(run: str, base: float, run_dir: Path, terminal: str = "fail", error: str | None = "WatchdogKilled", message: str | None = "The watchdog killed the turn after 75m with no output", failing: bool = True) -> None:
    pre = f"{run}-"
    root = {"workhorse.terminal": terminal, **({"error.class": error} if error else {})}
    failed = {**span(pre + "x", pre + "t", pre + "n", "qa-story", "agent_turn", base + 400, 30, turn("claude-sonnet-5", 30, None), 1, run), "status": "ERROR"}
    if message:
        failed["attrs"] = {**failed["attrs"], "status_message": message}
    rows = [
        {**span(pre + "r", pre + "t", "", "coder", "run:coder", base, 1000, root, 1, run), "run_dir": str(run_dir)},
        {**span(pre + "s", pre + "t", pre + "r", "work", "work", base + 5, 900, {"workhorse.span_kind": "state", "workhorse.depth": 0}, 1, run), "run_dir": str(run_dir)},
        {**span(pre + "n", pre + "t", pre + "s", "qa-story", "qa-story", base + 10, 800, {"workhorse.depth": 1, "progress": "1/2"}, 1, run), "run_dir": str(run_dir)},
        *([{**failed, "run_dir": str(run_dir)}] if failing else []),
    ]
    store.insert_spans(rows)


def banner_of(run: str, now: float) -> dict | None:
    refresh(now)
    return banner.banner(run)


def test_a_failed_runs_banner_names_the_node_where_it_ended_and_the_error_class(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        launched(tmp_path)
        broken("run-f", now - 3600, tmp_path)
        shown = banner_of("run-f", now)
    assert shown is not None
    assert shown["head"] == "Ended at qa-story: WatchdogKilled"


def test_the_banner_says_in_one_sentence_what_happened_and_how_many_work_items_finished(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        launched(tmp_path)
        broken("run-s", now - 3600, tmp_path)
        shown = banner_of("run-s", now)
    assert shown is not None
    assert shown["text"] == "The watchdog killed the turn after 75m with no output. 1 of 2 work items finished."


def test_a_long_failure_message_ends_the_banner_sentence_at_a_word_with_an_ellipsis_and_no_period(tmp_path: Path) -> None:
    now = time.time()
    words = " ".join(f"word{n}" for n in range(80))
    with _DB():
        launched(tmp_path)
        broken("run-l", now - 3600, tmp_path, message=f"{words}\nsecond line")
        shown = banner_of("run-l", now)
    assert shown is not None
    sentence = shown["text"].removesuffix(" 1 of 2 work items finished.")
    assert sentence.endswith("…")
    assert not sentence.endswith(".")
    assert sentence.removesuffix("…").split()[-1] in words.split()
    assert "second line" not in shown["text"]


def test_a_failure_message_under_the_limit_reaches_the_banner_whole_past_the_activity_cut(tmp_path: Path) -> None:
    now = time.time()
    words = " ".join(f"w{n}" for n in range(60))
    with _DB():
        launched(tmp_path)
        broken("run-w", now - 3600, tmp_path, message=words)
        shown = banner_of("run-w", now)
    assert shown is not None
    assert shown["text"].startswith(words[:1].upper() + words[1:] + ".")


@pytest.mark.parametrize(
    ("terminal", "head", "text"),
    [
        ("interrupted", "Ended at qa-story: interrupted by AgentTurnFailed", "The backend failed the turn, and the run paused. 1 of 2 work items finished."),
        ("aborted", "Ended at qa-story: crashed", "The run stopped on an unhandled error before it could finish. 1 of 2 work items finished."),
    ],
)
def test_an_interrupted_or_crashed_run_has_the_same_banner_naming_what_stopped_it(tmp_path: Path, terminal: str, head: str, text: str) -> None:
    now = time.time()
    with _DB():
        launched(tmp_path)
        broken("run-i", now - 3600, tmp_path, terminal, "AgentTurnFailed", "The backend failed the turn")
        shown = banner_of("run-i", now)
    assert shown is not None
    assert (shown["head"], shown["text"]) == (head, text)
    assert shown["command"]


def test_a_run_that_gave_up_has_a_banner_saying_it_skipped_the_work_item_and_shows_no_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOM_GIVEUP_NODES", "qa_give_up")
    now = time.time()
    with _DB():
        seed("run-g", now - 3600, "terminal", node="qa_give_up")
        shown = banner_of("run-g", now)
    assert shown is not None
    assert shown["head"] == "Ended at qa_give_up: gave up"
    assert "after exhausting its retries" in shown["text"]
    assert (shown["command"], shown["gone"]) == ("", False)


def test_a_successful_run_and_a_run_with_no_recorded_ending_have_no_banner() -> None:
    now = time.time()
    with _DB():
        seed("run-ok", now - 3600, "terminal")
        seed("run-open", now - 5 * 86400, None)
        refresh(now)
        silent = history.stored("run-open")
        assert silent is not None and silent["ending"] == "none"
        assert (banner.banner("run-ok"), banner.banner("run-open")) == (None, None)


def test_the_link_names_the_failing_turns_row_in_the_activity_timeline(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        launched(tmp_path)
        broken("run-l", now - 3600, tmp_path)
        shown = banner_of("run-l", now)
        slugs = [row["slug"] for row in activity.timeline("run-l")["rows"]]
    assert shown is not None
    assert shown["moment"] in slugs


def test_a_run_with_no_failing_row_in_its_timeline_has_the_banner_with_no_link(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        launched(tmp_path)
        broken("run-n", now - 3600, tmp_path, failing=False)
        shown = banner_of("run-n", now)
    assert shown is not None
    assert shown["moment"] == ""
    assert shown["head"] == "Ended: WatchdogKilled"


def test_the_command_is_the_resume_argv_the_run_recorded_at_launch_flags_included(tmp_path: Path) -> None:
    now = time.time()
    argv = ["/opt/bin/coder", "run", "--resume-run", str(tmp_path), "--cli", "codex", "--config", "/etc/my coder.toml"]
    with _DB():
        launched(tmp_path, argv, cwd="/srv/work")
        broken("run-c", now - 3600, tmp_path)
        shown = banner_of("run-c", now)
    assert shown is not None
    assert shown["command"] == f"cd /srv/work && {shlex.join(argv)}"
    assert shown["container"] is False


def test_a_recorded_directory_with_a_space_survives_a_paste_into_a_shell(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        launched(tmp_path, ["/opt/bin/coder", "run"], cwd="/srv/my work")
        broken("run-q", now - 3600, tmp_path)
        shown = banner_of("run-q", now)
    assert shown is not None
    assert shlex.split(shown["command"]) == ["cd", "/srv/my work", "&&", "/opt/bin/coder", "run"]


def test_a_launch_record_with_an_empty_cwd_shows_the_argv_alone(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        launched(tmp_path, ["/opt/bin/coder", "run"], cwd="")
        broken("run-e", now - 3600, tmp_path)
        shown = banner_of("run-e", now)
    assert shown is not None
    assert shown["command"] == "/opt/bin/coder run"


def test_a_summary_stored_before_the_cwd_was_read_is_summarized_again_once(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        launched(tmp_path, ["/opt/bin/coder", "run"], cwd="/srv/work")
        broken("run-o", now - 3600, tmp_path)
        refresh(now)
        with history.STORE.writing() as conn:
            conn.execute("UPDATE run_summary SET resume_command = ?, resume_read = 1 WHERE run_id = ?", ("/opt/bin/coder run", "run-o"))
        shown = banner_of("run-o", now)
    assert shown is not None
    assert shown["command"] == "cd /srv/work && /opt/bin/coder run"


def test_a_container_runs_banner_carries_the_command_and_says_it_runs_inside_the_container() -> None:
    now = time.time()
    record = json.dumps({"resume_argv": ["workhorse-coder", "run", "--resume-run", "/runs/billing-export-3"], "cwd": "/work/repo", "container": True})
    reader = patch.object(docker_io, "read_file", return_value=record)
    mounted = patch.dict(state.WORKFLOWS, {"c1": WorkflowContainer(container_id="c1", name="coder", run_id="run-k", runs_volume="runs-vol")})
    with _DB(), mounted, reader as read:
        broken("run-k", now - 3600, Path("/runs/billing-export-3"))
        shown = banner_of("run-k", now)
    assert shown is not None
    assert shown["container"] is True
    assert shown["command"] == "cd /work/repo && workhorse-coder run --resume-run /runs/billing-export-3"
    read.assert_called_with("runs-vol", "billing-export-3/launch.json")


def test_a_run_whose_folder_is_gone_says_it_cannot_be_continued_and_shows_no_command(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        broken("run-d", now - 3600, tmp_path / "gone")
        shown = banner_of("run-d", now)
    assert shown is not None
    assert (shown["command"], shown["gone"], shown["unrecorded"]) == ("", True, False)


def test_a_run_whose_folder_stays_but_recorded_no_launch_says_so_and_composes_no_command(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        broken("run-u", now - 3600, tmp_path)
        shown = banner_of("run-u", now)
    assert shown is not None
    assert (shown["command"], shown["gone"], shown["unrecorded"]) == ("", False, True)


def test_the_overview_route_carries_the_ending_banner_of_a_stopped_run_and_none_for_a_finished_one(tmp_path: Path) -> None:
    now = time.time()
    with _DB():
        launched(tmp_path)
        broken("run-r", now - 3600, tmp_path)
        seed("run-r2", now - 3600, "terminal")
        refresh(now)
        with TestClient(app=groom_app.create_app()) as client:
            stopped = client.get("/api/run/run-r/overview").json()
            fine = client.get("/api/run/run-r2/overview").json()
    assert stopped["ending"]["head"] == "Ended at qa-story: WatchdogKilled"
    assert fine["ending"] is None
