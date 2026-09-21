"""What a whole QA run owns: the ledger, the manifest, the evidence and the stack under it."""

from __future__ import annotations

import pytest
import hashlib
import json
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ostler.artifact.kinds import _qa_evidence_vet
from ostler.qa.context import book_files
from ostler.qa.plan import RETIRED_YAML, _validate_background, load_plan, validate_v2
from ostler.qa.evidence_map import build_evidence_map
from ostler.qa.run import cmd_run, cmd_validate
from ostler.qa import session
from ostler.qa.session import _kill_pid

OBLIGATION = "okf:docs/features/demo/item.md:contract"


@pytest.fixture(autouse=True)
def _fast_daemon_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep lifecycle wiring real without spending production grace periods per case."""
    monkeypatch.setattr(
        session,
        "_DAEMON_TIMING",
        session._DaemonTiming(  # noqa: SLF001 - this is the injected test clock
            poll_s=0.01,
            settle_s=0.05,
            interrupt_grace_s=0.05,
            terminate_grace_s=0.05,
        ),
    )

PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-run-1", story="story-1")

api = target("api")


@scenario(target=api, mechanism="live", covers=["{obligation}"])
def api_contract(qa: Qa) -> None:
    """The item is emitted."""
    qa.check("the value is ok", True, actual="ok", expected="ok", covers=["{obligation}"])
'''


def _spec(tmp_path: Path) -> Path:
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "qa-okf-context.json").write_text(
        json.dumps(
            {
                "version": 1,
                "available": True,
                "contracts": [],
                "acceptanceCriteria": [],
                "healthFindings": [],
                "obligations": [
                    {
                        "id": OBLIGATION,
                        "kind": "contract",
                        "node": "item",
                        "source": "docs/features/demo/item.md",
                        "requirement": "item is emitted",
                        "evidenceRequired": "live",
                        "reasons": [],
                    }
                ],
                "bookFiles": book_files(tmp_path, "docs/features"),
                "storyFile": None,
            }
        ),
        encoding="utf-8",
    )
    return spec


def _plan(spec: Path, source: str = PLAN) -> Path:
    module = spec / "qa_plan.py"
    module.write_text(source.format(obligation=OBLIGATION), encoding="utf-8")
    return module


def _records(spec: Path, qa_dirname: str = "qa") -> list[dict]:
    log = spec / qa_dirname / "qa-run.ndjson"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _with_background(entry: str) -> str:
    """A plan whose stack is one declared daemon."""
    return PLAN.replace(
        "from ostler_qa import Qa, plan, scenario, target",
        "from ostler_qa import Qa, background, plan, scenario, target",
    ).replace('api = target("api")', f'api = target("api")\n\n{entry}')



_SERVER = '''
import sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

delay, port, code = float(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
time.sleep(delay)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()


server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
# Self-terminating: the launcher case starts one of these as a grandchild, and a stray
# server outliving the suite is how a later test finds a port it did not expect.
threading.Timer(30.0, server.shutdown).start()
server.serve_forever()
'''


_DIES_ON_BIND = (
    "import sys\n"
    'sys.stderr.write("listen tcp :8080: bind: address already in use\\n")\n'
    "sys.exit(1)\n"
)

_DIES_LATE = "import time\ntime.sleep(0.5)\n" + _DIES_ON_BIND

_LAUNCHER = "import subprocess, sys\nsubprocess.Popen([sys.executable, '-c'] + sys.argv[1:])\n"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _argv(source: str, *args: object) -> str:
    """The `argv=[…]` literal for a daemon that runs *source* under this interpreter."""
    parts = [sys.executable, "-c", source, *(str(arg) for arg in args)]
    return "argv=[" + ", ".join(repr(part) for part in parts) + "]"


def _orphan(port: int) -> ThreadingHTTPServer:
    """A server this run did not start, answering on the port its daemon wanted."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            """Silent: the orphan is scenery, not a participant."""

        def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's spelling
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server




def test_a_run_owns_the_log_the_manifest_and_the_evidence(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    module = _plan(spec)
    stale = spec / "qa/stale.txt"
    stale.parent.mkdir()
    stale.write_text("old", encoding="utf-8")

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    assert not stale.exists()
    records = _records(spec)
    assert records[0]["kind"] == "session_start"
    assert records[-1]["kind"] == "session_stop"
    assert records[-1]["status"] == "passed"
    assert any(
        row.get("kind") == "assert"
        and OBLIGATION in row.get("covers", [])
        and row.get("result") == "PASS"
        for row in records
    )
    manifest = json.loads((spec / "qa/run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["runId"] == "qa-run-1"
    for artifact in manifest["artifacts"]:
        artifact_path = spec / artifact["path"]
        assert artifact_path.is_file()
        assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["sha256"]
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert evidence["obligations"][0]["verdict"] == "Pass"
    assert _qa_evidence_vet(evidence, spec, tmp_path) == []


def test_a_scenario_that_stops_early_claims_nothing_it_covered(tmp_path: Path) -> None:
    """A scenario that did not reach the end of its body proves none of its `covers`."""
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        PLAN + '    qa.check("the page is there", qa.get("nothing-published") == "")\n',
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "failed"
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert evidence["overall"] == "Fail"
    row = evidence["obligations"][0]
    assert row["verdict"] == "Fail"
    assert row["aborted_log_refs"] == ["api-contract:assert:1", "api-contract:assert:2"]
    assert row.get("failing_log_refs", []) == []
    assert _qa_evidence_vet(evidence, spec, tmp_path) == []

    stop = next(record for record in _records(spec) if record["kind"] == "scenario_stop")
    assert stop["aborted"] is True

    synthesized = [
        record
        for record in _records(spec)
        if record.get("kind") == "assert" and record.get("result") != "PASS"
    ]
    assert [record["covers"] for record in synthesized] == [[OBLIGATION]]
    assert [record.get("sentinel") for record in synthesized] == [True]

    mapped = build_evidence_map(spec)
    assert [row["status"] for row in mapped["obligations"]] == ["unproven"]

    tampered = json.loads(json.dumps(evidence))
    tampered["obligations"][0] = {
        "id": OBLIGATION,
        "verdict": "Pass",
        "log_refs": ["api-contract:assert:1"],
        "evidence": evidence["obligations"][0]["evidence"] or ["qa/qa-run.ndjson"],
    }
    problems = _qa_evidence_vet(tampered, spec, tmp_path)
    assert any("did not run to completion" in problem for problem in problems), problems
    assert not any("failing assertions" in problem for problem in problems), problems


def test_one_failing_assertion_sinks_the_item_it_covers(tmp_path: Path) -> None:
    """Evidence is a summary of the run log, so it may not disagree with the run log."""
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        PLAN
        + '    qa.check("the value is absent", False, actual="ok", expected="absent",\n'
        + '             covers=["{obligation}"])\n',
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "failed"
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert evidence["overall"] == "Fail"
    row = evidence["obligations"][0]
    assert row["verdict"] == "Fail"
    assert row["failing_log_refs"] == ["api-contract:assert:2"]
    assert row["log_refs"] == ["api-contract:assert:1", "api-contract:assert:2"]
    assert _qa_evidence_vet(evidence, spec, tmp_path) == []

    tampered = json.loads(json.dumps(evidence))
    tampered["obligations"][0] = {
        "id": OBLIGATION,
        "verdict": "Pass",
        "log_refs": ["api-contract:assert:1"],
        "evidence": evidence["obligations"][0]["evidence"] or ["qa/qa-run.ndjson"],
    }
    problems = _qa_evidence_vet(tampered, spec, tmp_path)
    assert any(
        "marked Pass but the run log records failing assertions" in problem
        and "api-contract:assert:2" in problem
        for problem in problems
    ), problems


def test_a_dry_run_executes_one_scenario_and_leaves_no_evidence(tmp_path: Path) -> None:
    """A planner checking its own work must not thereby produce the run's verdict."""
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        PLAN
        + '''

@scenario(target=api, mechanism="live", covers=["{obligation}"])
def second(qa: Qa) -> None:
    """A scenario that fails — the conflict branch of the same obligation."""
    qa.check("the value is absent", False, actual="ok", expected="absent",
             covers=["{obligation}"])
''',
    )
    scored = spec / "qa"
    scored.mkdir()
    (scored / "keep.txt").write_text("a scored run's ledger", encoding="utf-8")

    outcome = cmd_run(module, root=tmp_path, only=["api-contract"], label="dry")

    assert outcome.status == "passed", outcome.message
    assert set(outcome.data["scenarios"]) == {"api-contract"}
    assert (spec / "qa/dry/qa-run.ndjson").is_file()
    assert not (spec / "qa-evidence.json").exists()
    assert (scored / "keep.txt").read_text(encoding="utf-8") == "a scored run's ledger"
    assert not (scored / "qa-run.ndjson").exists()

    missing = cmd_run(module, root=tmp_path, only=["typo"], label="dry")
    assert missing.status == "invalid"
    assert "typo" in missing.message


