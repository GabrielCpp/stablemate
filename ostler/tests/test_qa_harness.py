"""The harness's two modes, exercised the way the driver invokes them: as a subprocess.

Importing `ostler_qa` into the test process would be the easy version and the wrong one.
The module's whole contract is that it runs under the *project's* interpreter with a
module-level registry, so a test that imports it once and declares twice would share
state across cases and prove nothing about the boundary the driver actually crosses.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

HARNESS_DIR = Path(__file__).resolve().parents[1] / "ostler" / "qa" / "harness"

PLAN = '''\
from ostler_qa import Qa, background, plan, scenario, secret, target

plan(run_id="qa-04-publish", story="04-publish")

api = target("api", interpreter=".venv/bin/python")
web = target("web", driver="playwright", base_url="http://localhost:5173", browser="chromium")

background("stack", argv=["./scripts/teststack.sh", "up"], ready_url="http://localhost:8090/healthz")
ADMIN = secret("ADMIN_TOKEN", from_env="QA_ADMIN_TOKEN")


@scenario(target=api, mechanism="live", covers=["ac:1", "okf:docs/a.md#publish:does:1"])
def publish_records_the_real_author(qa: Qa) -> None:
    """Publish ignores a spoofed author."""
    qa.capture("uid", "u-123")
    with qa.step("inspect the published object"):
        qa.check("author is the token uid", qa.get("uid") == "u-123", actual="u-123")
    qa.check("message is verbatim", True)


# Declared against `api`, not `web`: running it must not launch a browser. What it exercises
# is the raise path, and a `playwright` target here would make that test start Chromium.
@scenario(target=api, mechanism="live", covers=["ac:2"], checkpoints=["the banner shows"])
def banner_is_visible(qa: Qa) -> None:
    """The banner renders."""
    raise AssertionError("not implemented")


@scenario(target=web, mechanism="live", covers=["ac:3"])
def the_page_is_addressed_by_role(qa: Qa) -> None:
    """The book's role and route, written literally so `describe` can recover them."""
    qa.goto("/docs")
    qa.by_role("button", name="Publish").click()
    qa.by_text("done")
    qa.check("published", True)
