"""What a recorded step owes the reader, independent of who authored it.

A scenario is Python now, but `ostler qa step` still runs a command in a shell and records
what it produced, and every failure below was a case of the ledger and the filesystem
disagreeing about that. They are exercised through the session API directly because that is
the layer that owns the answer; none of them is about how the step came to be declared.
"""

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
    """A step that cannot tell a broken command from a true negative is not an oracle.

    A pipeline's exit status is its last stage, so `cat <missing-file> | wc -l` exits 0 and
    prints `0` whether the file was empty or never existed — and a check reading `0` off
    that step passes having observed nothing. `set -o pipefail` is what lets the non-zero
    exit path see the upstream failure.
    """
    spec = _spec(tmp_path)
    cmd_start("qa-run-1", "story-1", spec)

    outcome = cmd_step(spec, "count", "count the rows", "live", "cat ./absent.json | wc -l")

    assert not outcome.ok
    assert "exited" in outcome.message, outcome.message


def test_a_step_that_writes_into_qa_steps_itself_finds_the_directory_there(
    tmp_path: Path,
) -> None:
    """`qa/steps/` is a layout ostler publishes, so ostler has to be the one that creates it.

    Nothing needed it early for ostler's own sake: the `out_path` sidecar mkdirs its parent
    after the subprocess returns, and `qa/asserts/` is made just before the first assertion.
    But a step that redirects into `$QA_DIR/steps/` runs before any sidecar has been
    written, and so before anything has made the directory. A `curl -o` there cannot create
    it, exits 23, and the value that step was to produce comes back empty — after which the
    request reading it goes somewhere unrelated and gets a plausible wrong answer: a 404
    that reads as a product defect rather than as a missing directory.

    It bites only the first run against a fresh spec dir, which is exactly the run least
    likely to be doubted.
    """
    spec = _spec(tmp_path)
    fixture = spec / "qa/steps/create-fixture.json"
    assert not fixture.parent.exists()  # fresh spec dir: the first run is the one that breaks

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
    """`out_path` is a capture of stdout, and an empty capture is not a reason to delete
    evidence.

    A step that redirects its own stdout — `curl -w '%{http_code}' … > qa/steps/x.txt` — and
    also declares that file as its `out_path` leaves nothing on the pipe for ostler to
    capture. The sidecar write then landed 0 bytes on top of the bytes curl had just
    written, and the check reading that file compared a status code against an empty string.
    It failed, and it failed *as a product defect*: a run reported three acceptance criteria
    broken while its own per-step ledger recorded the correct 404/201/302 for every request.

    Naming both is redundant, and a validator could say so — but the harm is that ostler
    destroys output it did not produce, so the guard belongs at the write.
    """
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
    # The ledger says why the sidecar holds bytes ostler did not capture.
    assert probe["stdout_file_written_by_cmd"] is True
    assert probe["stdout_file"] == str(status)


def test_an_out_sidecar_does_not_adopt_a_file_from_an_earlier_run(tmp_path: Path) -> None:
    """The other half of that guard: adoption is only ever of *this* session's output.

    `qa/` is wiped once per QA lane — before the plan is even written — not at session
    start, so a file a dry run left behind is still sitting there when the scored run opens.
    Adopting it would let a step that produced nothing inherit the output of a rehearsal
    that was tuned until it passed, and report it to the evidence gate as proof.
    """
    spec = _spec(tmp_path)
    stale = spec / "qa/steps/status.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("404", encoding="utf-8")
    # Older than any session that could open after it.
    os.utime(stale, (0, 0))
    cmd_start("qa-run-1", "story-1", spec)

    # Writes nothing at all — the whole point is that the leftover must not stand in for it.
    outcome = cmd_step(spec, "probe", "probe", "live", "true", out_path="qa/steps/status.txt")

    assert outcome.ok, outcome.message
    probe = next(row for row in _records(spec) if row.get("id") == "probe")
    assert not probe.get("stdout_file_written_by_cmd"), "adopted a file from before the session"
    assert stale.read_text(encoding="utf-8") == "", "stale bytes were left standing as evidence"


