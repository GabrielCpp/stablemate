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
from pathlib import Path

import pytest

HARNESS_DIR = Path(__file__).resolve().parents[1] / "ostler" / "qa" / "harness"

PLAN = '''\
from ostler_qa import Qa, background, plan, scenario, secret, target

plan(run_id="qa-04-publish", story="04-publish")

api = target("api", interpreter=".venv/bin/python")
web = target("web", driver="playwright", base_url="http://localhost:5173", browser="chromium")

background("stack", cmd="./scripts/teststack.sh up", ready_url="http://localhost:8090/healthz")
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


def test_describe_names_the_secret_without_reading_it(tmp_path: Path) -> None:
    # describe runs during validation and its output is logged, so it must carry the
    # variable to read rather than anything read from it.
    described = _describe(_write(tmp_path))
    assert described["secrets"] == {"ADMIN_TOKEN": {"from_env": "QA_ADMIN_TOKEN"}}


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
    asserted = [record for record in records if record["type"] == "assert"]
    assert asserted[0]["label"] == "author is the token uid"
    assert asserted[0]["passed"] is True
    # covers defaults to the scenario's declaration, which is what qa-evidence.json
    # aggregates each assert record over.
    assert asserted[0]["covers"] == ["ac:1", "okf:docs/a.md#publish:does:1"]
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