def test_a_secret_is_runtime_only_and_redacted(tmp_path: Path, monkeypatch) -> None:
    """A secret reaches the scenario's process and nothing it leaves behind."""
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        PLAN.replace(
            "from ostler_qa import Qa, plan, scenario, target",
            "from ostler_qa import Qa, plan, scenario, secret, target",
        )
        .replace('api = target("api")', 'api = target("api")\n\nsecret("token", from_env="QA_TOKEN")')
        .replace(
            '    qa.check("the value is ok", True, actual="ok", expected="ok",'
            ' covers=["{obligation}"])',
            '    print("authorizing with", qa.secret("token"))\n'
            '    qa.check("the token was readable", bool(qa.secret("token")),\n'
            '             covers=["{obligation}"])',
        ),
    )
    monkeypatch.setenv("QA_TOKEN", "top-secret-value")

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in [
            spec / "qa/qa-run.ndjson",
            spec / "qa/qa-session.json",
            spec / "qa/steps/api-contract-stdout.txt",
        ]
        if path.exists()
    )
    assert "top-secret-value" not in persisted
    assert "authorizing with" in (spec / "qa/steps/api-contract-stdout.txt").read_text("utf-8")


def _file_secret_plan(from_file: str) -> str:
    return (
        PLAN.replace(
            "from ostler_qa import Qa, plan, scenario, target",
            "from ostler_qa import Qa, plan, scenario, secret, target",
        )
        .replace('api = target("api")', f'api = target("api")\n\nsecret("db", from_file="{from_file}")')
        .replace(
            '    qa.check("the value is ok", True, actual="ok", expected="ok",'
            ' covers=["{obligation}"])',
            '    print("connecting with", qa.secret("db"))\n'
            '    qa.check("the password was readable", bool(qa.secret("db")),\n'
            '             covers=["{obligation}"])',
        )
    )