def test_qa_dir_is_exported_to_commands_and_follows_the_ledger_directory(
    tmp_path: Path,
) -> None:
    """`$QA_DIR` is the only spelling of the ledger directory that survives a dry run.

    A step that redirects its own output has to name the directory somehow, and every
    literal spelling — `<spec>/qa/steps/…`, or an interpolated `qa_dir` — names the *scored*
    ledger whichever directory the run was pointed at. So a dry run writes into the evidence
    the scored run is later judged on. Observed live: ten dry runs of a six-scenario plan
    left ~30 artifacts in `qa/steps/` and produced an empty scratch directory.
    """
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
    """The redirect that hid the file's contents hid the status code with it.

    A step's HTTP status comes from the trailing `%{http_code}` curl appends to stdout. Send
    that stdout to a file and the pipe is empty, so the status parsed as None and every
    check on it failed — while the header dumps beside it showed the server had answered
    correctly all along. Keeping the file is not enough on its own: four `assert_contains`
    oracles re-reading those files went green while four status checks on the same steps
    stayed red, which is a worse state to leave a run in than uniformly failing. If the file
    is the step's stdout, everything derived from stdout has to come from it.
    """
    spec = _spec(tmp_path)
    body = spec / "qa/steps/response.txt"
    cmd_start("qa-run-1", "story-1", spec)

    outcome = cmd_step(
        spec,
        "request",
        "issue the request",
        "live",
        # What `curl -s -w '\n%{http_code}' … > file` leaves behind: body, then the code.
        "printf 'served\\n302' > \"$QA_DIR/steps/response.txt\"",
        out_path="qa/steps/response.txt",
    )

    assert outcome.ok, outcome.message
    # The file is untouched — the status was parsed out of it, not written back over it.
    assert body.read_text(encoding="utf-8") == "served\n302"
    assert outcome.data["http_status"] == 302
    assert outcome.data["stdout_file_written_by_cmd"] is True


def test_the_status_line_of_a_curl_header_dump_is_read_as_the_status(tmp_path: Path) -> None:
    """`-D` is the other way a step hands ostler a status, and it was the unreadable one.

    `curl -o body -D headers` sends the body one way and the response head another, leaving
    stdout empty — so there is no trailing `%{http_code}` to find, and the status compared
    None to 201 while the step's own sibling check read the same number off the same file
    with `head -1 | awk '{print $2}'`. Reporting an acceptance criterion broken over a status
    code sitting in a file ostler already captured is the worst answer available: it reads
    as a product defect and sends the loop off repairing working code.

    The redirect chain here is why the *last* status line wins rather than the first — with
    `-L` curl dumps every hop, and the claim is about the response that came back, not the
    302 that pointed at it.
    """
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
        # What `curl -s -o body.json -D headers.txt -L …` leaves in the dump.
        f"printf '{dump}' > \"$QA_DIR/steps/create-headers.txt\"",
        out_path="qa/steps/create-headers.txt",
    )

    assert outcome.ok, outcome.message
    # The head is evidence in its own right — nothing is stripped out of it.
    assert "Location: /final" in headers.read_text(encoding="utf-8")
    assert outcome.data["http_status"] == 201


def test_a_trailing_write_out_code_still_beats_a_body_that_looks_like_headers(
    tmp_path: Path,
) -> None:
    """The header-dump read is a fallback, and it has to stay one.

    A body can legitimately begin with `HTTP/` — a proxy log, a captured transcript, a
    fixture describing a response. If the dump scan ran first it would quietly win over the
    code curl was actually asked to write out, and the step would report a number from the
    payload instead of from the request. Ordering is the whole guarantee, so it gets a test.
    """
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
    """One path language: a `captures:` path selects with `[*]` and `[?(@.k==v)]` exactly as a
    `json_path` check does, a single selection is captured as the value, and a missing path is
    `None` rather than an empty string."""
    data = {"items": [{"id": "a", "n": 1}, {"id": "b", "n": 2}], "meta": {"total": 0}}
    assert _extract_path(data, "$.meta.total") == "0"
    assert _extract_path(data, "$.items[?(@.n==2)].id") == "b"
    assert _extract_path(data, "$.items[1].id") == "b"
    assert _extract_path(data, "$.items[*].id") == "['a', 'b']"
    assert _extract_path(data, "$.items[?(@.n==9)].id") is None
    assert _extract_path(data, "$.meta.missing") is None
    assert _extract_path(None, "$.x") is None
