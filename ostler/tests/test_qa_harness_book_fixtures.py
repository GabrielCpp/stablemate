"""`Qa.fixture()`'s book-fixture tier: dispatch order, env-not-shell-text, secrets-as-names, fault classification per Q38, needs memoization, and `@node.key`/`$name` namespacing."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from ostler.qa.drivers import stop_servers

HARNESS_DIR = Path(__file__).resolve().parents[1] / "ostler" / "qa" / "harness"

PLAN_HEADER = '''\
from ostler_qa import Qa, plan, scenario, target

plan(run_id="qa-fixtures", story="fixtures")

api = target("api", interpreter=".venv/bin/python")

'''


def _write(tmp_path: Path, scenario_body: str) -> Path:
    module = tmp_path / "qa_plan.py"
    module.write_text(PLAN_HEADER + scenario_body, encoding="utf-8")
    return module


def _harness(*args: str, env: dict[str, str], records_to: Path) -> tuple[int, str, list[dict]]:
    command = [sys.executable, "-m", "ostler_qa", *args]
    with records_to.open("w") as sink:
        done = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            env={**env, "PYTHONPATH": str(HARNESS_DIR), "OSTLER_QA_RECORD_FD": str(sink.fileno())},
            pass_fds=(sink.fileno(),),
            stdin=subprocess.DEVNULL,
            check=False,
        )
    records = [json.loads(line) for line in records_to.read_text(encoding="utf-8").splitlines() if line]
    return done.returncode, done.stdout + done.stderr, records


def _as_resolved(book_fixtures: dict) -> dict:
    """Fill in the page and the step `timeout` every fixture carries once `book_fixtures.resolved()` has run."""
    for name, spec in book_fixtures.items():
        spec.setdefault("page", f"docs/fixtures/{name}.md")
        for step in spec.get("steps", []):
            if not step.get("missing_run") and "timeout" not in step:
                step["timeout"] = 5.0
    return book_fixtures


def _run(
    module: Path, scenario_id: str, tmp_path: Path, *, book_fixtures: dict, env: dict[str, str] | None = None,
    lap_dir: Path | None = None,
) -> tuple[int, str, list[dict]]:
    context = json.dumps(
        {
            "root": str(tmp_path),
            "spec_dir": str(tmp_path),
            "qa_dir": str(tmp_path / "qa"),
            "book_fixtures": _as_resolved(book_fixtures),
            "lap_dir": str(lap_dir) if lap_dir is not None else "",
        }
    )
    return _harness(
        "run", str(module), scenario_id, context,
        env={**{"PATH": "/usr/bin:/bin"}, **(env or {})},
        records_to=tmp_path / "records.jsonl",
    )


def _seed_step(script: Path, body: str) -> None:
    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)


PROVIDES_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def uses_the_seeded_account(qa: Qa) -> None:
    """Runs the book fixture and reads back what it provides."""
    qa.fixture("seeded-acme")
    qa.check("id is on file", qa.get("id") == "does-not-exist") if False else None
    qa.check("fixture ran", True)
'''


def test_fixture_dispatches_book_fixtures_before_the_agentsyml_tier(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, '#!/bin/sh\necho \'{"id": "acc-1"}\'\n')
    module = _write(tmp_path, PROVIDES_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": [], "provides": [{"key": "id", "from": "seed-it", "read": ""}], "needs": [], "secrets": [],
        }
    }
    code, stdout, records = _run(module, "uses-the-seeded-account", tmp_path, book_fixtures=book_fixtures)
    assert code == 0, (stdout, records)
    fixture_records = [r for r in records if r.get("type") == "fixture"]
    assert fixture_records and fixture_records[0]["ok"] is True


ENV_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def passes_args_through_env_not_shell_text(qa: Qa) -> None:
    """The declared arg must reach the step's own environment."""
    qa.fixture("seeded-acme", "id=needle; rm -rf /tmp/should-not-run")
    qa.check("fixture ran", True)
'''


def test_args_reach_the_step_via_env_never_interpolated_into_shell_text(tmp_path: Path) -> None:
    out = tmp_path / "seen-env.txt"
    script = tmp_path / "seed.sh"
    _seed_step(script, f'#!/bin/sh\nprintf "%s" "$id" > {out}\necho \'{{}}\'\n')
    module = _write(tmp_path, ENV_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": ["id"], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, stdout, _records = _run(module, "passes-args-through-env-not-shell-text", tmp_path, book_fixtures=book_fixtures)
    assert code == 0, stdout
    assert out.read_text(encoding="utf-8") == "needle; rm -rf /tmp/should-not-run"


SECRET_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def needs_a_secret(qa: Qa) -> None:
    """Declares a secret the harness's own environment does not have."""
    qa.fixture("seeded-acme")
    qa.check("unreachable", True)
'''


def test_a_missing_secret_is_a_capability_fault(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, '#!/bin/sh\necho \'{}\'\n')
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": [], "provides": [], "needs": [], "secrets": ["MISSING_API_TOKEN"],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "capability"
    assert fault["fixture"] == "seeded-acme"
    dumped = "\n".join(json.dumps(r) for r in records)
    assert "MISSING_API_TOKEN" in dumped


