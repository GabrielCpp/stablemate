"""`Qa.fixture()`'s book-fixture tier: dispatch order, env-not-shell-text, secrets-as-names,
fault classification per Q38, needs memoization, and `@node.key`/`$name` namespacing.

Run as a real subprocess the way `test_qa_harness.py` does — never imported into the test
process, since the harness keeps a module-level registry that a second `plan()`/`scenario()`
call in the same interpreter would corrupt.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def _with_resolved_timeouts(book_fixtures: dict) -> dict:
    """Fill in the `timeout` every step carries once `book_fixtures.resolved()` has run.

    These fixtures are hand-built test doubles, not `book_fixtures.resolved()` output, so
    they skip the ostler-side normalization step (`stack.boot_timeout`) that guarantees a
    real step dict always carries a resolved float — the harness itself no longer defaults
    or parses one. A default here stands in for that normalization, not a harness default.
    """
    for spec in book_fixtures.values():
        for step in spec.get("steps", []):
            if not step.get("missing_run") and "timeout" not in step:
                step["timeout"] = 5.0
    return book_fixtures


def _run(
    module: Path, scenario_id: str, tmp_path: Path, *, book_fixtures: dict, env: dict[str, str] | None = None,
) -> tuple[int, str, list[dict]]:
    context = json.dumps(
        {
            "root": str(tmp_path),
            "spec_dir": str(tmp_path),
            "qa_dir": str(tmp_path / "qa"),
            "book_fixtures": _with_resolved_timeouts(book_fixtures),
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
    fixture_records = [r for r in records if r.get("kind") == "fixture"]
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
    # The whole value — semicolon and all — landed as one environment value, never parsed by
    # a shell: if it had been shell text, "rm -rf" would have run as a second command instead
    # of being written verbatim into $id.
    assert out.read_text(encoding="utf-8") == "needle; rm -rf /tmp/should-not-run"


SECRET_SCENARIO = '''\
@scenario(target=api, mechanism="live", covers=["ac:1"])
def needs_a_secret(qa: Qa) -> None:
    """Declares a secret the harness's own environment does not have."""
    qa.fixture("seeded-acme")
    qa.check("unreachable", True)
'''


def test_a_missing_secret_is_an_environment_fault(tmp_path: Path) -> None:
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
    assert fault["fault_class"] == "environment"
    assert fault["fixture"] == "seeded-acme"
    dumped = "\n".join(json.dumps(r) for r in records)
    assert "MISSING_API_TOKEN" in dumped
    # The name is expected — a value never is, because none exists to leak.


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


def test_a_missing_command_is_a_defect_whose_detail_names_it(tmp_path: Path) -> None:
    """`bash -c` exits 126/127 for a name it never found — identical, from the exit code
    alone, to a typo in the recipe. That is exactly why it is a defect, not an environment
    fault: the fault detail still has to flag the 126/127 case so triage can tell "this tool
    was never installed" apart from a generic non-zero exit."""
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
            # Wrong key — seeded-acme provides "id", not "no_such_key".
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
    """`working-directory: scenario:` and `qa.tool(...).run(..., cwd=qa.scenario_id)` must
    resolve to the exact same directory, not merely two directories under `qa.dir`."""
    qa.fixture("seeded-acme")
    fixture_cwd = qa.resolve("@seeded-acme.fixture_cwd")
    tool = qa.tool("sh")
    done = tool.run("-c", "pwd", cwd=qa.scenario_id)
    qa.check(
        "fixture cwd-frame and qa.tool cwd=qa.scenario_id are the same directory",
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
            "book_fixtures": _with_resolved_timeouts(book_fixtures),
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