def test_a_file_secret_is_runtime_only_and_redacted(tmp_path: Path) -> None:
    """A secret the trial wrote to a file reaches the scenario like one from the environment: read once at run start, one trailing newline stripped, and never in anything the run leaves behind — the session file persists the name, the ledger the redaction."""
    spec = _spec(tmp_path)
    module = _plan(spec, _file_secret_plan(".qa-secrets/db-password"))
    (tmp_path / ".qa-secrets").mkdir()
    (tmp_path / ".qa-secrets/db-password").write_text("hunter2-from-file\n", encoding="utf-8")

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in [
            spec / "qa/qa-run.ndjson",
            spec / "qa/qa-session.json",
            spec / "qa/steps/api-contract-stdout.txt",
        ]
        if path.exists()
    )
    assert "hunter2-from-file" not in persisted
    stdout = (spec / "qa/steps/api-contract-stdout.txt").read_text("utf-8")
    assert "connecting with [REDACTED]\n" in stdout
    assert "[REDACTED]\n\n" not in stdout


def test_a_file_secret_must_name_one_contained_source(tmp_path: Path) -> None:
    """Both sources, neither, a path that escapes the root, or one under the spec's disposable qa/ (emptied before the scenarios start) are refused at validation."""
    spec = _spec(tmp_path)
    for from_file, expected in [
        ("../outside", "escapes the repo root"),
        ("docs/specs/story-1/qa/token", "under disposable qa/"),
    ]:
        module = _plan(spec, _file_secret_plan(from_file))
        document, load_problems = load_plan(module, spec, tmp_path)
        assert not load_problems and document is not None
        problems = validate_v2(document)
        assert any(expected in item for item in problems), (from_file, problems)


def test_a_missing_secret_file_blocks_the_run(tmp_path: Path) -> None:
    """The file is the trial's to write; a run that starts without it would fail every scenario that reads the secret for a reason the plan cannot state, so it blocks first."""
    spec = _spec(tmp_path)
    module = _plan(spec, _file_secret_plan(".qa-secrets/db-password"))

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "blocked"
    assert "secret 'db' requires a non-empty file .qa-secrets/db-password" in outcome.message