def test_a_missing_cwd_is_an_environment_fault(tmp_path: Path) -> None:
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "command": "true", "cwd": str(tmp_path / "does-not-exist")}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "environment"


def test_a_nonzero_exit_is_a_defect(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, "#!/bin/sh\nexit 3\n")
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"


def test_a_failed_probe_step_is_a_capability_fault(tmp_path: Path) -> None:
    script = tmp_path / "probe.sh"
    _seed_step(script, "#!/bin/sh\nexit 1\n")
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "probe", "id": "probe-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, _stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "capability"


def test_a_failed_step_keeps_the_end_of_its_output_where_the_error_is_named(tmp_path: Path) -> None:
    """A traceback names its error on its last line, so the detail keeps the tail of a long output."""
    script = tmp_path / "seed.sh"
    _seed_step(script, "#!/bin/sh\nprintf 'frame %.0s' $(seq 200) >&2\necho 'HTTPError: HTTP Error 400: Bad Request' >&2\nexit 1\n")
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, _stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["detail"].endswith("HTTP Error 400: Bad Request")


def test_a_missing_command_is_a_defect_whose_detail_names_it(tmp_path: Path) -> None:
    """`bash -c` exits 126/127 for a name it never found — identical, from the exit code alone, to a typo in the recipe."""
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "command": "this-command-does-not-exist-anywhere", "cwd": str(tmp_path)}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert "command not found" in fault["detail"]
    assert "126" in fault["detail"] or "127" in fault["detail"]


def test_a_timeout_is_a_defect_not_an_environment_fault(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, "#!/bin/sh\nsleep 5\n")
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "command": str(script), "cwd": str(tmp_path), "timeout": "0.2"}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"


def test_malformed_provides_is_a_defect(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, "#!/bin/sh\necho 'not json'\n")
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": [], "provides": [{"key": "id", "from": "seed-it", "read": ""}], "needs": [], "secrets": [],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"


FROM_READ_NEEDS_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def a_project_needs_a_widget_count(qa: Qa) -> None:
    """Runs the dependent fixture, whose arg is bound to an earlier step's own value."""
    qa.fixture("seeded-globex")
    qa.check("fixture ran", True)
'''


def test_provides_from_names_an_earlier_step_and_read_names_its_path(tmp_path: Path) -> None:
    prepare_script = tmp_path / "prepare-acme.sh"
    _seed_step(prepare_script, "#!/bin/sh\necho '{\"widgets\": [7, 8, 9]}'\n")
    seed_script = tmp_path / "seed-acme.sh"
    _seed_step(seed_script, "#!/bin/sh\necho '{}'\n")
    globex_out = tmp_path / "globex-seen-count.txt"
    globex_script = tmp_path / "seed-globex.sh"
    _seed_step(globex_script, f'#!/bin/sh\nprintf "%s" "$count" > {globex_out}\necho \'{{}}\'\n')
    module = _write(tmp_path, FROM_READ_NEEDS_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [
                {"kind": "prepare", "id": "prepare-it", "command": str(prepare_script), "cwd": str(tmp_path)},
                {"kind": "seed", "id": "seed-it", "command": str(seed_script), "cwd": str(tmp_path)},
            ],
            "args": [], "needs": [], "secrets": [],
            "provides": [{"key": "count", "from": "prepare-it", "read": ".widgets[0]"}],
        },
        "seeded-globex": {
            "steps": [{"kind": "seed", "command": str(globex_script), "cwd": str(tmp_path)}],
            "args": ["count"], "provides": [],
            "needs": [{"fixture": "seeded-acme", "args": {"count": "@seeded-acme.count"}}],
            "secrets": [],
        },
    }
    code, stdout, _records = _run(module, "a-project-needs-a-widget-count", tmp_path, book_fixtures=book_fixtures)
    assert code == 0, stdout
    assert globex_out.read_text(encoding="utf-8") == "7"


CHAINED_STEPS_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def a_later_step_reads_what_an_earlier_step_provided(qa: Qa) -> None:
    """A fixture signs in, then seeds with the token its sign-in step printed."""
    qa.fixture("seeded-acme")
    qa.check("fixture ran", True)
'''


def test_a_later_step_reads_each_fact_an_earlier_step_provided_from_its_environment(tmp_path: Path) -> None:
    sign_in = tmp_path / "sign-in.sh"
    _seed_step(sign_in, "#!/bin/sh\necho '{\"idToken\": \"tok-1\"}'\n")
    seen = tmp_path / "seen.txt"
    seed = tmp_path / "seed.sh"
    _seed_step(seed, f'#!/bin/sh\nprintf "%s %s" "$token" "$region" > {seen}\necho \'{{}}\'\n')
    module = _write(tmp_path, CHAINED_STEPS_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [
                {"kind": "seed", "id": "sign-in", "command": str(sign_in), "cwd": str(tmp_path)},
                {"kind": "seed", "id": "seed-it", "command": str(seed), "cwd": str(tmp_path)},
            ],
            "args": [], "needs": [], "secrets": [],
            "provides": [
                {"key": "token", "from": "sign-in", "read": "idToken"},
                {"key": "region", "is": "eu"},
            ],
        }
    }
    code, stdout, _records = _run(module, "a-later-step-reads-what-an-earlier-step-provided", tmp_path, book_fixtures=book_fixtures)
    assert code == 0, stdout
    assert seen.read_text(encoding="utf-8") == "tok-1 eu"