'''


def _write(tmp_path: Path, source: str = PLAN) -> Path:
    module = tmp_path / "qa_plan.py"
    module.write_text(source, encoding="utf-8")
    return module


def _harness(*args: str, records_to: Path | None = None) -> tuple[int, str, list[dict]]:
    """Run the harness the way the driver does, returning (code, stdout, records)."""
    env = {"PYTHONPATH": str(HARNESS_DIR), "PATH": "/usr/bin:/bin"}
    command = [sys.executable, "-m", "ostler_qa", *args]
    if records_to is None:
        done = subprocess.run(command, capture_output=True, text=True, env=env, check=False)  # noqa: S603
        return done.returncode, done.stdout, []
    with records_to.open("w") as sink:
        done = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            env={**env, "OSTLER_QA_RECORD_FD": str(sink.fileno())},
            pass_fds=(sink.fileno(),),
            stdin=subprocess.DEVNULL,
            check=False,
        )
    records = [
        json.loads(line) for line in records_to.read_text(encoding="utf-8").splitlines() if line
    ]
    return done.returncode, done.stdout, records


def _describe(module: Path) -> dict:
    code, stdout, _ = _harness("describe", str(module))
    assert code == 0, stdout
    return json.loads(stdout)


def _run(module: Path, scenario_id: str, tmp_path: Path) -> tuple[int, list[dict]]:
    context = json.dumps(
        {"root": str(tmp_path), "spec_dir": str(tmp_path), "qa_dir": str(tmp_path / "qa")}
    )
    code, _, records = _harness(
        "run", str(module), scenario_id, context, records_to=tmp_path / "records.jsonl"
    )
    return code, records


def test_describe_emits_the_declaration_set(tmp_path: Path) -> None:
    described = _describe(_write(tmp_path))
    assert described["run_id"] == "qa-04-publish"
    assert described["story"] == "04-publish"
    assert described["targets"]["api"] == {"driver": "python", "interpreter": ".venv/bin/python"}
    assert described["targets"]["web"]["driver"] == "playwright"
    assert described["targets"]["web"]["base_url"] == "http://localhost:5173"
    assert described["background"][0]["ready_check"] == "http://localhost:8090/healthz"
    # An argv list, not a command line: nothing downstream of here reaches a shell, so a
    # daemon cannot be `go test ./...` with a `&&` in it.
    assert described["background"][0]["argv"] == ["./scripts/teststack.sh", "up"]


def test_describe_names_the_secret_without_reading_it(tmp_path: Path) -> None:
    # describe runs during validation and its output is logged, so it must carry the
    # variable to read rather than anything read from it.
    described = _describe(_write(tmp_path))
    assert described["secrets"] == {"ADMIN_TOKEN": {"from_env": "QA_ADMIN_TOKEN"}}


FILE_SECRET_PLAN = PLAN.replace(
    'secret("ADMIN_TOKEN", from_env="QA_ADMIN_TOKEN")',
    'secret("ADMIN_TOKEN", from_env="QA_ADMIN_TOKEN")\n'
    'secret("DB_PASSWORD", from_file=".qa-secrets/db-password")',
)


def test_describe_names_a_file_secrets_source_without_reading_it(tmp_path: Path) -> None:
    """A secret the trial wrote to a file is declared by the path, never by the contents —
    the file need not even exist at describe time, since the trial writes it later."""
    described = _describe(_write(tmp_path, FILE_SECRET_PLAN))
    assert described["secrets"]["DB_PASSWORD"] == {"from_file": ".qa-secrets/db-password"}


def test_a_secret_declares_exactly_one_source() -> None:
    harness = load_harness_module("ostler_qa")
    with pytest.raises(ValueError, match="exactly one of from_env= or from_file="):
        harness.secret("BOTH", from_env="X", from_file="y")
    with pytest.raises(ValueError, match="exactly one of from_env= or from_file="):
        harness.secret("NEITHER")


def test_describe_carries_the_daemons_a_scenario_restarts(tmp_path: Path) -> None:
    """`restart=[...]` is a declaration the runner acts on before the body runs, so it
    rides the describe record like `covers` — validated against `background` before start."""
    source = PLAN.replace(
        'checkpoints=["the banner shows"]', 'checkpoints=["the banner shows"], restart=["stack"]'
    )
    described = _describe(_write(tmp_path, source))
    assert described["scenarios"][1]["restart"] == ["stack"]
    assert "restart" not in described["scenarios"][0]


def test_describe_carries_covers_and_the_docstring_objective(tmp_path: Path) -> None:
    described = _describe(_write(tmp_path))
    first = described["scenarios"][0]
    assert first["id"] == "publish-records-the-real-author"
    assert first["target"] == "api"
    assert first["mechanism"] == "live"
    assert first["covers"] == ["ac:1", "okf:docs/a.md#publish:does:1"]
    assert first["objective"] == "Publish ignores a spoofed author."
    assert described["scenarios"][1]["checkpoints"] == ["the banner shows"]


def test_describe_counts_the_assertions_statically(tmp_path: Path) -> None:
    # The count is what replaces `_exit_sentinel`: a scenario claiming coverage and
    # calling no check proves nothing, and unlike a shell string that is now visible
    # before anything runs.
    described = _describe(_write(tmp_path))
    counts = {s["id"]: s["checks"] for s in described["scenarios"]}
    assert counts == {
        "publish-records-the-real-author": 2,
        "banner-is-visible": 0,
        "the-page-is-addressed-by-role": 1,
    }


def test_describe_recovers_the_screens_a_scenario_vets(tmp_path: Path) -> None:
    # The half of "mandatory" that bites before anything runs: `validate` reads this list to
    # refuse a UI scenario that never registers what it rendered. A screen assembled at run
    # time is reported as computed rather than guessed at, so validation can say so.
    module = _write(
        tmp_path,
        PLAN.replace(
            '    qa.check("published", True)',
            '    qa.vet("docs/features/demo/screen.md", name="loaded")\n'
            "    qa.vet(SCREEN)\n"
            '    qa.check("published", True)',
        ).replace(
            'plan(run_id="qa-04-publish", story="04-publish")',
            'SCREEN = "docs/features/demo/other.md"\n\nplan(run_id="qa-04-publish", story="04-publish")',
        ),
    )

    vets = {s["id"]: s["vets"] for s in _describe(module)["scenarios"]}
    assert vets["the-page-is-addressed-by-role"] == ["docs/features/demo/screen.md", "*"]
    assert vets["publish-records-the-real-author"] == []


def test_describe_recovers_the_locators_a_browser_scenario_writes(tmp_path: Path) -> None:
    # `_validate_book_locators` holds a browser scenario to the role, name and route the OKF
    # book documents. Under YAML it read the action list; the action list is now code, so
    # `describe` recovers the same shape from the parsed tree — before anything runs.
    described = _describe(_write(tmp_path))
    found = {s["id"]: s["locators"] for s in described["scenarios"]}
    assert found["the-page-is-addressed-by-role"] == [
        {"do": "goto", "url": "/docs"},
        {"locator": {"role": "button", "name": "Publish"}},
        {"locator": {"text": "done"}},
    ]
    assert found["publish-records-the-real-author"] == []


def test_describe_runs_nothing(tmp_path: Path) -> None:
    module = _write(
        tmp_path,
        PLAN.replace('    qa.capture("uid", "u-123")', '    raise SystemExit("ran the body")'),
    )
    assert _describe(module)["scenarios"][0]["checks"] == 2


def test_describe_reports_an_unimportable_plan(tmp_path: Path) -> None:
    # A static check YAML could never offer: the plan is rejected at validation time,
    # not discovered broken an hour into a run.
    module = _write(tmp_path, "import nonexistent_project_module\n")
    code, _, _ = _harness("describe", str(module))
    assert code != 0


def test_run_streams_records_and_passes(tmp_path: Path) -> None:
    code, records = _run(_write(tmp_path), "publish-records-the-real-author", tmp_path)
    assert code == 0
    kinds = [record["type"] for record in records]
    assert kinds == ["capture", "step_start", "assert", "step_end", "assert", "scenario"]
    # A step is stamped on the run's clock when it opens and closes — the driver grades
    # the stream after the scenario has exited, so only the harness can say when it ran.
    opened, closed = records[1], records[3]
    assert isinstance(opened["offset_ms"], int) and isinstance(closed["offset_ms"], int)
    assert 0 <= opened["offset_ms"] <= closed["offset_ms"]
    asserted = [record for record in records if record["type"] == "assert"]
    assert asserted[0]["label"] == "author is the token uid"
    assert asserted[0]["passed"] is True
    # An assert record carries the binding the check itself wrote, and nothing else.
    # It used to default to the scenario's whole `covers` list, which is what
    # qa-evidence.json aggregates over — so every assertion in the body was stamped with
    # every obligation the scenario claimed, one passing check reported the whole set
    # proven, and deleting the assertion that did the proving left the row green.
    assert asserted[0]["covers"] == []
    assert records[-1] == {
        "type": "scenario",
        "id": "publish-records-the-real-author",
        "status": "passed",
        "assertions": 2,
        "failures": 0,
        "error": None,
    }


def test_run_reports_a_raised_scenario_as_errored(tmp_path: Path) -> None:
    code, records = _run(_write(tmp_path), "banner-is-visible", tmp_path)
    assert code == 1
    assert records[-1]["status"] == "errored"
    assert "not implemented" in records[-1]["error"]


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ('    qa.check("holds", False)', "failed"),
        ('    qa.require("stops", False)\n    qa.check("unreached", True)', "failed"),
        ("    pass", "failed"),
    ],
)
def test_run_grades_the_scenario(tmp_path: Path, body: str, status: str) -> None:
    # The third case is the one that matters: a scenario claiming coverage and asserting
    # nothing is a failure at runtime too, not only a describe-time finding.
    module = _write(
        tmp_path,
        PLAN.replace('    qa.capture("uid", "u-123")', body).replace(
            '    with qa.step("inspect the published object"):\n'
            '        qa.check("author is the token uid", qa.get("uid") == "u-123", actual="u-123")\n'
            '    qa.check("message is verbatim", True)\n',
            "",
        ),
    )
    code, records = _run(module, "publish-records-the-real-author", tmp_path)
    assert code == 1
    assert records[-1]["status"] == status


def test_require_stops_the_scenario(tmp_path: Path) -> None:
    module = _write(
        tmp_path,
        PLAN.replace(
            '        qa.check("author is the token uid", qa.get("uid") == "u-123", actual="u-123")',
            '        qa.require("author is the token uid", False)',
        ),
    )
    _, records = _run(module, "publish-records-the-real-author", tmp_path)
    labels = [r["label"] for r in records if r["type"] == "assert"]
    assert labels == ["author is the token uid"]
    assert records[-1]["failures"] == 1


def test_a_ui_scenario_that_vets_nothing_fails_at_run_time(tmp_path: Path) -> None:
    """The static gate reads the plan; this one counts the calls that actually ran, so a
    scenario cannot reach the ledger green having proved only that its elements exist."""
    # A maestro target rather than the browser one: the refusal is about any UI driver, and
    # a `playwright` scenario would launch Chromium before reaching the code under test.
    module = _write(
        tmp_path,
        "from ostler_qa import Qa, plan, scenario, target\n\n"
        'plan(run_id="qa-04-publish", story="04-publish")\n\n'
        'phone = target("phone", driver="maestro")\n\n\n'
        '@scenario(target=phone, mechanism="live", covers=["ac:1"])\n'
        "def the_list_is_shown(qa: Qa) -> None:\n"
        '    """The list renders."""\n'
        '    qa.check("the list is shown", True)\n',
    )

    code, records = _run(module, "the-list-is-shown", tmp_path)

    assert code == 1
    assert records[-1]["status"] == "failed"
    assert "vetted no screen" in records[-1]["error"]


# -- the retrying assertion --------------------------------------------------------------

#: A read that is false on the first sample and true on a later one — the shape of every
#: race this API exists to end. `check` collapses it to a dead `False` before the harness
#: is called; `eventually` holds the sampler and looks again.
EVENTUALLY_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-05-arrive", story="05-arrive")

api = target("api")

samples = []


def rendered() -> bool:
    samples.append(len(samples) + 1)
    return len(samples) >= 3


@scenario(target=api, mechanism="live", covers=["ac:1", "ac:2"])
def the_badge_arrives(qa: Qa) -> None:
    """The badge is on the page once the render settles."""
    qa.check("sampled once, on the first paint", rendered())
    qa.eventually(
        "the badge arrives",
        rendered,
        interval=0.01,
        actual=lambda: len(samples),
        covers=["ac:2"],
    )
'''