def test_a_documented_node_is_separated_from_a_genuinely_unknown_id(tmp_path: Path) -> None:
    """A node the diff does not touch is not "unknown" — and saying so costs a rework lap."""
    spec = _spec(tmp_path)
    context = json.loads((spec / "qa-okf-context.json").read_text(encoding="utf-8"))
    context["contracts"] = ["docs/features/demo/api.md#tooling"]
    (spec / "qa-okf-context.json").write_text(json.dumps(context), encoding="utf-8")
    module = _plan(
        spec,
        PLAN.replace(
            'covers=["{obligation}"]',
            'covers=[\n'
            '    "{obligation}",\n'
            '    "okf:docs/features/demo/api.md#tooling:contract",  # documented, not owed here\n'
            '    "okf:docs/features/demo/api.md#tooling:raises:2",  # ditto, one bullet value\n'
            '    "okf:docs/features/demo/invented.md:contract",     # not in the book at all\n'
            ']',
        ),
    )

    document, load_problems = load_plan(module, spec, tmp_path)
    assert not load_problems and document is not None
    problems = validate_v2(document)
    documented = next(p for p in problems if "#tooling:contract" in p)
    valued = next(p for p in problems if "#tooling:raises:2" in p)
    unknown = next(p for p in problems if "invented.md" in p)

    assert "not an obligation of this change" in documented
    assert "unknown ID" not in documented
    assert "not an obligation of this change" in valued
    assert "unknown ID" not in valued
    assert OBLIGATION in documented
    assert OBLIGATION in unknown
    assert "unknown ID" in unknown


def test_validation_requires_the_okf_context(tmp_path: Path) -> None:
    spec = tmp_path / "docs/specs/story-1"
    spec.mkdir(parents=True)
    document, problems = load_plan(_plan(spec), spec, tmp_path)
    assert not problems and document is not None
    assert any("qa-okf-context.json is required" in item for item in validate_v2(document))


def test_an_input_under_disposable_qa_is_rejected(tmp_path: Path) -> None:
    """`qa/` is wiped at the start of every QA lane, so a fixture stored there is gone by the time the plan reads it — and the failure lands on whichever scenario read it first."""
    spec = _spec(tmp_path)
    (spec / "qa").mkdir()
    (spec / "qa/payload.json").write_text("{}", encoding="utf-8")
    module = _plan(
        spec,
        PLAN.replace(
            "from ostler_qa import Qa, plan, scenario, target",
            "from ostler_qa import Qa, input_file, plan, scenario, target",
        ).replace(
            'api = target("api")',
            'api = target("api")\n\ninput_file("payload", "qa/payload.json")',
        ),
    )

    outcome = cmd_validate(module, root=tmp_path)

    assert outcome.status == "invalid"
    assert any("disposable qa" in problem for problem in outcome.data["problems"])


def test_recording_cannot_be_disabled_by_the_plan_itself(tmp_path: Path) -> None:
    """A plan that may waive its own recording waives it on the run that needed the video."""
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        PLAN.replace(
            'api = target("api")',
            'api = target("web", driver="playwright", base_url="http://localhost:3000",\n'
            "             recording={{'required': False}})",
        ).replace(
            '    qa.check("the value is ok", True, actual="ok", expected="ok",'
            ' covers=["{obligation}"])',
            '    qa.vet("docs/features/demo/item.md", name="loaded")\n'
            '    qa.check("the value is ok", True, actual="ok", expected="ok",\n'
            '             covers=["{obligation}"])',
        ),
    )

    result = cmd_validate(module, root=tmp_path)
    assert any("repository policy" in problem for problem in result.data["problems"]), result.data

    (tmp_path / "ostler.yml").write_text("qa:\n  recordingExemptTargets: [web]\n", encoding="utf-8")
    assert cmd_validate(module, root=tmp_path).status == "passed"


def test_a_yaml_plan_is_rejected_with_the_replacement_named(tmp_path: Path) -> None:
    """The cutover has to be legible to whoever opens the old file, not just to the runner."""
    spec = _spec(tmp_path)
    legacy = spec / "qa-plan.yml"
    legacy.write_text("version: 2\nrun_id: qa-run-1\nstory: story-1\n", encoding="utf-8")

    document, problems = load_plan(legacy, spec, tmp_path)

    assert document is None
    assert problems == [RETIRED_YAML]
    assert "qa_plan.py" in RETIRED_YAML


