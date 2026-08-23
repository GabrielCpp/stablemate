"""`ostler.qa.runbook` — the book's ops nodes read as the manifest `ensure_stack` takes.

These tests are about the *derivation*, not the lifecycle: nothing here boots a process.
`test_qa_stack.py` owns adoption, staleness and boot windows, and this module owns the one
question that used to have no answer at all — what the book says the stack is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ostler import model
from ostler.qa import runbook as rb

from conftest import write


def make_runbook(root: Path, body: str, *, name: str = "qa-stack") -> None:
    write(root / "docs" / "features" / "app" / "ops" / f"{name}.md", body)


RUNBOOK = """---
type: runbook
title: QA stack
---

# QA stack

- driver: web
- entry-url: http://localhost:18084
- health-path: /healthz
- identity: `"status": "ok"`
- reuse: never
- boot-timeout: 120
- stop: docker compose -f compose.yml down -v
- working-directory: app

## Steps

### build

- kind: prepare
- run: docker compose build

### serve

- kind: service
- run: docker compose up -d --wait
- health: curl -fsS http://localhost:18084/healthz

### seed-fixtures

- kind: seed
- run: ./scripts/seed.sh

### smoke

- kind: run
- run: ./scripts/smoke.sh
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, RUNBOOK)
    return tmp_path


def test_load_stack_folds_steps_into_phases(repo: Path) -> None:
    manifest = rb.load_stack(repo)
    assert manifest["launch"] == "docker compose up -d --wait"
    assert [s["run"] for s in manifest["prepare"]] == ["docker compose build"]
    assert [s["run"] for s in manifest["seed"]] == ["./scripts/seed.sh"]
    # The `service` step's `health:` becomes a health gate; the `run` step is not a phase.
    assert [s["run"] for s in manifest["health"]] == [
        "curl -fsS http://localhost:18084/healthz"]


def test_scalars_are_spelled_the_way_ensure_stack_reads_them(repo: Path) -> None:
    manifest = rb.load_stack(repo)
    assert manifest["entry_url"] == "http://localhost:18084"
    assert manifest["health_path"] == "/healthz"
    assert manifest["reuse"] == "never"
    assert manifest["boot_timeout"] == "120"
    assert manifest["identity"] == '"status": "ok"'


def test_working_directory_comes_back_absolute(repo: Path) -> None:
    # Authored repo-relative because that is what an author means; nothing downstream
    # resolves it, so an unresolved `app` would launch the stack from the engine's cwd.
    manifest = rb.load_stack(repo)
    assert manifest["app_cwd"] == str((repo / "app").resolve())
    assert manifest["prepare"][0]["working-directory"] == str((repo / "app").resolve())
    assert manifest["repo_root"] == str(repo.resolve())


def test_every_step_is_the_mapping_form(repo: Path) -> None:
    # A bare string gets `_run_step`'s *boot* timeout and a mapping gets STEP_TIMEOUT_S, so
    # one shape is what keeps `- make build` from meaning something else than `- run: …`.
    manifest = rb.load_stack(repo)
    for phase in ("prepare", "seed", "health"):
        assert all(isinstance(step, dict) and "run" in step for step in manifest[phase])


def test_source_names_the_node_the_recipe_came_from(repo: Path) -> None:
    manifest = rb.load_stack(repo)
    assert manifest["source"] == "docs/features/app/ops/qa-stack.md"


def test_step_timeout_and_optional_and_env(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, """---
type: runbook
---

# QA stack

- driver: web

## Steps

### warm

- kind: prepare
- run: ./warm.sh
- timeout: 45
- optional: true
- env:
  - PORT=8080
  - MODE=test

### serve

- kind: service
- run: ./serve.sh
- health: curl -fsS localhost:8080
""")
    step = rb.load_stack(tmp_path)["prepare"][0]
    assert step["timeout"] == "45"
    # Best-effort is carried in the recipe: `ensure_stack` has no soft mode to carry it in.
    assert step["run"] == "export PORT=8080; export MODE=test; ./warm.sh || true"