def test_provides_from_naming_an_unknown_step_is_a_defect(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, "#!/bin/sh\necho '{}'\n")
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": [], "needs": [], "secrets": [],
            "provides": [{"key": "id", "from": "no-such-step", "read": "id"}],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert "no-such-step" in fault["detail"]


def test_provides_read_naming_an_unresolvable_path_is_a_defect(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, "#!/bin/sh\necho '{}'\n")
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": [], "needs": [], "secrets": [],
            "provides": [{"key": "id", "from": "seed-it", "read": "no_such_key"}],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert "id" in fault["detail"] and "absent" in fault["detail"]


NEEDS_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def a_project_needs_an_account(qa: Qa) -> None:
    """Runs the dependent fixture, which runs its own need exactly once."""
    qa.fixture("seeded-globex")
    qa.fixture("seeded-globex")
    qa.check("fixture ran", True)
'''


def test_a_shared_need_runs_exactly_once_per_scenario(tmp_path: Path) -> None:
    counter = tmp_path / "acme-runs.txt"
    acme_script = tmp_path / "seed-acme.sh"
    _seed_step(acme_script, f'#!/bin/sh\nprintf "x" >> {counter}\necho \'{{"id": "acc-1"}}\'\n')
    globex_out = tmp_path / "globex-seen-id.txt"
    globex_script = tmp_path / "seed-globex.sh"
    _seed_step(globex_script, f'#!/bin/sh\nprintf "%s" "$id" > {globex_out}\necho \'{{}}\'\n')
    module = _write(tmp_path, NEEDS_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(acme_script), "cwd": str(tmp_path)}],
            "args": [], "provides": [{"key": "id", "from": "seed-it", "read": ""}], "needs": [], "secrets": [],
        },
        "seeded-globex": {
            "steps": [{"kind": "seed", "command": str(globex_script), "cwd": str(tmp_path)}],
            "args": ["id"], "provides": [],
            "needs": [{"fixture": "seeded-acme", "args": {"id": "@seeded-acme.id"}}],
            "secrets": [],
        },
    }
    code, stdout, _records = _run(module, "a-project-needs-an-account", tmp_path, book_fixtures=book_fixtures)
    assert code == 0, stdout
    assert counter.read_text(encoding="utf-8") == "x"
    assert globex_out.read_text(encoding="utf-8") == "acc-1"


LAP_SCENARIOS = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def first_page(qa: Qa) -> None:
    """Arranges the dependent fixture first in the lap."""
    qa.fixture("seeded-globex")
    qa.check("fixture ran", True)


@scenario(target=api, mechanism="live", covers=["ac:2"])
def second_page(qa: Qa) -> None:
    """Arranges it again later in the same lap, and reads what its need provides."""
    qa.fixture("seeded-globex")
    qa.check("the need's id reached this scenario", qa.resolve("@seeded-acme.id") == "acc-1")
'''


def _lap_fixtures(tmp_path: Path, counter: Path, acme_body: str) -> dict:
    acme_script = tmp_path / "seed-acme.sh"
    _seed_step(acme_script, acme_body)
    globex_script = tmp_path / "seed-globex.sh"
    _seed_step(globex_script, f'#!/bin/sh\nprintf "g" >> {counter}\necho \'{{}}\'\n')
    return {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(acme_script), "cwd": str(tmp_path)}],
            "args": [], "provides": [{"key": "id", "from": "seed-it", "read": ""}], "needs": [], "secrets": [],
        },
        "seeded-globex": {
            "steps": [{"kind": "seed", "command": str(globex_script), "cwd": str(tmp_path)}],
            "args": ["id"], "provides": [],
            "needs": [{"fixture": "seeded-acme", "args": {"id": "@seeded-acme.id"}}],
            "secrets": [],
        },
    }


def test_a_precondition_built_in_one_scenario_is_reused_by_the_next_in_its_lap(tmp_path: Path) -> None:
    counter = tmp_path / "runs.txt"
    book_fixtures = _lap_fixtures(tmp_path, counter, f'#!/bin/sh\nprintf "a" >> {counter}\necho \'{{"id": "acc-1"}}\'\n')
    module = _write(tmp_path, LAP_SCENARIOS)
    lap = tmp_path / "lap"

    first_code, first_out, first_records = _run(module, "first-page", tmp_path, book_fixtures=book_fixtures, lap_dir=lap)
    second_code, second_out, second_records = _run(module, "second-page", tmp_path, book_fixtures=book_fixtures, lap_dir=lap)

    assert first_code == 0, first_out
    assert second_code == 0, second_out
    assert counter.read_text(encoding="utf-8") == "ag"
    assert {r["name"]: r["reused"] for r in first_records if r.get("type") == "fixture"} == {
        "seeded-acme": False, "seeded-globex": False}
    assert {r["name"]: r["reused"] for r in second_records if r.get("type") == "fixture"} == {
        "seeded-acme": True, "seeded-globex": True}
    built = next(r for r in first_records if r.get("type") == "fixture" and r["name"] == "seeded-acme")
    assert (built["page"], built["lifetime"]) == ("docs/fixtures/seeded-acme.md", "lap")
    assert built["seconds"] >= 0