def _asserts(records: list[dict]) -> list[dict]:
    return [record for record in records if record["type"] == "assert"]


def test_eventually_looks_again_where_check_sampled_the_first_paint(tmp_path: Path) -> None:
    """The motivating defect, reduced: the same read, asserted both ways, in one scenario.

    `check` reports the first paint as a product failure. `eventually` re-samples and the
    claim holds — and the record says how long it waited, so a reader can tell an assertion
    that settled from one that was true all along.
    """
    _, records = _run(_write(tmp_path, EVENTUALLY_PLAN), "the-badge-arrives", tmp_path)

    early, settled = _asserts(records)
    assert early["passed"] is False
    # Absent, not zero: a timing field on an assertion nobody retried is a claim about a
    # sample that was never taken, and it is exactly what a race reader would believe.
    assert "settled_ms" not in early and "mode" not in early
    assert settled["passed"] is True
    assert settled["mode"] == "eventually"
    assert settled["polls"] == 2
    assert settled["settled_ms"] > 0
    # Read after the loop settled — the value that decided the verdict, not one sampled
    # before the wait began.
    assert settled["actual"] == 3
    assert settled["covers"] == ["ac:2"]


def test_an_already_evaluated_condition_is_refused_and_names_a_repair_lint_accepts(
    tmp_path: Path,
) -> None:
    """Never a silent fallback to `check`. Falling back would make the new API behave
    exactly like the old one at the single moment the author got it wrong — the race ships,
    and the plan reads as though it were already guarded against one."""
    module = _write(
        tmp_path,
        EVENTUALLY_PLAN.replace("        rendered,", "        rendered(),"),
    )

    code, records = _run(module, "the-badge-arrives", tmp_path)

    assert code == 1
    assert records[-1]["status"] == "errored"
    error = records[-1]["error"]
    assert "bool" in error
    # The repair it names has to be one plan lint will accept, and the obvious spelling —
    # wrap the expression in a lambda — is admitted, so it leads.
    assert "lambda" in error
    assert "bound method" in error
    assert "named nested function" in error