def test_an_unrunnable_ready_check_is_caught_at_validation() -> None:
    """Where a bad daemon shape should fail: at validate, with a diagnostic naming it."""
    problems = _validate_background(
        [
            {"name": "api", "argv": ["go", "run", "./cmd/server"], "ready_check": "localhost:8080"},
            {"name": "web", "cmd": "npm start", "ready_check": {"assert_contains": "201"}},
            {"name": "web", "argv": [], "ready_check": {"cmd": "curl -s /", "url": "http://x/"}},
        ]
    )

    assert any("must be an http(s) URL" in item for item in problems), problems
    assert any("duplicate background daemon 'web'" in item for item in problems), problems
    assert any(".cmd is retired" in item for item in problems), problems
    assert any("ready_check.cmd is retired" in item for item in problems), problems
    assert any("argv is required and must be a non-empty list" in item for item in problems), (
        problems
    )
    assert any("supported: url, method, status, timeout" in item for item in problems), problems




def test_a_ready_check_that_is_not_a_get_200_polls_until_the_daemon_says_it_is_up(
    tmp_path: Path,
) -> None:
    """`ready_check` accepts a `{url, method, status}` mapping, not just a URL."""
    spec = _spec(tmp_path)
    port = _free_port()
    module = _plan(
        spec,
        _with_background(
            'background("api-server",\n'
            f"           {_argv(_SERVER, 0.4, port, 201)},\n"
            f'           ready_url="http://127.0.0.1:{port}/orders",\n'
            '           ready_method="POST", ready_status=201, timeout=10)'
        ),
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    records = _records(spec)
    assert not [row for row in records if row.get("kind") == "runner_error"], records
    (started,) = [row for row in records if row.get("kind") == "daemon_start"]
    assert started["ready_check"]["method"] == "POST"
    assert started["ready_check"]["status"] == 201
    assert started["argv"][0] == sys.executable


def test_a_run_that_dies_before_its_scenarios_reports_why(tmp_path: Path) -> None:
    """The caller must be told the cause, not just that nothing ran."""
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        _with_background(
            'background("api-server",\n'
            f'           {_argv("import time; time.sleep(30)")},\n'
            f'           ready_url="http://127.0.0.1:{_free_port()}/health", timeout=1)'
        ),
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "invalid", outcome.message
    assert "0 scenarios" in outcome.message
    assert "TimeoutError" in outcome.message, outcome.message
    assert "ready_check" in outcome.message, outcome.message
    assert outcome.data["runner_errors"], outcome.data


def test_a_daemon_that_dies_on_startup_is_reported_dead_with_what_it_printed(
    tmp_path: Path,
) -> None:
    """"Timed out" describes a slow service."""
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        _with_background(
            'background("api-server",\n'
            f"           {_argv(_DIES_ON_BIND)},\n"
            f'           ready_url="http://127.0.0.1:{_free_port()}/health", timeout=30)'
        ),
    )

    started = time.monotonic()
    outcome = cmd_run(module, root=tmp_path)
    elapsed = time.monotonic() - started

    assert outcome.status == "invalid", outcome.message
    assert "exited with code 1" in outcome.message, outcome.message
    assert "address already in use" in outcome.message, outcome.message
    assert elapsed < 15, f"polled a dead daemon for {elapsed:.1f}s"


