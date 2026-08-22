"""What a whole QA run owns: the ledger, the manifest, the evidence and the stack under it.

These cases are the v2 runner's, carried over onto the format that replaced it. The plan is
Python now, but nothing here is about the plan language — a dry run may not touch the scored
ledger, an item covered by a failing assertion may not be published Pass, a daemon that died
may not be reported as slow. Each one is a failure that was observed live, and the docstring
is the reason it stays.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ostler.artifact.kinds import _qa_evidence_vet
from ostler.qa.plan import RETIRED_YAML, _validate_background, load_plan, validate_v2
from ostler.qa.evidence_map import build_evidence_map
from ostler.qa.run import cmd_run, cmd_validate
from ostler.qa.session import _kill_pid

OBLIGATION = "okf:docs/features/demo/item.md:contract"

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


# ---------------------------------------------------------------------------
# Daemons, without a shell
#
# `background:` takes an argv list, so every daemon below is a program and its arguments.
# The program is this interpreter, which is the one thing a test can rely on being on the
# box, and the source is passed with `-c`. Nothing here goes through `bash -c`, which is
# the property under test as much as anything the assertions say: a daemon that could be a
# command line could be `go test ./...`, and the sandbox never sees it because daemons
# start on the host.
#
# Braces are avoided throughout — `_plan` runs the plan source through `str.format`.
# ---------------------------------------------------------------------------

#: A server that binds after *delay* seconds and answers *code* to a POST, 405 to a GET.
#: The delay is what makes the readiness poll do its job: the first probe must fail.
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


#: A daemon that cannot bind, printing what a real server prints on its way out.
_DIES_ON_BIND = (
    "import sys\n"
    'sys.stderr.write("listen tcp :8080: bind: address already in use\\n")\n'
    "sys.exit(1)\n"
)

#: The same death, but late enough that the readiness probe wins the race to be sampled.
_DIES_LATE = "import time\ntime.sleep(0.5)\n" + _DIES_ON_BIND

#: A launcher: it starts the real server as a child and exits 0, like `docker compose up -d`.
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
    """A server this run did not start, answering on the port its daemon wanted.

    The stand-in for the previous run's process still bound to 8080 — the thing a readiness
    probe cannot distinguish from the daemon under test, which is the whole reason a
    non-zero exit outranks a passing check.
    """

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


# ---------------------------------------------------------------------------
# the ledger, the manifest and the evidence
# ---------------------------------------------------------------------------


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
    """A scenario that did not reach the end of its body proves none of its `covers`.

    This is the failing-assertion case's blind side, and it cost a whole benchmark round.
    An assertion that ran and disagreed writes a record naming the obligation it sank; a
    scenario killed by a browser locator timeout writes no record at all — so the passing
    prefix it managed first was the only thing bound to the obligation, and it published
    `Pass` for a screen the run never got to look at. The reader downstream sees a covered
    obligation with green refs beside it and no way to tell that the steps which would have
    contradicted it never ran.

    The demotion is deliberately over the *whole* `covers`, not the part left unproven: an
    assertion that passed before the abort proved a state the steps after it never got to
    leave, and reading it as standing evidence is the same optimism in a smaller place.
    """
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        # The lookup of a capture nothing published stands in for every way a scenario dies
        # mid-body — a Playwright timeout, a detached node, a fixture that went away. What
        # matters is the shape, not the exception: a green assertion is already on the
        # ledger when the body stops. (A bare `raise` would be a plan the linter refuses,
        # which is a different test.)
        PLAN + '    qa.check("the page is there", qa.get("nothing-published") == "")\n',
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "failed"
    evidence = json.loads((spec / "qa-evidence.json").read_text(encoding="utf-8"))
    assert evidence["overall"] == "Fail"
    row = evidence["obligations"][0]
    assert row["verdict"] == "Fail"
    # The passing assertion is named as one the abort invalidated rather than dropped, so
    # the reason a row is Fail with a green ref on it is on the artifact.
    assert row["aborted_log_refs"] == ["api-contract:assert:1"]
    assert _qa_evidence_vet(evidence, spec, tmp_path) == []

    stop = next(record for record in _records(spec) if record["kind"] == "scenario_stop")
    assert stop["aborted"] is True

    # And the synthesized assertion is bound to what the scenario claimed, so the evidence
    # map reaches the same verdict from the log alone. It is marked as the harness's own
    # note rather than left to look like an observation: the map has to demote the
    # obligation without accusing the product of a defect nothing in this run went and
    # looked for, which is why the status is `unproven` and not `contradicted`.
    synthesized = [
        record
        for record in _records(spec)
        if record.get("kind") == "assert" and record.get("result") != "PASS"
    ]
    assert [record["covers"] for record in synthesized] == [[OBLIGATION]]
    assert [record.get("sentinel") for record in synthesized] == [True]

    mapped = build_evidence_map(spec)
    assert [row["status"] for row in mapped["obligations"]] == ["unproven"]


def test_one_failing_assertion_sinks_the_item_it_covers(tmp_path: Path) -> None:
    """Evidence is a summary of the run log, so it may not disagree with the run log.

    The aggregation used to read the passing assertions alone, which made an item Pass as
    soon as any one assertion covering it succeeded. A live journey that walked eight steps
    and failed the ninth therefore published every criterion Pass under an `overall: Fail` —
    an artifact strictly worse than none, because the QA assessor downstream either routes
    on the per-item verdicts the same file's `overall` contradicts, or spends a turn every
    pass rediscovering that it has to read `qa/qa-run.ndjson` instead.
    """
    spec = _spec(tmp_path)
    module = _plan(
        spec,
        # The failing check binds the obligation explicitly: an assertion is credited to what
        # it names and nothing else, so "sinks the item it covers" now says which item.
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
    # The disproof is named, not merely implied by the absence of a Pass: a consumer routing
    # on this file should not have to re-derive from the log which assertion sank the item.
    assert row["failing_log_refs"] == ["api-contract:assert:2"]
    assert row["log_refs"] == ["api-contract:assert:1", "api-contract:assert:2"]
    assert _qa_evidence_vet(evidence, spec, tmp_path) == []

    # And the gate rejects the same claim made by hand, which is the shape an agent authoring
    # the file itself produces — every other check asks whether a Pass is supported.
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
    """A planner checking its own work must not thereby produce the run's verdict.

    `clear_qa_evidence` wipes `<spec>/qa/` and the evidence gate reads it, so a dry run that
    wrote there would let a plan tuned until it passed become its own admissible proof — and
    would destroy a scored run's ledger on the way. The subset and the redirect are one
    feature: dry run for authoring, scored run for the record.
    """
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
    # The failing scenario was not selected, so it neither ran nor sank the verdict.
    assert set(outcome.data["scenarios"]) == {"api-contract"}
    assert (spec / "qa/dry/qa-run.ndjson").is_file()
    assert not (spec / "qa-evidence.json").exists()
    assert (scored / "keep.txt").read_text(encoding="utf-8") == "a scored run's ledger"
    assert not (scored / "qa-run.ndjson").exists()

    # A name it cannot run is a stated error, not a silently empty run reported as passing.
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
    # It really did reach the scenario — otherwise the redaction above proves nothing.
    assert "authorizing with" in (spec / "qa/steps/api-contract-stdout.txt").read_text("utf-8")


# ---------------------------------------------------------------------------
# validation of what surrounds the scenarios
# ---------------------------------------------------------------------------


def test_a_documented_node_is_separated_from_a_genuinely_unknown_id(tmp_path: Path) -> None:
    """A node the diff does not touch is not "unknown" — and saying so costs a rework lap.

    The live failure: a plan covered `okf:…/api.md#tooling:contract`. `#tooling` is a real
    documented section, so "covers unknown ID" sent the author back to the book to confirm a
    node that was never in question, instead of to the obligation list — which is the only
    place that says what this change actually owes. The plan came back asserting the same id
    and the story spent one of its three plan reworks on the round trip.
    """
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

    # The documented-but-untouched one says so, and does not call the node unknown.
    assert "not an obligation of this change" in documented
    assert "unknown ID" not in documented
    # …and so does one naming a single value of an enumerated bullet. Its trailing index is
    # not part of the node id, and reading it as one sent every such cover to the "unknown
    # ID" branch — the exact wrong turn this message exists to prevent.
    assert "not an obligation of this change" in valued
    assert "unknown ID" not in valued
    # Both name what the plan *could* cover — the list neither message used to carry.
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
    """`qa/` is wiped at the start of every QA lane, so a fixture stored there is gone by the
    time the plan reads it — and the failure lands on whichever scenario read it first.
    """
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
            # A UI scenario has to vet, so the plan that tests the *recording* policy has to
            # satisfy the vetting one too — otherwise it fails for the wrong reason.
            '    qa.check("the value is ok", True, actual="ok", expected="ok",'
            ' covers=["{obligation}"])',
            '    qa.vet("docs/features/demo/item.md", name="loaded")\n'
            '    qa.check("the value is ok", True, actual="ok", expected="ok",\n'
            '             covers=["{obligation}"])',
        ),
    )

    result = cmd_validate(module, root=tmp_path)
    assert any("repository policy" in problem for problem in result.data["problems"]), result.data

    # The repository may waive it, in the file the repository owns.
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
    """Where a bad daemon shape should fail: at validate, with a diagnostic naming it.

    `background` is the block whose entries reach a subprocess. A failure at run time gets a
    status and a sentence; a failure here is handed to the plan agent as a field-level
    diagnostic it can act on. The entries below cannot be authored through `background()` —
    they are the shapes a hand-written or generated declaration set produces, which is what
    the validator sees.
    """
    problems = _validate_background(
        [
            {"name": "api", "argv": ["go", "run", "./cmd/server"], "ready_check": "localhost:8080"},
            {"name": "web", "cmd": "npm start", "ready_check": {"assert_contains": "201"}},
            {"name": "web", "argv": [], "ready_check": {"cmd": "curl -s /", "url": "http://x/"}},
        ]
    )

    assert any("must be an http(s) URL" in item for item in problems), problems
    assert any("duplicate background daemon 'web'" in item for item in problems), problems
    # Both retired fields are refused by name. An author porting an older plan wrote `cmd`
    # on purpose, and "argv is required" would read as a typo rather than as a removal.
    assert any(".cmd is retired" in item for item in problems), problems
    assert any("ready_check.cmd is retired" in item for item in problems), problems
    assert any("argv is required and must be a non-empty list" in item for item in problems), (
        problems
    )
    assert any("supported: url, method, status, timeout" in item for item in problems), problems


# ---------------------------------------------------------------------------
# the stack a scenario is entitled to assume
# ---------------------------------------------------------------------------


def test_a_ready_check_that_is_not_a_get_200_polls_until_the_daemon_says_it_is_up(
    tmp_path: Path,
) -> None:
    """`ready_check` accepts a `{url, method, status}` mapping, not just a URL.

    A bare URL cannot express every service's notion of "up": the plan that surfaced this ran
    an API whose only route was a `POST`, so no `GET` answered 200 and the string form could
    not probe it at all. The mapping used to be handed straight to `urlopen`, which set
    `.timeout` on it — an `AttributeError`, which the poll's `URLError`/`OSError` guard did
    not catch, so it aborted the run before its first scenario.

    That plan reached the POST by declaring a `curl` command line and matching `201` in its
    output, which is where the last host shell in a QA run lived. The capability was HTTP the
    whole time; saying so directly keeps the plan working and removes the shell.

    The daemon here is slow on purpose: the check must fail once and be retried, which is the
    whole point of a readiness probe. Its 405 to a `GET` is not scenery either — a probe that
    accepted any answer would pass against a server that has no such route.
    """
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
    # The ledger records a program and its arguments. There is no command line to record.
    assert started["argv"][0] == sys.executable


def test_a_run_that_dies_before_its_scenarios_reports_why(tmp_path: Path) -> None:
    """The caller must be told the cause, not just that nothing ran.

    The ledger has always carried a `runner_error` record, but the returned message carried
    only counts — so a crash in the runner surfaced to the coder workflow's QA gate as
    "0 scenarios" with no cause. Having nothing to route around, the gate sent a valid,
    reviewer-approved plan back to be re-planned until its rework guard ran out. A gate can
    only act on a failure it can read.
    """
    spec = _spec(tmp_path)
    # Alive but never ready: it binds nothing, and the probe's port answers no one.
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
    """"Timed out" describes a slow service. A daemon that never started is a different fault.

    A service that cannot bind, compile or migrate exits in under a second, and the poll used
    to keep probing the corpse for the rest of the timeout and then report `ready_check timed
    out after 30s` — true of a slow daemon, misleading about a dead one, and silent on the
    cause. The run that prompted this had `listen tcp :8080: bind: address already in use`
    sitting in `qa/daemon-api-server.log` while the QA verdict said only "timed out"; the
    agent had to go find it and a gate deciding whether to retry could not see it at all.

    So both halves are asserted: the exit code (this is death, not slowness) and the daemon's
    own last words. The wall clock is asserted too — the whole point is not waiting out a
    timeout that cannot end any other way.
    """
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
    # Failed on the exit, not by waiting out the 30s the plan asked for.
    assert elapsed < 15, f"polled a dead daemon for {elapsed:.1f}s"


def test_a_dead_daemon_whose_check_still_passes_fails_the_run(tmp_path: Path) -> None:
    """A readiness probe asks "is anything answering", never "is it mine".

    This is the observed false pass, reproduced. A previous run's server was still bound to
    the port, so the daemon this run started died instantly on `address already in use` — and
    the probe got its `201` from the orphan. The session recorded `passed` with zero runner
    errors, and the suite validated a binary built five minutes earlier instead of the code
    under test. Silent, and worse than any false failure.

    The orphan here is literal: a server already bound to the port before the run starts. The
    daemon dies on it, the probe gets its 200 from the squatter, and the run must still fail.
    A non-zero exit outranks a passing check; the launcher case below pins the other half,
    that exit 0 does not.
    """
    spec = _spec(tmp_path)
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
    # The message must name the actual fault, or the reader concludes the check is flaky.
    assert "something other than this run's daemon is answering" in outcome.message
    assert "address already in use" in outcome.message, outcome.message


def test_a_daemon_that_dies_just_after_a_passing_check_still_fails_the_run(
    tmp_path: Path,
) -> None:
    """The rule above was a race, and this is the half of it that was losing.

    Both facts are sampled in the same instant: the orphan answers immediately, and our own
    daemon — which is going to die on `address already in use` — has not been scheduled long
    enough to have exited, so `poll()` reads `None`. Ready wins, and the suite runs green
    against the previous run's server. Exactly the false pass the test above claims to catch,
    reached by losing the race instead of by the check arriving late.

    The daemon here dies half a second in, which is what a real bind failure behind a startup
    script looks like. Nothing about the verdict may depend on which of the two won.
    """
    spec = _spec(tmp_path)
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
    """Exit 0 is a hand-off, not a death — the other half of the rule above.

    `docker compose up -d`, a wrapper that backgrounds the real server, an `npm start` that
    execs and detaches: all exit 0 while the service they started comes up behind them. If a
    clean exit stopped the poll, none of them could ever be a daemon here.
    """
    spec = _spec(tmp_path)
    port = _free_port()
    module = _plan(
        spec,
        _with_background(
            'background("api-server",\n'
            # Hands off to a child that becomes ready after the launcher is already gone.
            f"           {_argv(_LAUNCHER, _SERVER, 1, port, 200)},\n"
            f'           ready_url="http://127.0.0.1:{port}/orders",\n'
            '           ready_method="POST", timeout=10)'
        ),
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message


# ---------------------------------------------------------------------------
# teardown
# ---------------------------------------------------------------------------


def test_stopping_a_daemon_that_already_exited_is_not_an_error() -> None:
    """Teardown must survive a daemon that stopped on its own.

    `killpg` does not answer the same way everywhere for a group with nothing left in it: on
    macOS/BSD an unreaped zombie leader gives EPERM (a zombie has no credentials to check the
    signal against), where Linux gives ESRCH. The kill path guarded only `ProcessLookupError`,
    so every `ostler qa run` on macOS ended by raising `PermissionError` out of
    `stop_all_daemons` — the run failed on cleanup after its scenarios had already passed.

    The **outcome** of that difference is not portable either, and asserting one platform's
    number is how this test then failed on the other Unix. A zombie is still a process on
    Linux, so `killpg` *succeeds*: the escalation runs its full SIGINT → SIGTERM window and
    reports SIGKILL, where macOS stops at the first EPERM and reports that nothing landed.
    Both are the contract being kept. What this test owns is that teardown **survives** — it
    returns rather than raising — so it accepts either answer and pins the invariant instead
    of the platform.
    """
    proc = subprocess.Popen("exit 0", shell=True, start_new_session=True)
    pid = proc.pid
    # Deliberately NOT reaped: the zombie window is exactly the case that broke.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            break
        except PermissionError:
            break  # macOS: the group is now all-zombie, which is what we want
        time.sleep(0.02)

    # 0 on macOS (EPERM read as "gone"); -SIGKILL on Linux, where the zombie group is real
    # enough to signal. Neither is a failure; raising would be.
    assert _kill_pid(pid) in (0, -signal.SIGKILL)
    proc.wait()


def test_a_live_daemon_is_still_stopped_and_reports_its_signal() -> None:
    """The EPERM tolerance above must not turn into "never kills anything"."""
    proc = subprocess.Popen("sleep 30", shell=True, start_new_session=True)
    try:
        assert _kill_pid(proc.pid) in (-signal.SIGINT, -signal.SIGTERM, -signal.SIGKILL)
    finally:
        proc.wait()


# ---------------------------------------------------------------------------
# where a daemon keeps its state
# ---------------------------------------------------------------------------

#: A server that touches the state file it is given, then answers 200 to a GET.
#: Braceless on purpose: it travels inside a plan source these tests build by hand.
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
    """A plan whose one daemon keeps its state at *state*, written without `str.format`.

    `_plan` runs its source through `str.format`, which would eat the `{{…}}` these two
    cases are about — a doubled-brace token is exactly what the runner is asked to expand.
    """
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
    """`{{qa_dir}}` is how a daemon is told to keep its state inside the run.

    Unexpanded it does not fail, which is why this is a test and not a crash: the token
    falls through to the capture lookup, comes back as itself, and the daemon dutifully
    creates a literal `{{qa_dir}}` directory beside the spec — a state file the next run
    inherits, in a run whose entire premise is that it does not.
    """
    spec = _spec(tmp_path)
    port = _free_port()
    module = _stateful(spec, "{{qa_dir}}/links.json", port)

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    assert (spec / "qa/links.json").is_file()
    assert not list(tmp_path.rglob("*qa_dir*"))
def test_reset_paths_clear_stale_daemon_state_before_it_starts(tmp_path: Path) -> None:
    """State the last run left behind is the last run's answer, replayed into this one.

    A daemon that persists is the point of the fixture — but a run that starts on top of
    the previous run's file is scoring a product it did not build. The paths expand like
    any other, so the same `{{qa_dir}}` token works when the state lives outside it too.
    """
    spec = _spec(tmp_path)
    stale = spec / "links.json"
    stale.write_text('["left over from the last run"]', encoding="utf-8")
    port = _free_port()
    module = _stateful(
        spec, "{{qa_dir}}/../links.json", port, reset=["{{qa_dir}}/../links.json"]
    )

    outcome = cmd_run(module, root=tmp_path)

    assert outcome.status == "passed", outcome.message
    # Touched fresh by the daemon after the unlink, so "exists" is not the assertion.
    assert stale.read_text(encoding="utf-8") == ""