def test_a_defect_in_the_condition_surfaces_instead_of_burning_the_deadline(
    tmp_path: Path,
) -> None:
    """A `KeyError` in the condition is a plan defect, and swallowing it as "not yet" would
    spend the whole timeout and then report it as a product failure — the mis-hypothesis
    this work exists to end, recreated inside its own fix."""
    module = _write(
        tmp_path,
        EVENTUALLY_PLAN.replace(
            "        rendered,\n        interval=0.01,",
            '        lambda: {}["absent"],\n        timeout=60,\n        interval=0.01,',
        ),
    )

    started = time.monotonic()
    code, records = _run(module, "the-badge-arrives", tmp_path)
    elapsed = time.monotonic() - started

    assert code == 1
    assert records[-1]["status"] == "errored"
    assert "absent" in records[-1]["error"]
    assert elapsed < 30, "the deadline was polled through instead of the defect being raised"


def test_a_red_eventually_records_the_deadline_it_spent(tmp_path: Path) -> None:
    # What tells a repair turn that the page never arrived at all, rather than arriving
    # wrong: the assertion looked repeatedly, for a stated budget, and never saw it.
    module = _write(
        tmp_path,
        EVENTUALLY_PLAN.replace(
            "        rendered,\n        interval=0.01,",
            "        lambda: False,\n        timeout=0.05,\n        interval=0.01,",
        ),
    )

    code, records = _run(module, "the-badge-arrives", tmp_path)

    assert code == 1
    settled = _asserts(records)[1]
    assert settled["passed"] is False
    assert settled["timeout_ms"] == 50
    assert settled["polls"] > 1
    assert settled["settled_ms"] >= 50


def test_require_eventually_stops_the_cascade(tmp_path: Path) -> None:
    """When the state a journey waited for never came, every later assertion reads a page
    the plan is not about, and the run reports failures whose actual values are all noise."""
    module = _write(
        tmp_path,
        EVENTUALLY_PLAN.replace("    qa.eventually(", "    qa.require_eventually(").replace(
            "        rendered,\n        interval=0.01,",
            "        lambda: False,\n        timeout=0.05,\n        interval=0.01,",
        )
        + '    qa.check("never reached", True)\n',
    )

    code, records = _run(module, "the-badge-arrives", tmp_path)

    assert code == 1
    assert [record["label"] for record in _asserts(records)] == [
        "sampled once, on the first paint",
        "the badge arrives",
    ]


def test_describe_counts_eventually_as_an_assertion_and_binds_its_covers(
    tmp_path: Path,
) -> None:
    """The one-line static change that makes the retrying spelling usable: `CHECK_METHODS`
    is what `count_checks` and `extract_check_covers` key off, so a scenario written wholly
    in `eventually` is neither vacuous nor uncredited for the obligation it proves."""
    described = _describe(_write(tmp_path, EVENTUALLY_PLAN))

    scenario = described["scenarios"][0]
    assert scenario["checks"] == 2
    assert scenario["check_covers"] == ["ac:2"]


