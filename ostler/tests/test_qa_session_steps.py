"""What a recorded step owes the reader, independent of who authored it."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ostler.qa.run import cmd_start, cmd_step
from ostler.qa.session import QaSession, _extract_path, scratch_dirname


def _spec(tmp_path: Path) -> Path:
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    return spec


def _records(spec: Path, qa_dirname: str = "qa") -> list[dict]:
    log = spec / qa_dirname / "qa-run.ndjson"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_a_failing_upstream_pipeline_stage_fails_the_step(tmp_path: Path) -> None:
    """A step that cannot tell a broken command from a true negative is not an oracle."""
    spec = _spec(tmp_path)
    cmd_start("qa-run-1", "story-1", spec)

    outcome = cmd_step(spec, "count", "count the rows", "live", "cat ./absent.json | wc -l")

    assert not outcome.ok
    assert "exited" in outcome.message, outcome.message


def test_a_step_that_writes_into_qa_steps_itself_finds_the_directory_there(
    tmp_path: Path,
) -> None:
    """`qa/steps/` is a layout ostler publishes, so ostler has to be the one that creates it."""
    spec = _spec(tmp_path)
    fixture = spec / "qa/steps/create-fixture.json"
    assert not fixture.parent.exists()

    cmd_start("qa-run-1", "story-1", spec)
    outcome = cmd_step(
        spec,
        "create-fixture",
        "seed the fixture",
        "live",
        'printf \'{"code":"abc"}\' > "$QA_DIR/steps/create-fixture.json"',
    )

    assert outcome.ok, outcome.message
    assert json.loads(fixture.read_text(encoding="utf-8")) == {"code": "abc"}


def test_an_out_sidecar_never_blanks_a_file_the_command_wrote_itself(tmp_path: Path) -> None:
    """`out_path` is a capture of stdout, and an empty capture is not a reason to delete evidence."""
    spec = _spec(tmp_path)
    status = spec / "qa/steps/status.txt"
    cmd_start("qa-run-1", "story-1", spec)

    outcome = cmd_step(
        spec,
        "probe",
        "probe the endpoint",
        "live",
        'printf \'404\' > "$QA_DIR/steps/status.txt"',
        out_path="qa/steps/status.txt",
    )

    assert outcome.ok, outcome.message
    assert status.read_text(encoding="utf-8") == "404"
    probe = next(row for row in _records(spec) if row.get("id") == "probe")
    assert probe["stdout_file_written_by_cmd"] is True
    assert probe["stdout_file"] == str(status)


def test_an_out_sidecar_does_not_adopt_a_file_from_an_earlier_run(tmp_path: Path) -> None:
    """The other half of that guard: adoption is only ever of *this* session's output."""
    spec = _spec(tmp_path)
    stale = spec / "qa/steps/status.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("404", encoding="utf-8")
    os.utime(stale, (0, 0))
    cmd_start("qa-run-1", "story-1", spec)

    outcome = cmd_step(spec, "probe", "probe", "live", "true", out_path="qa/steps/status.txt")

    assert outcome.ok, outcome.message
    probe = next(row for row in _records(spec) if row.get("id") == "probe")
    assert not probe.get("stdout_file_written_by_cmd"), "adopted a file from before the session"
    assert stale.read_text(encoding="utf-8") == "", "stale bytes were left standing as evidence"


def test_qa_dir_is_exported_to_commands_and_follows_the_ledger_directory(
    tmp_path: Path,
) -> None:
    """`$QA_DIR` is the only spelling of the ledger directory that survives a dry run."""
    spec = _spec(tmp_path)
    session = QaSession.create(
        spec, "qa-run-1", "story-1", {}, qa_dirname=scratch_dirname("dry")
    )
    session.write_session_start()

    record = session.run_step(
        "probe",
        "probe",
        "live",
        'printf \'ok\' > "$QA_DIR/steps/body.txt" && printf "at=%s" "$QA_DIR"',
        cwd=spec,
    )

    assert record["exit_code"] == 0
    assert (spec / "qa/dry/steps/body.txt").read_text(encoding="utf-8") == "ok"
    assert not (spec / "qa/steps").exists(), "a dry run reached the scored ledger"


def test_a_status_the_command_redirected_into_its_own_out_file_is_still_read(
    tmp_path: Path,
) -> None:
    """The redirect that hid the file's contents hid the status code with it."""
    spec = _spec(tmp_path)
    body = spec / "qa/steps/response.txt"
    cmd_start("qa-run-1", "story-1", spec)

    outcome = cmd_step(
        spec,
        "request",
        "issue the request",
        "live",
        "printf 'served\\n302' > \"$QA_DIR/steps/response.txt\"",
        out_path="qa/steps/response.txt",
    )

    assert outcome.ok, outcome.message
    assert body.read_text(encoding="utf-8") == "served\n302"
    assert outcome.data["http_status"] == 302
    assert outcome.data["stdout_file_written_by_cmd"] is True


def test_the_status_line_of_a_curl_header_dump_is_read_as_the_status(tmp_path: Path) -> None:
    """`-D` is the other way a step hands ostler a status, and it was the unreadable one."""
    spec = _spec(tmp_path)
    headers = spec / "qa/steps/create-headers.txt"
    dump = (
        "HTTP/1.1 302 Found\\r\\nLocation: /final\\r\\n\\r\\n"
        "HTTP/1.1 201 Created\\r\\nContent-Type: application/json\\r\\n\\r\\n"
    )
    cmd_start("qa-run-1", "story-1", spec)

    outcome = cmd_step(
        spec,
        "create",
        "create the record",
        "live",
        f"printf '{dump}' > \"$QA_DIR/steps/create-headers.txt\"",
        out_path="qa/steps/create-headers.txt",
    )

    assert outcome.ok, outcome.message
    assert "Location: /final" in headers.read_text(encoding="utf-8")
    assert outcome.data["http_status"] == 201


def test_a_trailing_write_out_code_still_beats_a_body_that_looks_like_headers(
    tmp_path: Path,
) -> None:
    """The header-dump read is a fallback, and it has to stay one."""
    spec = _spec(tmp_path)
    cmd_start("qa-run-1", "story-1", spec)

    outcome = cmd_step(
        spec,
        "transcript",
        "replay the transcript",
        "live",
        "printf 'HTTP/1.1 500 Internal Server Error\\nrecorded upstream\\n200'",
    )

    assert outcome.ok, outcome.message
    assert outcome.data["http_status"] == 200


def test_a_capture_path_speaks_the_harness_grammar() -> None:
    """One path language: a `captures:` path selects with `[*]` and `[?(@.k==v)]` exactly as a `json_path` check does, a single selection is captured as the value, and a missing path is `None` rather than an empty string."""
    data = {"items": [{"id": "a", "n": 1}, {"id": "b", "n": 2}], "meta": {"total": 0}}
    assert _extract_path(data, "$.meta.total") == "0"
    assert _extract_path(data, "$.items[?(@.n==2)].id") == "b"
    assert _extract_path(data, "$.items[1].id") == "b"
    assert _extract_path(data, "$.items[*].id") == "['a', 'b']"
    assert _extract_path(data, "$.items[?(@.n==9)].id") is None
    assert _extract_path(data, "$.meta.missing") is None
    assert _extract_path(None, "$.x") is None