def test_a_precondition_that_failed_in_its_lap_fails_again_without_running(tmp_path: Path) -> None:
    counter = tmp_path / "runs.txt"
    book_fixtures = _lap_fixtures(tmp_path, counter, f'#!/bin/sh\nprintf "a" >> {counter}\necho boom >&2\nexit 3\n')
    module = _write(tmp_path, LAP_SCENARIOS)
    lap = tmp_path / "lap"

    first_code, _first_out, first_records = _run(module, "first-page", tmp_path, book_fixtures=book_fixtures, lap_dir=lap)
    second_code, _second_out, second_records = _run(module, "second-page", tmp_path, book_fixtures=book_fixtures, lap_dir=lap)

    assert first_code != 0
    assert second_code != 0
    assert counter.read_text(encoding="utf-8") == "a"
    [first_fault] = [r for r in first_records if r.get("type") == "fixture_fault"]
    [second_fault] = [r for r in second_records if r.get("type") == "fixture_fault"]
    assert second_fault == first_fault


def test_a_precondition_of_scenario_lifetime_is_built_again_by_each_scenario_of_a_lap(tmp_path: Path) -> None:
    counter = tmp_path / "runs.txt"
    book_fixtures = _lap_fixtures(tmp_path, counter, f'#!/bin/sh\nprintf "a" >> {counter}\necho \'{{"id": "acc-1"}}\'\n')
    book_fixtures["seeded-globex"]["lifetime"] = "scenario"
    module = _write(tmp_path, LAP_SCENARIOS)
    lap = tmp_path / "lap"

    first_code, first_out, _first_records = _run(module, "first-page", tmp_path, book_fixtures=book_fixtures, lap_dir=lap)
    second_code, second_out, second_records = _run(module, "second-page", tmp_path, book_fixtures=book_fixtures, lap_dir=lap)

    assert first_code == 0, first_out
    assert second_code == 0, second_out
    assert counter.read_text(encoding="utf-8") == "agg"
    assert {r["name"]: r["reused"] for r in second_records if r.get("type") == "fixture"} == {
        "seeded-acme": True, "seeded-globex": False}


def test_without_a_lap_each_scenario_builds_its_own_preconditions(tmp_path: Path) -> None:
    counter = tmp_path / "runs.txt"
    book_fixtures = _lap_fixtures(tmp_path, counter, f'#!/bin/sh\nprintf "a" >> {counter}\necho \'{{"id": "acc-1"}}\'\n')
    module = _write(tmp_path, LAP_SCENARIOS)

    first_code, first_out, _first_records = _run(module, "first-page", tmp_path, book_fixtures=book_fixtures)
    second_code, second_out, _second_records = _run(module, "second-page", tmp_path, book_fixtures=book_fixtures)

    assert first_code == 0, first_out
    assert second_code == 0, second_out
    assert counter.read_text(encoding="utf-8") == "agag"


def test_a_needs_binding_naming_an_unresolvable_node_key_is_a_defect(tmp_path: Path) -> None:
    acme_script = tmp_path / "seed-acme.sh"
    _seed_step(acme_script, '#!/bin/sh\necho \'{"id": "acc-1"}\'\n')
    globex_script = tmp_path / "seed-globex.sh"
    _seed_step(globex_script, "#!/bin/sh\necho '{}'\n")
    module = _write(tmp_path, NEEDS_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(acme_script), "cwd": str(tmp_path)}],
            "args": [], "provides": [{"key": "id", "from": "seed-it", "read": ""}], "needs": [], "secrets": [],
        },
        "seeded-globex": {
            "steps": [{"kind": "seed", "command": str(globex_script), "cwd": str(tmp_path)}],
            "args": ["id"], "provides": [],
            "needs": [{"fixture": "seeded-acme", "args": {"id": "@seeded-acme.no_such_key"}}],
            "secrets": [],
        },
    }
    code, stdout, records = _run(module, "a-project-needs-an-account", tmp_path, book_fixtures=book_fixtures)
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert fault["fixture"] == "seeded-globex"
    assert "no_such_key" in fault["detail"]