STATUS_PLAN = '''\
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-05-confirm", story="05-confirm")

api = target("api")


class Always201(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        self.send_response(201)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@scenario(target=api, mechanism="live", covers=["okf:docs/a.md#confirm:concurrency:1"])
def a_stale_confirm_is_refused(qa: Qa) -> None:
    """A confirmation quoting an old version is refused."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Always201)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    qa.http.base_url = "http://127.0.0.1:%d" % server.server_address[1]
    qa.http.post("/api/seats/A2/booking", json_body={"version": 1}, expect_status=409)
    qa.check("unreached", True)
'''


def test_an_unmet_expect_status_is_recorded_before_it_raises(tmp_path: Path) -> None:
    """The loudest failure the harness has must leave an assertion behind.

    `expect_status=409` says the product refuses this. When it answers 201 instead, the
    `HttpError` aborts the scenario before any `qa.check` runs — so without this record the
    run log holds nothing bound to the obligation, and `ostler qa evidence-map` reports
    `claimed-but-unasserted` (a QA gap) for what is actually the product contradicting the
    book. A benchmark trial with a seeded compare-and-swap defect was detected exactly this
    way and scored as a miss.
    """
    code, records = _run(_write(tmp_path, STATUS_PLAN), "a-stale-confirm-is-refused", tmp_path)

    assert code == 1
    asserted = _asserts(records)
    assert len(asserted) == 1
    assert asserted[0]["passed"] is False
    assert asserted[0]["actual"] == 201
    assert asserted[0]["expected"] == [409]
    # Bound to the scenario's whole `covers`, unlike a bare check: the call aborts the
    # scenario, so nothing else it claimed will be shown either.
    assert asserted[0]["covers"] == ["okf:docs/a.md#confirm:concurrency:1"]
    assert records[-1]["status"] == "errored"


ROOT_TOKEN_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-06-import", story="06-import")

api = target("api")

DOCUMENT = {"item": {"id": "abc"}, "items": [{"id": "def"}]}


@scenario(target=api, mechanism="live", covers=["okf:docs/a.md#import:does:1"])
def a_rooted_path_reads_the_same_field(qa: Qa) -> None:
    """A `$`-rooted json_path names the same field as the bare one."""
    qa.verify("json_path", DOCUMENT, path="$.item.id", equals="abc")
    qa.verify("json_path", DOCUMENT, path="item.id", equals="abc")
    qa.verify("json_path", DOCUMENT, path="$.items[0].id", equals="def")
    qa.verify("json_path", DOCUMENT, path="$.item.missing", absent=True)
'''


def test_a_dollar_rooted_json_path_resolves_like_the_bare_one(tmp_path: Path) -> None:
    """`$` is JSONPath's root token, not a key the document is expected to hold.

    The vocabulary's own examples are written `$.error.title`, and `qa.session._extract_path`
    has always stripped the prefix. The harness's resolver did not, so every `$`-rooted
    `json_path` failed as *absent* against a document that held the value — a red assertion
    filed against the product for a defect in the check.
    """
    code, records = _run(
        _write(tmp_path, ROOT_TOKEN_PLAN), "a-rooted-path-reads-the-same-field", tmp_path
    )

    assert code == 0
    asserted = _asserts(records)
    assert len(asserted) == 4
    assert [record["passed"] for record in asserted] == [True, True, True, True]


FILTER_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-06-import", story="06-import")

api = target("api")

DOCUMENT = {"items": [{"id": "def"}, {"id": "ghi", "n": 2}]}


@scenario(target=api, mechanism="live", covers=["okf:docs/a.md#import:does:1"])
def a_filter_selects_by_what_an_entry_holds(qa: Qa) -> None:
    """A filter segment names the entry by a field it holds, not by its position."""
    qa.verify("json_path", DOCUMENT, path="$.items[?(@.id=='ghi')].n", equals=2)
    qa.verify("json_path", DOCUMENT, path="items[*].id", matches="ghi")
    qa.check("read through a selector", qa.field(DOCUMENT, "items[?(@.n==2)].id") == "ghi")
'''


def test_a_filter_segment_selects_an_entry_by_a_field_it_holds(tmp_path: Path) -> None:
    """`items[?(@.id=='ghi')].n` is a claim about the entry whose id is ghi — the order the
    product writes its list in is not what the book claimed. `[*]` with a value claim is
    refused as ambiguous unless it selects exactly one; `matches` against two ids is red too."""
    code, records = _run(
        _write(tmp_path, FILTER_PLAN), "a-filter-selects-by-what-an-entry-holds", tmp_path
    )

    assert code == 1
    asserted = _asserts(records)
    assert [record["passed"] for record in asserted] == [True, False, True]
    assert asserted[1]["actual"] == {"selected": ["def", "ghi"]}