def test_a_dead_daemon_whose_check_still_passes_fails_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A readiness probe asks "is anything answering", never "is it mine"."""
    spec = _spec(tmp_path)
    monkeypatch.setattr(
        session,
        "_DAEMON_TIMING",
        session._DaemonTiming(  # noqa: SLF001 - this case owns the scheduler race
            poll_s=0.01,
            settle_s=0.75,
            interrupt_grace_s=0.05,
            terminate_grace_s=0.05,
        ),
    )
    port = _free_port()
    orphan = _orphan(port)
    try:
        module = _plan(
            spec,
            _with_background(
                'background("api-server",\n'
                f"           {_argv(_DIES_ON_BIND)},\n"
                f'           ready_url="http://127.0.0.1:{port}/health", timeout=10)'
            ),
        )

        outcome = cmd_run(module, root=tmp_path)
    finally:
        orphan.shutdown()
        orphan.server_close()

    assert outcome.status == "invalid", outcome.message
    assert "exited with code 1" in outcome.message, outcome.message
    assert "something other than this run's daemon is answering" in outcome.message
    assert "address already in use" in outcome.message, outcome.message


def test_a_daemon_that_dies_just_after_a_passing_check_still_fails_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule above was a race, and this is the half of it that was losing."""
    spec = _spec(tmp_path)
    monkeypatch.setattr(
        session,
        "_DAEMON_TIMING",
        session._DaemonTiming(  # noqa: SLF001 - this case owns the scheduler race
            poll_s=0.01,
            settle_s=0.75,
            interrupt_grace_s=0.05,
            terminate_grace_s=0.05,
        ),
    )
    port = _free_port()
    orphan = _orphan(port)
    try:
        module = _plan(
            spec,
            _with_background(
                'background("api-server",\n'
                f"           {_argv(_DIES_LATE)},\n"
                f'           ready_url="http://127.0.0.1:{port}/health", timeout=10)'
            ),
        )

        outcome = cmd_run(module, root=tmp_path)
    finally:
        orphan.shutdown()
        orphan.server_close()

    assert outcome.status == "invalid", outcome.message
    assert "exited with code 1" in outcome.message, outcome.message
    assert "something other than this run's daemon is answering" in outcome.message
    assert "address already in use" in outcome.message, outcome.message