def test_secrets_are_name_to_recipe(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, """---
type: runbook
---

# QA stack

- driver: web
- secrets:
  - QA_TOKEN: ./scripts/mint-token.sh
  - QA_ADMIN_TOKEN: ./scripts/mint-token.sh --admin

## Steps

### serve

- kind: service
- run: ./serve.sh
- health: curl -fsS localhost:8080
""")
    assert rb.load_stack(tmp_path)["secrets"] == {
        "QA_TOKEN": "./scripts/mint-token.sh",
        "QA_ADMIN_TOKEN": "./scripts/mint-token.sh --admin",
    }


def test_empty_when_the_book_declares_nothing(tmp_path: Path) -> None:
    # The only honest "nothing to bring up" left. Everything else used to land here too.
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "app" / "home.md",
          "---\ntype: feature\nslug: home\n---\n\n# Home\n\nprose\n")
    assert rb.load_stack(tmp_path) == {}


def test_falls_back_to_the_walkthrough_server(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "api" / "server.md", """---
type: server
title: API
---

# API

- launch: npm start
- entry-url: http://localhost:3000/
- health-path: /health
- working-directory: api
- walkthrough: true
""")
    manifest = rb.load_stack(tmp_path)
    assert manifest["launch"] == "npm start"
    assert manifest["entry_url"] == "http://localhost:3000"  # trailing slash trimmed
    assert manifest["app_cwd"] == str((tmp_path / "api").resolve())


def test_two_marked_servers_resolve_to_nothing(tmp_path: Path) -> None:
    # A walk against the wrong service is worse than a walk that says it has nowhere to go.
    (tmp_path / ".git").mkdir()
    for slug in ("one", "two"):
        write(tmp_path / "docs" / "features" / "api" / f"{slug}.md",
              f"---\ntype: server\ntitle: {slug}\n---\n\n# {slug}\n\n"
              "- launch: npm start\n- entry-url: http://localhost:3000\n- walkthrough: true\n")
    assert rb.load_stack(tmp_path) == {}


def test_named_runbook_selects_and_a_wrong_name_does_not_guess(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    for name, port in (("qa-stack", 1111), ("release", 2222)):
        make_runbook(tmp_path, f"---\ntype: runbook\n---\n\n# {name}\n\n"
                     f"- driver: web\n- entry-url: http://localhost:{port}\n\n"
                     "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
                     "- health: curl -fsS localhost\n", name=name)
    assert rb.load_stack(tmp_path, name="release")["entry_url"] == "http://localhost:2222"
    # Several runbooks and no name is ambiguous, and guessing brings the wrong stack up.
    assert rb.load_stack(tmp_path) == {}
    assert rb.load_stack(tmp_path, name="nope") == {}


def test_steps_belong_to_their_own_runbook(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    for name, cmd in (("qa-stack", "./qa.sh"), ("release", "./release.sh")):
        make_runbook(tmp_path, f"---\ntype: runbook\n---\n\n# {name}\n\n- driver: web\n\n"
                     f"## Steps\n\n### serve\n\n- kind: service\n- run: {cmd}\n"
                     "- health: curl -fsS localhost\n", name=name)
    graph = model.load(tmp_path)
    chosen = rb.select_runbook(graph, "release")
    assert chosen is not None
    assert [s.meta["run"] for s in rb.steps_of(graph, chosen)] == ["./release.sh"]


def test_cmd_stack_up_reports_none_without_booting_anything(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs").mkdir()
    outcome = rb.cmd_stack_up(tmp_path)
    assert outcome.ok and outcome.status == "none"
    assert outcome.data["manifest"] == {}


def test_cmd_stack_down_without_a_stop_recipe_leaves_it_serving(tmp_path: Path) -> None:
    # Policy, not failure: a shared emulator is cheaper left serving than rebuilt.
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n\n"
                 "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
                 "- health: curl -fsS localhost\n")
    outcome = rb.cmd_stack_down(tmp_path)
    assert outcome.data["torn_down"] == "skipped"


# --- the doctor half: the book saying nothing, or saying something unrunnable ---


def codes(root: Path) -> list[str]:
    from ostler import doctor
    return [fd.code for fd in doctor.run(model.load(root)).findings]


def test_doctor_warns_once_when_no_stack_is_declared(tmp_path: Path) -> None:
    # The finding that moves the greenfield hole from turn 61 to author time.
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "app" / "home.md",
          "---\ntype: feature\nslug: home\n---\n\n# Home\n\nprose\n")
    assert codes(tmp_path).count("runbook-missing") == 1


def test_doctor_stays_quiet_when_a_walkthrough_server_declares_it(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "api" / "server.md",
          "---\ntype: server\ntitle: API\n---\n\n# API\n\n- launch: npm start\n"
          "- entry-url: http://localhost:3000\n- walkthrough: true\n")
    assert "runbook-missing" not in codes(tmp_path)


def test_doctor_rejects_a_kind_and_a_reuse_outside_the_vocabulary(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- reuse: sometimes\n- entry-url: http://localhost:1\n\n## Steps\n\n"
                 "### serve\n\n- kind: service\n- run: ./serve.sh\n\n"
                 "### odd\n\n- kind: incantation\n- run: ./odd.sh\n")
    found = codes(tmp_path)
    assert "runbook-bad-reuse" in found
    assert "runbook-bad-kind" in found


def test_doctor_reports_a_runbook_that_declares_a_launch_but_starts_nothing(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- entry-url: http://localhost:1\n\n## Steps\n\n"
                 "### build\n\n- kind: prepare\n- run: make\n")
    assert "runbook-incomplete" in codes(tmp_path)


def test_doctor_holds_only_stack_runbooks_to_the_stack_shape(tmp_path: Path) -> None:
    """A runbook that starts nothing is a procedure, not a broken stack.

    `runbook` is the general ops type — "preview the plan", "rotate the keys", "restore last
    night's dump". None of those has a system to bring up, and demanding a `kind: service`
    step of them would make the doctor red for writing ops documentation correctly. What the
    book *does* still get told is that nothing here declares a stack.
    """
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# Rotate the keys\n\n- driver: cli\n"
                 "\n## Steps\n\n### rotate\n\n- kind: run\n- run: ./rotate.sh\n")
    found = codes(tmp_path)
    assert "runbook-incomplete" not in found
    assert found.count("runbook-missing") == 1