def test_a_browser_problem_is_a_failing_assertion_bound_to_the_scenario_covers(
    tmp_path: Path,
) -> None:
    """An uncaught page error or a 5xx contradicts what the scenario set out to prove.

    The browser's clean-gate used to ride only on the scenario record's `error`: the
    scenario went red, but every assertion it had recorded stayed green, so the evidence
    map scored its obligations *covered* off those checks while the page had thrown.
    Each problem is now a failing assertion bound to the scenario's `covers`, which is the
    reading that holds — the run observed the product under this scenario and it broke —
    and the one the map turns into `contradicted`.
    """
    harness = load_harness_module("ostler_qa")

    emitted: list[dict] = []
    recorder = harness._Recorder(fd=-1)
    recorder.emit = emitted.append  # type: ignore[method-assign]
    qa = harness.Qa(
        scenario_id="list-is-shown",
        target=harness.Target("web", driver="playwright"),
        root=tmp_path,
        spec_dir=tmp_path,
        qa_dir=tmp_path / "qa",
        covers=["ac:1", "okf:docs/a.md#list:does:1"],
        recorder=recorder,
    )

    problem = "1 uncaught page error(s) in the browser, first: locale is undefined"
    returned = harness._bind_browser_unclean(qa, [problem])

    assert returned == [problem]
    assert qa.failures == 1
    assert emitted == [
        {
            "type": "assert",
            "id": "list-is-shown-1",
            "label": "the browser stayed clean",
            "passed": False,
            "actual": problem,
            "expected": harness.BROWSER_CLEAN_EXPECTED,
            "covers": ["ac:1", "okf:docs/a.md#list:does:1"],
            "origin": "browser",
        }
    ]
    # Nothing to bind is nothing recorded: a clean browser adds no assertion of its own.
    assert harness._bind_browser_unclean(qa, []) == []
    assert qa.failures == 1


TOOL_ENV_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target, tool_env

plan(run_id="qa-tool-env", story="tool-env")
api = target("api")
tool_env("TALLY_HOME", "TZ")


@scenario(target=api, mechanism="live", covers=["ac:1"])
def the_tool_runs_where_and_how_the_scenario_says(qa: Qa) -> None:
    """A tool observed under the scenario's own cwd and env, not the runner's."""
    tool = qa.tool("sh")
    # pwd inside the run's scratch space, created on demand; env overlaid by declared name.
    done = tool.run("-c", 'pwd; printf %s "$TALLY_HOME"', cwd="home-a", env={"TALLY_HOME": "/h"})
    qa.check("ran in qa.dir/home-a", done.stdout.splitlines()[0].endswith("/qa/home-a"), actual=done.stdout)
    qa.check("env overlaid", done.stdout.splitlines()[1] == "/h", actual=done.stdout)
    # The default is still the repo root, with the inherited environment.
    plain = tool.run("-c", "pwd")
    qa.check("default cwd is the root", plain.stdout.strip() == qa.root.as_posix(), actual=plain.stdout)
    try:
        tool.run("-c", "true", cwd="../escaped")
    except ValueError as exc:
        qa.check("an escaping cwd is refused", "qa directory" in str(exc), actual=str(exc))
    else:
        qa.check("an escaping cwd is refused", False)
    try:
        tool.run("-c", "true", env={"PATH": "/nowhere"})
    except ValueError as exc:
        qa.check("an undeclared env name is refused", "tool_env" in str(exc), actual=str(exc))
    else:
        qa.check("an undeclared env name is refused", False)
'''


def test_a_tool_runs_with_a_contained_cwd_and_a_declared_env(tmp_path: Path) -> None:
    """`Tool.run` was `cwd=root` with the runner's environment and no way to say otherwise —
    for a product whose contract is what it does to the directory it was run in, the one
    axis the scenario most needed. cwd stays inside `qa.dir`; env names must be declared."""
    module = _write(tmp_path, TOOL_ENV_PLAN)
    assert _describe(module)["tool_env"] == ["TALLY_HOME", "TZ"]
    context = json.dumps(
        {
            "root": str(tmp_path),
            "spec_dir": str(tmp_path),
            "qa_dir": str(tmp_path / "qa"),
            "tools": {"sh": "sh"},
        }
    )
    code, stdout, records = _harness(
        "run", str(module), "the-tool-runs-where-and-how-the-scenario-says", context,
        records_to=tmp_path / "records.jsonl",
    )
    checks = [r for r in records if r["type"] == "assert"]
    assert code == 0, (stdout, records)
    assert [c["label"] for c in checks] == [
        "ran in qa.dir/home-a",
        "env overlaid",
        "default cwd is the root",
        "an escaping cwd is refused",
        "an undeclared env name is refused",
    ]
    assert all(c["passed"] for c in checks), checks
    assert (tmp_path / "qa/home-a").is_dir()
    assert not (tmp_path / "escaped").exists()


def test_tool_env_refuses_a_name_it_cannot_safely_hand_out() -> None:
    """The declaration is the validation surface, so a bad name fails at import."""
    harness = load_harness_module("ostler_qa")
    harness.REGISTRY.tool_env.clear()
    with pytest.raises(ValueError, match=r"\[A-Z_\]"):
        harness.tool_env("lower")
    harness.tool_env("TZ")
    with pytest.raises(ValueError, match="duplicate"):
        harness.tool_env("TZ")
    harness.REGISTRY.tool_env.clear()


DIRECTORY_ARTIFACT_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-dir-artifact", story="dir-artifact")
api = target("api")


@scenario(target=api, mechanism="live", covers=["ac:1"])
def a_report_tree_is_filed(qa: Qa) -> None:
    """A directory is evidence too."""
    report = qa.dir / "report"
    report.mkdir(parents=True)
    (report / "a.txt").write_text("a")
    qa.artifact("report", kind="log")
    qa.artifact("single.txt", kind="log").write_text("one")
    qa.check("filed", True)
'''