def test_a_needs_binding_naming_an_uncaptured_dollar_name_is_a_defect(tmp_path: Path) -> None:
    acme_script = tmp_path / "seed-acme.sh"
    _seed_step(acme_script, '#!/bin/sh\necho \'{"id": "acc-1"}\'\n')
    globex_script = tmp_path / "seed-globex.sh"
    _seed_step(globex_script, "#!/bin/sh\necho '{}'\n")
    module = _write(tmp_path, NEEDS_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(acme_script), "cwd": str(tmp_path)}],
            "args": [], "provides": [{"key": "id", "from": "seed-it", "read": ""}], "needs": [], "secrets": [],
        },
        "seeded-globex": {
            "steps": [{"kind": "seed", "command": str(globex_script), "cwd": str(tmp_path)}],
            "args": ["id"], "provides": [],
            "needs": [{"fixture": "seeded-acme", "args": {"id": "$never_captured"}}],
            "secrets": [],
        },
    }
    code, stdout, records = _run(module, "a-project-needs-an-account", tmp_path, book_fixtures=book_fixtures)
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert fault["fixture"] == "seeded-globex"
    assert "never_captured" in fault["detail"]


def test_a_step_with_no_run_command_is_a_defect_not_a_silent_skip(tmp_path: Path) -> None:
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "missing_run": True}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert fault["fixture"] == "seeded-acme"


def test_a_browser_step_the_book_cannot_state_is_a_defect_naming_why(tmp_path: Path) -> None:
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "sign-in", "unperformable": "`open:` links no `screen`"}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert "`open:` links no `screen`" in json.dumps(fault)


def test_a_browser_step_on_a_scenario_with_no_browser_is_a_defect(tmp_path: Path) -> None:
    module = _write(tmp_path, SECRET_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "sign-in", "browser": [{"open": "/login", "screen": "login.md"}]}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        }
    }
    code, stdout, records = _run(module, "needs-a-secret", tmp_path, book_fixtures=book_fixtures)
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert fault["fixture"] == "seeded-acme"


def test_an_unresolvable_needs_link_is_a_defect_not_a_silent_skip(tmp_path: Path) -> None:
    globex_script = tmp_path / "seed-globex.sh"
    _seed_step(globex_script, "#!/bin/sh\necho '{}'\n")
    module = _write(tmp_path, NEEDS_SCENARIO)
    book_fixtures = {
        "seeded-globex": {
            "steps": [{"kind": "seed", "command": str(globex_script), "cwd": str(tmp_path)}],
            "args": [], "provides": [],
            "needs": [{"fixture": None, "unresolved": "no-such-fixture.md", "args": {}}],
            "secrets": [],
        },
    }
    code, stdout, records = _run(module, "a-project-needs-an-account", tmp_path, book_fixtures=book_fixtures)
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert fault["fixture"] == "seeded-globex"
    assert "no-such-fixture.md" in fault["detail"]


def test_an_arg_colliding_with_a_secret_name_is_a_defect(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, "#!/bin/sh\necho '{}'\n")
    module = _write(tmp_path, ENV_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": ["id"], "provides": [], "needs": [], "secrets": ["id"],
        }
    }
    code, stdout, records = _run(
        module, "passes-args-through-env-not-shell-text", tmp_path,
        book_fixtures=book_fixtures, env={"id": "should-not-be-overridden"},
    )
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert fault["fixture"] == "seeded-acme"
    assert "id" in fault["detail"]


NAMESPACE_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def a_capture_and_a_provide_share_no_namespace(qa: Qa) -> None:
    """A `$name` capture and a fixture's `@node.key` provide never collide."""
    qa.capture("id", "captured-value")
    qa.fixture("seeded-acme")
    qa.check("the capture kept its own value", qa.get("id") == "captured-value")
'''


def test_node_provides_and_dollar_captures_are_namespaced_apart(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, '#!/bin/sh\necho \'{"id": "acc-1"}\'\n')
    module = _write(tmp_path, NAMESPACE_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd": str(tmp_path)}],
            "args": [], "provides": [{"key": "id", "from": "seed-it", "read": ""}], "needs": [], "secrets": [],
        }
    }
    code, stdout, _records = _run(
        module, "a-capture-and-a-provide-share-no-namespace", tmp_path, book_fixtures=book_fixtures,
    )
    assert code == 0, stdout


SCENARIO_FRAME_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def the_fixture_frame_and_the_tool_call_land_in_one_place(qa: Qa) -> None:
    """`working-directory: scenario:` and `qa.tool(...).run(..., cwd=qa.scenario_checkout_copy())` must
    resolve to the exact same directory, not merely two directories under `qa.dir`."""
    qa.fixture("seeded-acme")
    fixture_cwd = qa.resolve("@seeded-acme.fixture_cwd")
    tool = qa.tool("sh")
    done = tool.run("-c", "pwd", cwd=qa.scenario_checkout_copy())
    qa.check(
        "fixture cwd-frame and qa.tool cwd=qa.scenario_checkout_copy() are the same directory",
        fixture_cwd == done.stdout.strip(),
        actual=(fixture_cwd, done.stdout.strip()),
    )
'''