def test_doctor_reports_a_runbook_nothing_proves_the_readiness_of(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n\n## Steps\n\n"
                 "### serve\n\n- kind: service\n- run: ./serve.sh\n")
    assert "runbook-incomplete" in codes(tmp_path)


def test_doctor_reports_two_service_steps(tmp_path: Path) -> None:
    # The reader takes the first and keeps going, so which one launched is otherwise luck.
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- entry-url: http://localhost:1\n\n## Steps\n\n"
                 "### api\n\n- kind: service\n- run: ./api.sh\n\n"
                 "### web\n\n- kind: service\n- run: ./web.sh\n")
    assert "runbook-multi-service" in codes(tmp_path)


def test_doctor_refuses_a_local_only_environment_pointing_off_the_machine(
        tmp_path: Path) -> None:
    # Honouring it is cheap here and impossible later: by the time the recipe runs it is
    # already talking to whatever it was pointed at. The evidence is the service *host* —
    # a selector is free prose, so reading intent out of it would libel `BIND=127.0.0.1`.
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "app" / "ops" / "staging.md",
          "---\ntype: environment\ntitle: staging\n---\n\n# staging\n\n"
          "- selector: staging\n- services:\n  - api: `https://api.example.com`\n"
          "- local-only: true\n")
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- environment: [staging](staging.md)\n- entry-url: http://localhost:1\n\n"
                 "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n")
    assert "runbook-local-only" in codes(tmp_path)


def test_a_loopback_service_is_not_a_local_only_violation(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "app" / "ops" / "local.md",
          "---\ntype: environment\ntitle: local\n---\n\n# local\n\n"
          "- selector: `APP_BIND=127.0.0.1`\n- services:\n  - api: `http://127.0.0.1:8787`\n"
          "- local-only: true\n")
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- environment: [local](local.md)\n- entry-url: http://localhost:1\n\n"
                 "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n")
    assert "runbook-local-only" not in codes(tmp_path)