def test_a_launcher_that_forks_and_exits_zero_still_counts_as_ready(tmp_path: Path) -> None:
    """Exit 0 is a hand-off, not a death — the other half of the rule above."""
    spec = _spec(tmp_path)
    port = _free_port()
    module = _plan(
        spec,
        _with_background(
            'background("api-server",\n'
            f"           {_argv(_LAUNCHER, _SERVER, 1, port, 200)},\n"
            f'           ready_url="http://127.0.0.1:{port}/orders",\n'
            '           ready_method="POST", timeout=10)'
        ),
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message




def test_stopping_a_daemon_that_already_exited_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Teardown must survive a daemon that stopped on its own."""
    def zombie_group(_pid: int, _sig: int) -> None:
        raise PermissionError

    monkeypatch.setattr(session.os, "killpg", zombie_group)

    assert _kill_pid(8123) == 0


def test_a_live_daemon_is_still_stopped_and_reports_its_signal() -> None:
    """The EPERM tolerance above must not turn into "never kills anything"."""
    proc = subprocess.Popen("sleep 30", shell=True, start_new_session=True)
    try:
        assert _kill_pid(proc.pid) in (-signal.SIGINT, -signal.SIGTERM, -signal.SIGKILL)
    finally:
        proc.wait()



_STATEFUL = (
    "import sys, threading\n"
    "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
    "state, port = sys.argv[1], int(sys.argv[2])\n"
    "open(state, 'a').close()\n"
    "class Handler(BaseHTTPRequestHandler):\n"
    "    def log_message(self, fmt, *args):\n"
    "        pass\n"
    "    def do_GET(self):\n"
    "        self.send_response(200)\n"
    "        self.send_header('Content-Length', '0')\n"
    "        self.end_headers()\n"
    "server = ThreadingHTTPServer(('127.0.0.1', port), Handler)\n"
    "threading.Timer(30.0, server.shutdown).start()\n"
    "server.serve_forever()\n"
)


def _stateful(spec: Path, state: str, port: int, reset: list[str] | None = None) -> Path:
    """A plan whose one daemon keeps its state at *state*, written without `str.format`."""
    reset_line = f"           reset_paths={reset!r},\n" if reset else ""
    source = _with_background(
        'background("api-server",\n'
        f"           {_argv(_STATEFUL, state, port)},\n"
        f"{reset_line}"
        f'           ready_url="http://127.0.0.1:{port}/health", timeout=10)'
    ).replace("{obligation}", OBLIGATION)
    module = spec / "qa_plan.py"
    module.write_text(source, encoding="utf-8")
    return module


def test_a_daemon_can_be_pointed_at_the_runs_own_qa_directory(tmp_path: Path) -> None:
    """`{{qa_dir}}` is how a daemon is told to keep its state inside the run."""
    spec = _spec(tmp_path)
    port = _free_port()
    module = _stateful(spec, "{{qa_dir}}/links.json", port)

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    assert (spec / "qa/links.json").is_file()
    assert not list(tmp_path.rglob("*qa_dir*"))


def test_a_daemon_honours_its_declared_cwd(tmp_path: Path) -> None:
    """`background(cwd=)` was declared, recorded, and then started at the root anyway."""
    spec = _spec(tmp_path)
    (tmp_path / "services/api").mkdir(parents=True)
    port = _free_port()
    source = _with_background(
        'background("api-server",\n'
        f"           {_argv(_STATEFUL, 'started-here.json', port)},\n"
        '           cwd="services/api",\n'
        f'           ready_url="http://127.0.0.1:{port}/health", timeout=10)'
    ).replace("{obligation}", OBLIGATION)
    module = spec / "qa_plan.py"
    module.write_text(source, encoding="utf-8")

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    assert (tmp_path / "services/api/started-here.json").is_file()
    assert not (tmp_path / "started-here.json").exists()


def test_tool_env_names_are_validated_against_the_runner_and_the_secrets(tmp_path: Path) -> None:
    """The declared list is what `ostler qa validate` reads, so what a scenario body cannot reach — the runner's `QA_*`, a secret's variable, a lower-case typo — is refused here."""
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        PLAN.replace(
            "from ostler_qa import Qa, plan, scenario, target",
            "from ostler_qa import Qa, plan, scenario, secret, target, tool_env",
        ).replace(
            'api = target("api")',
            'api = target("api")\n'
            'TOKEN = secret("TOKEN", from_env="API_TOKEN")\n'
            'tool_env("TZ", "QA_SECRET", "API_TOKEN")',
        ),
    )
    document, load_problems = load_plan(module, spec, tmp_path)
    assert not load_problems and document is not None

    problems = validate_v2(document)

    assert "tool_env name 'QA_SECRET' is in the runner's QA_ namespace" in problems
    assert "tool_env name 'API_TOKEN' is a secret's from_env; reach it through secret()" in problems
    assert not any("'TZ'" in item for item in problems), problems


def test_a_daemon_cwd_outside_the_root_is_a_plan_problem(tmp_path: Path) -> None:
    """The daemon is the product and the product lives in the repo; a cwd that escapes it is refused by name at validation, where the plan agent can read it, not at start."""
    problems = _validate_background(
        [
            {"name": "api", "argv": ["x"], "cwd": "../elsewhere", "ready_check": "http://127.0.0.1:1/"},
            {"name": "web", "argv": ["x"], "cwd": "  ", "ready_check": "http://127.0.0.1:1/"},
            {"name": "ok", "argv": ["x"], "cwd": "services/api", "ready_check": "http://127.0.0.1:1/"},
            {"name": "late", "argv": ["x"], "cwd": "{{qa_dir}}/srv", "ready_check": "http://127.0.0.1:1/"},
        ],
        root=tmp_path,
    )

    assert problems == [
        "background daemon 'api'.cwd must stay inside the repo root (../elsewhere)",
        "background daemon 'web'.cwd must be a non-empty string",
    ]


def test_reset_paths_clear_stale_daemon_state_before_it_starts(tmp_path: Path) -> None:
    """State the last run left behind is the last run's answer, replayed into this one."""
    spec = _spec(tmp_path)
    stale = spec / "links.json"
    stale.write_text('["left over from the last run"]', encoding="utf-8")
    port = _free_port()
    module = _stateful(
        spec, "{{qa_dir}}/../links.json", port, reset=["{{qa_dir}}/../links.json"]
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    assert stale.read_text(encoding="utf-8") == ""


_RESTARTABLE = _STATEFUL.replace("import sys, threading", "import os, sys, threading").replace(
    "open(state, 'a').close()", "open(state, 'a').write(str(os.getpid()) + chr(10))"
)


def _restart_plan(spec: Path, port: int, restart: str) -> Path:
    """Two scenarios against one daemon; the second declares *restart* between them."""
    source = (
        _with_background(
            'background("api-server",\n'
            f"           {_argv(_RESTARTABLE, '{{qa_dir}}/../pids.txt', port)},\n"
            f'           ready_url="http://127.0.0.1:{port}/health", timeout=10)'
        )
        + "\n\n"
        + f'@scenario(target=api, mechanism="live", covers=["{{obligation}}"], {restart})\n'
        + "def api_survives_a_restart(qa: Qa) -> None:\n"
        + '    """The value is still there after the process came back."""\n'
        + '    qa.check("still ok", True, actual="ok", expected="ok", covers=["{obligation}"])\n'
    ).replace("{obligation}", OBLIGATION)
    module = spec / "qa_plan.py"
    module.write_text(source, encoding="utf-8")
    return module


def test_a_scenario_can_restart_a_daemon_before_it_runs(tmp_path: Path) -> None:
    """The persistence seam: a write in one scenario and a read in the next prove nothing about survival unless the process went away in between."""
    spec = _spec(tmp_path)
    port = _free_port()
    module = _restart_plan(spec, port, 'restart=["api-server"]')

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    pids = (spec / "pids.txt").read_text(encoding="utf-8").split()
    assert len(pids) == 2 and pids[0] != pids[1], pids
    records = _records(spec)
    starts = [r["pid"] for r in records if r.get("kind") == "daemon_start"]
    assert [str(p) for p in starts] == pids
    stops = [r for r in records if r.get("kind") == "daemon_stop"]
    assert [s.get("reason") for s in stops] == ["restart", None]
    assert stops[0]["pid"] == starts[0]
    restart = next(r for r in records if r.get("kind") == "daemon_restart")
    assert restart["name"] == "api-server"
    assert restart["scenario"] == "api-survives-a-restart"
    assert restart["pid"] == starts[1]
    kinds = [r.get("kind") for r in records]
    assert kinds.index("daemon_restart") < kinds.index("scenario_start", kinds.index("scenario_stop"))


def test_restart_names_a_declared_daemon(tmp_path: Path) -> None:
    """A name the runner could not find would surface as an exception on the scenario's turn, after everything before it had run — so validate refuses it, and refuses a restart in a plan with no daemon at all."""
    spec = _spec(tmp_path)
    module = _restart_plan(spec, _free_port(), 'restart=["db"]')
    document, load_problems = load_plan(module, spec, tmp_path)
    assert not load_problems and document is not None
    problems = validate_v2(document)
    assert any("restarts unknown daemon 'db'" in item for item in problems), problems

    module = _plan(
        spec,
        PLAN.replace(
            'covers=["{obligation}"])\ndef api_contract',
            'covers=["{obligation}"], restart=["api-server"])\ndef api_contract',
        ),
    )
    document, load_problems = load_plan(module, spec, tmp_path)
    assert not load_problems and document is not None
    problems = validate_v2(document)
    assert any("declares no background daemon" in item for item in problems), problems


def _directory_artifact_plan(body: str) -> str:
    return PLAN.replace(
        '    qa.check("the value is ok", True, actual="ok", expected="ok", covers=["{obligation}"])',
        body + '\n    qa.check("the value is ok", True, actual="ok", expected="ok", covers=["{obligation}"])',
    )


def _shell_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt the tmp repo into an `sh` QA tool — plan code may not touch the filesystem itself, so a plan builds an artifact tree the way a real one does: through a tool."""
    (tmp_path / "agents.yml").write_text("qa:\n  tools: [sh]\n", encoding="utf-8")
    config = tmp_path / "config.toml"
    config.write_text('[qa_tools.sh]\ncommand = "/bin/sh"\n', encoding="utf-8")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(config))


def test_a_directory_artifact_is_one_manifest_row_per_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The manifest hashes files and the evidence map reads files, so a directory arrives as its files — each carrying the directory it came from — never as one opaque row."""
    _shell_tool(tmp_path, monkeypatch)
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        _directory_artifact_plan(
            '    qa.tool("sh").run("-c", "echo a > a.txt; mkdir nested; echo b > nested/b.txt", cwd="report")\n'
            '    qa.artifact("report", kind="log")'
        ),
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    manifest = json.loads((spec / "qa/run-manifest.json").read_text(encoding="utf-8"))
    filed = sorted((row["path"], row["directory"]) for row in manifest["artifacts"] if "directory" in row)
    assert filed == [
        ("qa/report/a.txt", str(spec / "qa/report")),
        ("qa/report/nested/b.txt", str(spec / "qa/report")),
    ]
    assert all(row["kind"] == "log" for row in manifest["artifacts"] if "report/" in row["path"])


def test_an_empty_artifact_directory_is_a_problem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An artifact that says nothing is not evidence of anything, and the scenario that produced it aborts like one that handed over a missing file."""
    _shell_tool(tmp_path, monkeypatch)
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        _directory_artifact_plan(
            '    qa.tool("sh").run("-c", "true", cwd="report")\n    qa.artifact("report", kind="log")'
        ),
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status != "passed"
    ends = [row for row in _records(spec) if row.get("kind") == "scenario_stop"]
    assert "artifact directory is empty" in ends[0].get("message", ""), ends