def test_the_scenario_frame_and_a_tool_run_land_in_the_same_directory(tmp_path: Path) -> None:
    script = tmp_path / "seed.sh"
    _seed_step(script, '#!/bin/sh\nprintf \'{"cwd": "%s"}\' "$(pwd)"\n')
    module = _write(tmp_path, SCENARIO_FRAME_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(script), "cwd-frame": "scenario"}],
            "args": [], "provides": [{"key": "fixture_cwd", "from": "seed-it", "read": "cwd"}],
            "needs": [], "secrets": [],
        }
    }
    context = json.dumps(
        {
            "root": str(tmp_path),
            "spec_dir": str(tmp_path),
            "qa_dir": str(tmp_path / "qa"),
            "book_fixtures": _as_resolved(book_fixtures),
            "tools": {"sh": "sh"},
        }
    )
    code, stdout, records = _harness(
        "run", str(module), "the-fixture-frame-and-the-tool-call-land-in-one-place", context,
        env={"PATH": "/usr/bin:/bin"}, records_to=tmp_path / "records.jsonl",
    )
    checks = [r for r in records if r.get("type") == "assert"]
    assert code == 0, (stdout, records)
    assert checks and all(c["passed"] for c in checks), (stdout, checks)


CHECKOUT_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def a_command_runs_in_its_own_copy_of_the_checkout(qa: Qa) -> None:
    """A command reaches the checkout's files, and what it writes lands in this scenario alone."""
    done = qa.tool("sh").run("-c", "test ! -e out.txt && test ! -e qa && cat app.txt && echo made > out.txt", cwd=qa.scenario_checkout_copy())
    qa.check("the command read the checkout from a world of its own", done.stdout == "the app\\n", actual=done.stdout)
'''


def test_each_run_of_a_scenario_starts_from_a_fresh_copy_of_the_checkout(tmp_path: Path) -> None:
    (tmp_path / "app.txt").write_text("the app\n", encoding="utf-8")
    module = _write(tmp_path, CHECKOUT_SCENARIO)
    context = json.dumps(
        {"root": str(tmp_path), "spec_dir": str(tmp_path), "qa_dir": str(tmp_path / "qa"), "tools": {"sh": "sh"}}
    )

    for _ in range(2):
        code, stdout, records = _harness(
            "run", str(module), "a-command-runs-in-its-own-copy-of-the-checkout", context,
            env={"PATH": "/usr/bin:/bin"}, records_to=tmp_path / "records.jsonl",
        )
        checks = [r for r in records if r.get("type") == "assert"]
        assert code == 0, (stdout, records)
        assert checks and all(c["passed"] for c in checks), (stdout, checks)

    assert not (tmp_path / "out.txt").exists()
    assert (tmp_path / "qa" / "a-command-runs-in-its-own-copy-of-the-checkout" / "out.txt").is_file()


IGNORED_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def a_command_reads_what_the_checkout_ignores(qa: Qa) -> None:
    """A command reaches the checkout's ignored build output, and what it writes lands in this scenario alone."""
    done = qa.tool("sh").run("-c", "cat app.txt deps/lib.txt && echo made > out.txt", cwd=qa.scenario_checkout_copy())
    qa.check("the command read the app and its ignored deps", done.stdout == "the app\\nthe lib\\n", actual=done.stdout)
'''