def test_artifact_marks_a_directory_so_the_runner_files_it_file_by_file(tmp_path: Path) -> None:
    """`qa.artifact` was a file, full stop — a CLI whose contract is the tree it writes had no
    way to hand that tree over. The harness only marks the shape; the runner reads the tree
    once the scenario is done and files each file under it."""
    module = _write(tmp_path, DIRECTORY_ARTIFACT_PLAN)
    code, records = _run(module, "a-report-tree-is-filed", tmp_path)
    assert code == 0, records
    artifacts = [r for r in records if r["type"] == "artifact"]
    assert [(Path(a["path"]).name, a.get("directory")) for a in artifacts] == [
        ("report", True),
        ("single.txt", None),
    ]


CAPTURE_FEEDS_REQUEST_PLAN = '''\
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-08-capture", story="08-capture")

api = target("api")


class AccountThenEcho(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps({"account_id": "acme-42"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        received = json.loads(self.rfile.read(length) or b"{}")
        body = json.dumps({"linked_account_id": received.get("account_id")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@scenario(target=api, mechanism="live", covers=["okf:docs/a.md#accounts:does:1"])
def an_account_id_captured_from_one_response_addresses_the_next(qa: Qa) -> None:
    """An id captured from an API response substitutes into a later request's body."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), AccountThenEcho)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    qa.http.base_url = "http://127.0.0.1:%d" % server.server_address[1]
    created = qa.http.get("/api/accounts/new")
    qa.capture_field("account_id", created.json(), "account_id")
    linked = qa.http.post(
        "/api/accounts/link", json_body={"account_id": qa.resolve("$account_id")}
    )
    qa.check(
        "the captured id reached the server, not the literal reference",
        qa.field(linked.json(), "linked_account_id") == "acme-42",
        actual=qa.field(linked.json(), "linked_account_id"),
    )
'''


def test_a_capture_from_a_response_feeds_a_later_request(tmp_path: Path) -> None:
    """`$name` is a runtime binding, resolved before the value reaches the HTTP call.

    `qa.capture_field` reads the id out of the first response and `qa.capture`s it; the
    second request names it as `$account_id` in its body, and the scenario resolves it
    explicitly with `qa.resolve(...)` before handing it to `qa.http.post` — `Http` itself
    treats `json_body` as a plain literal and never substitutes on its own — so the server
    sees the real id rather than the literal reference string.
    """
    code, records = _run(
        _write(tmp_path, CAPTURE_FEEDS_REQUEST_PLAN),
        "an-account-id-captured-from-one-response-addresses-the-next",
        tmp_path,
    )
    assert code == 0, records
    asserted = _asserts(records)
    assert len(asserted) == 1
    assert asserted[0]["passed"] is True
    captures = [r for r in records if r["type"] == "capture"]
    assert captures == [{"type": "capture", "key": "account_id", "value": "acme-42"}]


CAPTURE_MISS_PLAN = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-09-capture-miss", story="09-capture-miss")

api = target("api")


@scenario(target=api, mechanism="live", covers=["okf:docs/a.md#accounts:does:1"])
def a_capture_path_that_finds_nothing_is_a_defect(qa: Qa) -> None:
    """A declared capture whose path is absent from the response is a book/code defect."""
    qa.capture_field("missing_id", {"account_id": "acme-42"}, "no_such_field")
    qa.check("unreached", True)