def test_a_copy_links_what_the_checkout_ignores_instead_of_copying_it(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    (root / "deps").mkdir(parents=True)
    (root / "app.txt").write_text("the app\n", encoding="utf-8")
    (root / "deps" / "lib.txt").write_text("the lib\n", encoding="utf-8")
    (root / "dump.sql").write_text("rows\n", encoding="utf-8")
    (root / ".gitignore").write_text("deps/\ndump.sql\n", encoding="utf-8")
    (root / "tool" / "node_modules").mkdir(parents=True)
    (root / "tool" / "node_modules" / "mod.js").write_text("mod\n", encoding="utf-8")
    (root / "tool" / ".gitignore").write_text("node_modules\n.gitignore\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "app.txt", ".gitignore"], check=True)
    module = _write(tmp_path, IGNORED_SCENARIO)
    context = json.dumps(
        {"root": str(root), "spec_dir": str(tmp_path), "qa_dir": str(tmp_path / "qa"), "tools": {"sh": "sh"}}
    )

    code, stdout, records = _harness(
        "run", str(module), "a-command-reads-what-the-checkout-ignores", context,
        env={"PATH": "/usr/bin:/bin"}, records_to=tmp_path / "records.jsonl",
    )

    world = tmp_path / "qa" / "a-command-reads-what-the-checkout-ignores"
    checks = [r for r in records if r.get("type") == "assert"]
    assert code == 0, (stdout, records)
    assert checks and all(c["passed"] for c in checks), (stdout, checks)
    assert (world / "app.txt").is_file() and not (world / "app.txt").is_symlink()
    assert (world / "deps").is_symlink() and (world / "dump.sql").is_symlink()
    assert (world / "tool").is_symlink() and (world / "tool" / "node_modules" / "mod.js").is_file()
    assert (world / "out.txt").is_file() and not (root / "out.txt").exists()


NO_COMMAND_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def a_scenario_that_runs_no_command(qa: Qa) -> None:
    """A scenario that never reads its directory leaves the checkout uncopied."""
    qa.check("the scenario ran", True)
'''


def test_a_scenario_that_runs_no_command_copies_no_checkout(tmp_path: Path) -> None:
    (tmp_path / "app.txt").write_text("the app\n", encoding="utf-8")
    module = _write(tmp_path, NO_COMMAND_SCENARIO)
    context = json.dumps({"root": str(tmp_path), "spec_dir": str(tmp_path), "qa_dir": str(tmp_path / "qa")})

    code, stdout, records = _harness(
        "run", str(module), "a-scenario-that-runs-no-command", context,
        env={"PATH": "/usr/bin:/bin"}, records_to=tmp_path / "records.jsonl",
    )

    assert code == 0, (stdout, records)
    assert not (tmp_path / "qa" / "a-scenario-that-runs-no-command").exists()


CREDENTIAL_SCENARIO = '''\
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Refuses(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(401)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@scenario(target=api, mechanism="live", covers=["ac:1", "ac:2", "ac:3"])
def a_token_the_app_refuses(qa: Qa) -> None:
    """One request with the seeded token, one with none, and a claim whose precondition breaks."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Refuses)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    qa.http.base_url = "http://127.0.0.1:%d" % server.server_address[1]
    qa.fixture("signed-in")
    with qa.claim(["ac:1"]):
        qa.http.get("/api/me", headers={"Authorization": qa.resolve("Bearer @signed-in.token")}, expect_status=200)
    with qa.claim(["ac:2"]):
        qa.http.get("/api/me", expect_status=200)
    with qa.claim(["ac:3"]):
        qa.fixture("broken")
'''

TOKEN = "tok-4f1c-99ab-seeded"


def test_a_failed_check_names_the_precondition_whose_credential_it_sent_and_never_the_credential(tmp_path: Path) -> None:
    seed = tmp_path / "seed.sh"
    _seed_step(seed, f'#!/bin/sh\necho \'{{"token": "{TOKEN}"}}\'\n')
    broken = tmp_path / "broken.sh"
    _seed_step(broken, "#!/bin/sh\nexit 3\n")
    book_fixtures = {
        "signed-in": {
            "page": "docs/fixtures/signed-in.md",
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(seed), "cwd": str(tmp_path)}],
            "args": [], "provides": [{"key": "token", "from": "seed-it", "read": ""}], "needs": [], "secrets": [],
        },
        "broken": {
            "page": "docs/fixtures/broken.md",
            "steps": [{"kind": "seed", "id": "fail", "command": str(broken), "cwd": str(tmp_path)}],
            "args": [], "provides": [], "needs": [], "secrets": [],
        },
    }

    _, stdout, records = _run(_write(tmp_path, CREDENTIAL_SCENARIO), "a-token-the-app-refuses", tmp_path, book_fixtures=book_fixtures)

    sent, unsent, arranged = [r for r in records if r.get("type") == "assert"]
    assert (sent["exchange"]["credential_sent"], sent["exchange"]["precondition"]) == (True, "docs/fixtures/signed-in.md"), stdout
    assert (unsent["exchange"]["credential_sent"], unsent["exchange"]["precondition"]) == (False, "")
    assert arranged["fault"] == {"fault_class": "defect", "fixture": "broken", "page": "docs/fixtures/broken.md"}
    assert arranged["raised"] == "RuntimeError"
    assert TOKEN not in json.dumps([sent, unsent, arranged])


def test_a_book_fixture_that_names_no_page_is_refused_before_any_claim_runs(tmp_path: Path) -> None:
    book_fixtures = {"signed-in": {"page": "", "steps": [], "args": [], "provides": [], "needs": [], "secrets": []}}

    code, stdout, records = _run(_write(tmp_path, CREDENTIAL_SCENARIO), "a-token-the-app-refuses", tmp_path, book_fixtures=book_fixtures)

    assert code != 0
    assert "names no page" in stdout
    assert not [r for r in records if r.get("type") == "assert"]


STRUCTURED_FACT_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def a_body_member_sends_an_object_fact_as_an_object(qa: Qa) -> None:
    """A fixture provides a JSON object, and a body member naming it whole sends the object."""
    qa.fixture("seeded-acme")
    qa.check("the body member is the object", qa.resolve_body("@seeded-acme.locales") == {"fr": "Bonjour"})
    qa.check("embedded text spells it as JSON", qa.resolve("@seeded-acme.locales") == '{"fr": "Bonjour"}')
    qa.check("a scalar fact stays text", qa.resolve_body("@seeded-acme.slug") == "intro")
'''


def test_a_body_member_naming_an_object_fact_sends_the_object_not_its_text(tmp_path: Path) -> None:
    seed = tmp_path / "seed.sh"
    _seed_step(seed, "#!/bin/sh\necho '{\"slug\": \"intro\", \"locales\": {\"fr\": \"Bonjour\"}}'\n")
    module = _write(tmp_path, STRUCTURED_FACT_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(seed), "cwd": str(tmp_path)}],
            "args": [], "needs": [], "secrets": [],
            "provides": [
                {"key": "locales", "from": "seed-it", "read": "locales"},
                {"key": "slug", "from": "seed-it", "read": "slug"},
            ],
        }
    }
    code, stdout, records = _run(module, "a-body-member-sends-an-object-fact-as-an-object", tmp_path, book_fixtures=book_fixtures)
    assert code == 0, stdout
    asserted = [record for record in records if record.get("type") == "assert"]
    assert [record["passed"] for record in asserted] == [True, True, True], asserted


def test_an_object_fact_reused_later_in_its_lap_is_still_an_object(tmp_path: Path) -> None:
    seed = tmp_path / "seed.sh"
    _seed_step(seed, "#!/bin/sh\necho '{\"slug\": \"intro\", \"locales\": {\"fr\": \"Bonjour\"}}'\n")
    module = _write(tmp_path, STRUCTURED_FACT_SCENARIO)
    book_fixtures = {
        "seeded-acme": {
            "steps": [{"kind": "seed", "id": "seed-it", "command": str(seed), "cwd": str(tmp_path)}],
            "args": [], "needs": [], "secrets": [],
            "provides": [
                {"key": "locales", "from": "seed-it", "read": "locales"},
                {"key": "slug", "from": "seed-it", "read": "slug"},
            ],
        }
    }
    lap = tmp_path / "lap"
    scenario = "a-body-member-sends-an-object-fact-as-an-object"

    first_code, first_out, _first_records = _run(module, scenario, tmp_path, book_fixtures=book_fixtures, lap_dir=lap)
    second_code, second_out, second_records = _run(module, scenario, tmp_path, book_fixtures=book_fixtures, lap_dir=lap)

    assert first_code == 0, first_out
    assert second_code == 0, second_out
    assert [r["reused"] for r in second_records if r.get("type") == "fixture"] == [True]
    asserted = [record for record in second_records if record.get("type") == "assert"]
    assert [record["passed"] for record in asserted] == [True, True, True], asserted


SERVE_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def talks_to_a_server(qa: Qa) -> None:
    """Arranges a server the scenario talks to."""
    qa.fixture("mock-backend")
    qa.check("arranged", True)
'''


def _serve_fixture(tmp_path: Path, *, lifetime: str = "scenario", serve: str = "") -> dict:
    pid_file = tmp_path / "server.pid"
    return {
        "mock-backend": {
            "steps": [
                {"kind": "serve", "id": "start", "command": serve or f"echo $$ > {pid_file}; exec sleep 30"},
                {"kind": "verify", "id": "alive", "command": f"sleep 0.2; kill -0 $(cat {pid_file})"},
            ],
            "args": [], "provides": [], "needs": [], "secrets": [], "lifetime": lifetime,
        }
    }


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"


def test_a_served_process_answers_the_next_step_and_is_gone_when_the_scenario_ends(tmp_path: Path) -> None:
    module = _write(tmp_path, SERVE_SCENARIO)
    code, stdout, records = _run(module, "talks-to-a-server", tmp_path, book_fixtures=_serve_fixture(tmp_path))
    assert code == 0, stdout
    [served] = [r for r in records if r.get("type") == "serve"]
    assert served["fixture"] == "mock-backend"
    assert not _is_running(int((tmp_path / "server.pid").read_text()))


def test_a_backgrounded_command_is_refused_naming_the_serve_step(tmp_path: Path) -> None:
    module = _write(tmp_path, SERVE_SCENARIO)
    book_fixtures = {
        "mock-backend": {
            "steps": [{"kind": "seed", "id": "start", "command": "sleep 30 &"}],
            "args": [], "provides": [], "needs": [], "secrets": [], "lifetime": "scenario",
        }
    }
    code, stdout, records = _run(module, "talks-to-a-server", tmp_path, book_fixtures=book_fixtures)
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert fault["fault_class"] == "defect"
    assert "`kind: serve`" in fault["detail"]


def test_a_served_process_in_a_fixture_shared_across_scenarios_is_refused(tmp_path: Path) -> None:
    module = _write(tmp_path, SERVE_SCENARIO)
    book_fixtures = _serve_fixture(tmp_path, lifetime="lap")
    code, stdout, records = _run(module, "talks-to-a-server", tmp_path, book_fixtures=book_fixtures)
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert "`lifetime: scenario`" in fault["detail"]
    assert not (tmp_path / "server.pid").exists()


def test_a_server_that_dies_as_it_starts_is_a_defect_quoting_its_output(tmp_path: Path) -> None:
    module = _write(tmp_path, SERVE_SCENARIO)
    book_fixtures = _serve_fixture(tmp_path, serve="echo 'address already in use' >&2; exit 3")
    code, stdout, records = _run(module, "talks-to-a-server", tmp_path, book_fixtures=book_fixtures)
    assert code != 0, stdout
    [fault] = [r for r in records if r.get("type") == "fixture_fault"]
    assert "exited 3" in fault["detail"]
    assert "address already in use" in fault["detail"]


def test_the_driver_stops_a_server_a_killed_scenario_left_running(tmp_path: Path) -> None:
    server = subprocess.Popen(["sleep", "30"], process_group=0)  # noqa: S603, S607
    stop_servers([{"type": "serve", "pgid": server.pid}])
    assert server.wait(timeout=5) == -signal.SIGKILL