'''


def test_a_capture_that_finds_nothing_is_a_defect_fault(tmp_path: Path) -> None:
    """A capture is a promise the plan makes about the response, not an optional read.

    `qa.field` alone would answer `MISSING` in silence — the right behaviour for an
    assertion, the wrong one for a capture, since every later `$name` reference would then
    fail at its own, unrelated line instead of naming the actual absent path.
    """
    code, records = _run(
        _write(tmp_path, CAPTURE_MISS_PLAN),
        "a-capture-path-that-finds-nothing-is-a-defect",
        tmp_path,
    )
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert "no_such_field" in fault["detail"]
    assert "missing_id" in fault["detail"]


class _FakeLocator:
    """Just enough of Playwright's `Locator` for `capture_text`: `count()` and `inner_text()`."""

    def __init__(self, text: str = "", count: int = 1) -> None:
        self._text = text
        self._count = count

    def count(self) -> int:
        return self._count

    def inner_text(self) -> str:
        return self._text


class _FakePage:
    """Just enough of Playwright's `Page` for `qa.by_text` — records what it was asked for."""

    def __init__(self) -> None:
        self.text_calls: list[str] = []

    def get_by_text(self, text: str, **kwargs: object) -> _FakeLocator:
        self.text_calls.append(text)
        if text == "Welcome, acme":
            return _FakeLocator("Welcome, acme", count=1)
        return _FakeLocator(count=0)


def _ui_qa(tmp_path: Path) -> Any:
    """A `Qa` built the way `test_a_browser_problem_...` builds one: no subprocess, no
    real Playwright — just enough of the harness's own object to exercise `qa.page`."""
    harness = load_harness_module("ostler_qa")
    recorder = harness._Recorder(fd=-1)
    recorder.emit = lambda record: None
    return harness.Qa(
        scenario_id="greeting-flows",
        target=harness.Target("web", driver="playwright"),
        root=tmp_path,
        spec_dir=tmp_path,
        qa_dir=tmp_path / "qa",
        covers=["ac:1"],
        recorder=recorder,
    )


def test_a_ui_capture_feeds_a_later_locator(tmp_path: Path) -> None:
    """Text captured off one locator substitutes into a later `by_text` call — the UI half
    of the API capture-into-a-later-request test above. `by_text` takes a plain literal
    now, so the scenario resolves `$greeting` explicitly before passing it on."""
    qa = _ui_qa(tmp_path)
    page = _FakePage()
    qa.page = page

    banner = qa.by_text("Welcome, acme")
    qa.capture_text("greeting", banner)
    qa.by_text(qa.resolve("$greeting"))

    assert page.text_calls == ["Welcome, acme", "Welcome, acme"]


def test_a_ui_capture_that_finds_nothing_is_a_defect_fault(tmp_path: Path) -> None:
    """A locator that matches zero elements is a book/code defect, not a silent miss —
    the UI half of `test_a_capture_that_finds_nothing_is_a_defect_fault` above."""
    qa = _ui_qa(tmp_path)
    emitted: list[dict[str, Any]] = []
    qa._recorder.emit = emitted.append  # noqa: SLF001
    qa.page = _FakePage()

    missing = qa.by_text("Nothing here")
    with pytest.raises(RuntimeError, match="matched no elements"):
        qa.capture_text("missing_greeting", missing)

    [fault] = [r for r in emitted if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert "missing_greeting" in fault["detail"]


def test_qa_resolve_substitutes_a_reference_embedded_mid_string(tmp_path: Path) -> None:
    """`qa.resolve` substitutes an occurrence anywhere in the string, not only a value that
    is entirely one reference — a route path is typically `/orgs/@acme.id/projects`, one
    segment of a larger literal, not the whole string."""
    qa = _ui_qa(tmp_path)
    qa.capture("id", "acme-1")
    assert qa.resolve("/orgs/$id/projects") == "/orgs/acme-1/projects"


LITERAL_AT_AND_DOLLAR_PLAN = '''\
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-10-literal", story="10-literal")

api = target("api")

RECEIVED = []


class Echo(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        RECEIVED.append(json.loads(self.rfile.read(length) or b"{}"))
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@scenario(target=api, mechanism="live", covers=["okf:docs/a.md#pay:does:1"])
def a_literal_at_and_dollar_are_never_treated_as_references(qa: Qa) -> None:
    """A body carrying an `@`/`$` literal reaches the server verbatim, unresolved."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    qa.http.base_url = "http://127.0.0.1:%d" % server.server_address[1]
    qa.http.post("/api/pay", json_body={"email": "user@acme.dev", "note": "Pay $total"})
    qa.check("received the literal, unresolved", RECEIVED == [
        {"email": "user@acme.dev", "note": "Pay $total"}
    ], actual=RECEIVED)
'''


def test_http_treats_at_and_dollar_literals_as_plain_text(tmp_path: Path) -> None:
    """`Http` no longer resolves anything implicitly (Fix 2) — a literal `@acme.dev` handle
    or a `$5` price/`Pay $total` label is sent verbatim, exactly as the plan wrote it, never
    misread as a reference and never faulted for failing to resolve one."""
    code, records = _run(
        _write(tmp_path, LITERAL_AT_AND_DOLLAR_PLAN),
        "a-literal-at-and-dollar-are-never-treated-as-references",
        tmp_path,
    )
    assert code == 0, records
    asserted = _asserts(records)
    assert len(asserted) == 1
    assert asserted[0]["passed"] is True
    assert not [r for r in records if r["type"] == "fixture_fault"]
