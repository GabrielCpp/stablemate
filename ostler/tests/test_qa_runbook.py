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


def test_a_check_expression_on_run_or_health_is_not_shelled(tmp_path: Path) -> None:
    # The doctor's `check-expression-as-command` is the loud finding an author sees before
    # bring-up ever runs; this is only the backstop that keeps a book that skipped the doctor
    # from handing bash a check call instead of a command. Both bullets are treated as absent,
    # the same as a `step` that declared no `run:`/`health:` at all.
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, """---
type: runbook
---

# QA stack

- driver: web
- entry-url: http://localhost:18084

## Steps

### serve

- kind: service
- run: http_status(200, path="/healthz")
- health: http_status(200, path="/healthz")
""")
    manifest = rb.load_stack(tmp_path)
    assert manifest.get("launch") is None
    assert manifest.get("health", []) == []


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
    assert manifest["launch_cwd"] == str((repo / "app").resolve())


def test_the_launch_runs_in_the_service_step_s_own_directory(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, """---
type: runbook
---

# QA stack

- driver: web
- working-directory: `.`

## Steps

### load

- kind: prepare
- run: `make testdb-load`
- working-directory: `api`

### serve

- kind: service
- run: `make run`
- working-directory: `report`
- health: `curl -sf http://localhost:8081/health`
""")
    manifest = rb.load_stack(tmp_path)
    assert manifest["app_cwd"] == str(tmp_path.resolve())
    assert manifest["launch_cwd"] == str((tmp_path / "report").resolve())
    assert manifest["prepare"][0]["working-directory"] == str((tmp_path / "api").resolve())
    assert manifest["health"][0]["working-directory"] == str((tmp_path / "report").resolve())


def test_scenario_frame_token_is_carried_as_a_marker_not_a_resolved_path(tmp_path: Path) -> None:
    """No scenario directory exists at manifest-build time, so `_step_command` must not
    invent a fake absolute path for the token — it hands the frame on as a marker for
    the harness to resolve at run time."""
    node = model.UINode(
        type="step", kind="section", id="fixtures/f.md#seed-it", path=tmp_path / "f.md",
        meta={"run": "./seed.sh", "working-directory": "scenario:"},
    )
    step = rb.step_command(node, tmp_path, ".")
    assert step is not None
    assert step["cwd-frame"] == "scenario"
    assert "working-directory" not in step


def test_a_stated_path_still_resolves_checkout_relative(tmp_path: Path) -> None:
    node = model.UINode(
        type="step", kind="section", id="ops/qa-stack.md#build", path=tmp_path / "qa-stack.md",
        meta={"run": "make build", "working-directory": "services/api"},
    )
    step = rb.step_command(node, tmp_path, ".")
    assert step is not None
    assert step["working-directory"] == str((tmp_path / "services" / "api").resolve())
    assert "cwd-frame" not in step


def test_an_absent_working_directory_still_resolves_to_the_default_cwd(tmp_path: Path) -> None:
    node = model.UINode(
        type="step", kind="section", id="ops/qa-stack.md#build", path=tmp_path / "qa-stack.md",
        meta={"run": "make build"},
    )
    step = rb.step_command(node, tmp_path, "app")
    assert step is not None
    assert step["working-directory"] == str((tmp_path / "app").resolve())
    assert "cwd-frame" not in step


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


def test_prose_env_child_is_not_exported(tmp_path: Path) -> None:
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
- env:
  - fixed in [Local](local.md) `backing:` — `DB_HOST=db`, `DB_PORT=3306`
  - PORT=8080
  - `MODE=test`

### serve

- kind: service
- run: ./serve.sh
- health: curl -fsS localhost:8080
""")
    step = rb.load_stack(tmp_path)["prepare"][0]
    assert step["run"] == "export PORT=8080; export MODE=test; ./warm.sh"


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


def _two_stacks(root: Path, *, environments: tuple[str, str]) -> None:
    """Two stack runbooks under `app/ops`, each binding to the named environment file."""
    for env in set(environments):
        write(root / "docs" / "features" / "app" / "ops" / f"{env}.md",
              f"---\ntype: environment\n---\n\n# {env}\n\n- local-only: true\n")
    for name, port, env in (("api-stack", 1111, environments[0]),
                            ("web-stack", 2222, environments[1])):
        make_runbook(root, f"---\ntype: runbook\n---\n\n# {name}\n\n"
                     f"- driver: web\n- entry-url: http://localhost:{port}\n"
                     f"- environment: [{env}]({env}.md)\n\n"
                     "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
                     "- health: curl -fsS localhost\n", name=name)


def test_stack_runbooks_sharing_an_environment_come_up_together(tmp_path: Path) -> None:
    # The unit is the environment, not the runbook: a journey through a web surface that
    # calls an API needs both serving, and what makes them one system is that the author
    # bound both to one `environment:` node.
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "local"))
    graph = model.load(tmp_path)
    selection = rb.select_stack(graph)
    assert selection.reason == ""
    assert [n.path.stem for n in selection.runbooks] == ["api-stack", "web-stack"]
    assert selection.environment.endswith("local.md")
    manifests, _ = rb.load_stacks(graph)
    assert [m["entry_url"] for m in manifests] == ["http://localhost:1111",
                                                   "http://localhost:2222"]


def test_an_environment_link_is_resolved_not_compared_as_text(tmp_path: Path) -> None:
    # globex's two runbooks sit in different service directories and spell the same
    # environment `local.md` and `../../api-service/ops/local.md`. A string compare says
    # those are two systems.
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "api" / "ops" / "local.md",
          "---\ntype: environment\n---\n\n# local\n\n- local-only: true\n")
    for svc, port, href in (("api", 1111, "local.md"),
                            ("web", 2222, "../../api/ops/local.md")):
        write(tmp_path / "docs" / "features" / svc / "ops" / f"{svc}-stack.md",
              f"---\ntype: runbook\n---\n\n# {svc}\n\n- driver: web\n"
              f"- entry-url: http://localhost:{port}\n- environment: [local]({href})\n\n"
              "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
              "- health: curl -fsS localhost\n")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert len(selection.runbooks) == 2


def test_several_environments_and_no_name_is_a_refusal_not_an_absence(tmp_path: Path) -> None:
    # Opposite findings want opposite fixes: "write a runbook" is the wrong instruction to
    # hand someone whose book declares two.
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "staging"))
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == "ambiguous"
    assert len(selection.candidates) == 2
    outcome = rb.cmd_stack_up(tmp_path)
    assert not outcome.ok and outcome.status == "ambiguous"
    assert "--runbook" in outcome.message
    assert rb.cmd_stack_down(tmp_path).status == "ambiguous"


def test_a_refusal_does_not_fall_back_to_the_walkthrough_server(tmp_path: Path) -> None:
    """`load_stack` used to read a refusal as an absence and fall through to whichever
    server was marked `walkthrough: true`, bringing up one service and reporting success
    against six surfaces it never served.
    """
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "staging"))
    write(tmp_path / "docs" / "features" / "other" / "server.md", """---
type: server
title: Other
---

# Other

- launch: npm start
- entry-url: http://localhost:9000/
- walkthrough: true
""")
    assert rb.load_stack(tmp_path) == {}


def test_a_single_environment_with_two_runbooks_has_no_single_manifest(tmp_path: Path) -> None:
    """globex's shape: two runbooks, one environment. `select_stack` chooses both, but
    `load_stack` returns one manifest, so it refuses rather than picking one at random.
    """
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "local"))
    assert rb.load_stack(tmp_path) == {}
    manifests, selection = rb.load_stacks(model.load(tmp_path))
    assert selection.reason == ""
    assert len(manifests) == 2


def test_a_name_that_matches_nothing_is_distinct_from_a_bookless_book(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "local"))
    outcome = rb.cmd_stack_up(tmp_path, name="nope")
    assert not outcome.ok and outcome.status == "unknown-runbook"


def _local_stack_runbook(root: Path, name: str, port: int, env: str) -> None:
    """One stack runbook under `app/ops`, bound to the named environment file."""
    make_runbook(root, f"---\ntype: runbook\n---\n\n# {name}\n\n"
                 f"- driver: web\n- entry-url: http://localhost:{port}\n"
                 f"- environment: [{env}]({env}.md)\n\n"
                 "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
                 "- health: curl -fsS localhost\n", name=name)


def _environment_file(root: Path, env: str, *, local_only: bool | None,
                      walkthrough: bool = False) -> None:
    """One `environment` node under `app/ops`, its bullets set explicitly.

    `local_only=None` writes no `local-only` bullet at all, which is a different book from
    one declaring `false` — an absent declaration is not a declaration of absence.
    """
    bullets = ""
    if local_only is not None:
        bullets += f"- local-only: {'true' if local_only else 'false'}\n"
    if walkthrough:
        bullets += "- walkthrough: true\n"
    write(root / "docs" / "features" / "app" / "ops" / f"{env}.md",
          f"---\ntype: environment\n---\n\n# {env}\n\n{bullets}")


def test_the_local_only_environment_resolves_an_otherwise_ambiguous_book(
        tmp_path: Path) -> None:
    """Two stack runbooks bind to `local`, one to `staging`, and only `local` is declared
    `local-only: true`. That declaration is the book's own answer to which system QA boots,
    so it resolves the same book that would otherwise be a refusal — and every runbook
    bound to `local`, not just one of them, comes up with it.
    """
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=True)
    _environment_file(tmp_path, "staging", local_only=False)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "web-stack", 2222, "local")
    _local_stack_runbook(tmp_path, "worker-stack", 3333, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")
    assert len(selection.runbooks) == 2
    assert {n.path.stem for n in selection.runbooks} == {"api-stack", "web-stack"}


def test_two_local_only_environments_stay_ambiguous(tmp_path: Path) -> None:
    """The control case: both candidate environments declaring `local-only: true` must not
    collapse the ambiguity, or the filter would just be picking one of them rather than
    reading a declaration the author actually narrowed to one.
    """
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=True)
    _environment_file(tmp_path, "staging", local_only=True)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "web-stack", 2222, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == "ambiguous"


def test_neither_local_only_environment_stays_ambiguous(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=False)
    _environment_file(tmp_path, "staging", local_only=False)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "web-stack", 2222, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == "ambiguous"


def test_a_single_local_only_environment_still_early_returns(tmp_path: Path) -> None:
    """A book with one environment never reaches the `local-only` filter at all — it
    resolves earlier, on every stack runbook sharing that one environment.
    """
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=True)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "web-stack", 2222, "local")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")
    assert len(selection.runbooks) == 2


def test_walkthrough_resolves_between_two_local_only_environments(tmp_path: Path) -> None:
    """The payoff: two local-only docker-compose profiles are both eligible after the
    `local-only` filter, and only `walkthrough: true` on one of them says which a QA
    bring-up boots — resolving to it with every stack runbook bound to it, not just one.
    """
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=True, walkthrough=True)
    _environment_file(tmp_path, "staging", local_only=True)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "web-stack", 2222, "local")
    _local_stack_runbook(tmp_path, "worker-stack", 3333, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")
    assert {n.path.stem for n in selection.runbooks} == {"api-stack", "web-stack"}


def test_two_local_only_environments_neither_marked_stay_ambiguous(tmp_path: Path) -> None:
    """The control: its passing is the result. Without `walkthrough` marking either
    environment, two `local-only` candidates must still refuse — proving the new marker
    is what resolves the payoff case above, not the `local-only` filter collapsing on its
    own.
    """
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=True)
    _environment_file(tmp_path, "staging", local_only=True)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "worker-stack", 3333, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == "ambiguous"


def test_local_only_outranks_a_walkthrough_mark_on_a_non_local_environment(
        tmp_path: Path) -> None:
    """The safety ordering: `staging` is marked `walkthrough: true` but is not `local-only`,
    while `local` is `local-only: true` and unmarked. The bring-up must resolve to `local`
    — never to `staging` — or a book could make a QA run boot a non-local system just by
    marking it. This is the test that fails if the filter and the selector are ever
    reordered.
    """
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=True)
    _environment_file(tmp_path, "staging", local_only=False, walkthrough=True)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "worker-stack", 3333, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")
    assert {n.path.stem for n in selection.runbooks} == {"api-stack"}


def test_two_walkthrough_marks_among_local_only_candidates_stay_ambiguous(
        tmp_path: Path) -> None:
    """Marking more than one eligible environment `walkthrough: true` is as unresolved as
    marking none — the book has to narrow it to exactly one, same as `local-only` itself.
    """
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=True, walkthrough=True)
    _environment_file(tmp_path, "staging", local_only=True, walkthrough=True)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "worker-stack", 3333, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == "ambiguous"


def test_a_walkthrough_mark_settles_a_book_that_declares_no_local_only(
        tmp_path: Path) -> None:
    """Neither environment says anything about being local, so the safety filter has
    nothing to keep and every candidate stays eligible. The mark is then the only thing
    the book says about which one QA boots, and it settles it — an absent `local-only` is
    silence, not a refusal, and silence must not cost the book its own answer.
    """
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=None, walkthrough=True)
    _environment_file(tmp_path, "staging", local_only=None)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "worker-stack", 3333, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")


def test_a_walkthrough_mark_cannot_select_an_environment_declared_non_local(
        tmp_path: Path) -> None:
    """The paired case, and the one with teeth: no candidate declares itself local, so the
    filter again keeps everything — but the marked environment declares `local-only: false`
    outright. A preference among systems cannot overturn a stated fact about one, so the
    mark selects nothing and the refusal stands. Without this the marker would be a way to
    talk a QA bring-up into booting a production environment the book had already refused.
    """
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "prod", local_only=False, walkthrough=True)
    _environment_file(tmp_path, "staging", local_only=None)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "prod")
    _local_stack_runbook(tmp_path, "worker-stack", 3333, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == "ambiguous"


def _environment(root: Path, surface: str, name: str, *, local_only: bool = True) -> None:
    write(root / "docs" / "features" / surface / "ops" / f"{name}.md",
          f"---\ntype: environment\n---\n\n# {name}\n\n"
          f"- local-only: {'true' if local_only else 'false'}\n")


def _stack_runbook(root: Path, surface: str, name: str, port: int, env_href: str) -> None:
    write(root / "docs" / "features" / surface / "ops" / f"{name}.md",
          f"---\ntype: runbook\n---\n\n# {name}\n\n"
          f"- driver: web\n- entry-url: http://localhost:{port}\n"
          f"- environment: [env]({env_href})\n\n"
          "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
          "- health: curl -fsS localhost\n")


def test_near_narrows_an_ambiguous_selection_to_its_shared_environment(tmp_path: Path) -> None:
    """web-app and api-service bind to different environments; mobile-app binds to the same
    environment as web-app despite sitting in a third surface. Naming no runbook, a spec
    under web-app should pull in both runbooks sharing web-app's environment — including
    the one that lives in mobile-app — and leave api-service out.
    """
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, "web-app", "local")
    _environment(tmp_path, "api-service", "staging")
    _stack_runbook(tmp_path, "web-app", "web-stack", 1111, "local.md")
    _stack_runbook(tmp_path, "api-service", "api-stack", 2222, "staging.md")
    _stack_runbook(tmp_path, "mobile-app", "mobile-stack", 3333, "../../web-app/ops/local.md")
    graph = model.load(tmp_path)

    baseline = rb.select_stack(graph)
    assert baseline.reason == "ambiguous"
    assert len(baseline.candidates) == 3

    near = tmp_path / "docs" / "features" / "web-app" / "specs" / "home.md"
    selection = rb.select_stack(graph, near=near)
    assert selection.reason == ""
    assert {n.path.stem for n in selection.runbooks} == {"web-stack", "mobile-stack"}
    assert selection.environment.endswith("local.md")


def test_near_stays_ambiguous_when_its_surface_spans_two_environments(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, "web-app", "local")
    _environment(tmp_path, "web-app", "staging")
    _stack_runbook(tmp_path, "web-app", "web-stack-a", 1111, "local.md")
    _stack_runbook(tmp_path, "web-app", "web-stack-b", 2222, "staging.md")
    graph = model.load(tmp_path)
    near = tmp_path / "docs" / "features" / "web-app" / "specs" / "home.md"
    selection = rb.select_stack(graph, near=near)
    assert selection.reason == "ambiguous"


def test_near_outside_the_features_root_stays_ambiguous(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, "web-app", "local")
    _environment(tmp_path, "api-service", "staging")
    _stack_runbook(tmp_path, "web-app", "web-stack", 1111, "local.md")
    _stack_runbook(tmp_path, "api-service", "api-stack", 2222, "staging.md")
    graph = model.load(tmp_path)
    selection = rb.select_stack(graph, near=tmp_path / "README.md")
    assert selection.reason == "ambiguous"


def test_an_explicit_name_wins_over_near(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, "web-app", "local")
    _environment(tmp_path, "api-service", "staging")
    _stack_runbook(tmp_path, "web-app", "web-stack", 1111, "local.md")
    _stack_runbook(tmp_path, "api-service", "api-stack", 2222, "staging.md")
    graph = model.load(tmp_path)
    near = tmp_path / "docs" / "features" / "web-app" / "specs" / "home.md"
    selection = rb.select_stack(graph, name="api-stack", near=near)
    assert selection.reason == ""
    assert [n.path.stem for n in selection.runbooks] == ["api-stack"]


def test_near_outranks_a_lone_local_only_environment_elsewhere(tmp_path: Path) -> None:
    """The surface under audit decides, even when the only `local-only` environment in the
    book belongs to another surface. `near` knows which surface QA is exercising and the
    `local-only` filter does not, so a book-wide declaration must never pull the bring-up
    across to a system the spec has nothing to do with.
    """
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, "web-app", "staging", local_only=False)
    _environment(tmp_path, "api-service", "devbox", local_only=True)
    _stack_runbook(tmp_path, "web-app", "web-stack", 1111, "staging.md")
    _stack_runbook(tmp_path, "api-service", "api-stack", 2222, "devbox.md")
    graph = model.load(tmp_path)

    assert rb.select_stack(graph).environment.endswith("devbox.md")

    near = tmp_path / "docs" / "features" / "web-app" / "specs" / "home.md"
    selection = rb.select_stack(graph, near=near)
    assert selection.reason == ""
    assert [n.path.stem for n in selection.runbooks] == ["web-stack"]
    assert selection.environment.endswith("staging.md")


def test_near_is_a_no_op_when_the_book_already_resolves(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "local"))
    graph = model.load(tmp_path)
    without_near = rb.select_stack(graph)
    near = tmp_path / "docs" / "features" / "app" / "specs" / "home.md"
    with_near = rb.select_stack(graph, near=near)
    assert with_near == without_near


def test_a_nested_book_resolves_paths_against_the_system_it_describes(tmp_path: Path) -> None:
    # A book is a description, and a description is not located in its subject. `.` means
    # the root of the system the book is about, not the checkout the book was read from —
    # otherwise a fixture's stack launches from a directory holding none of its files.
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "fixtures" / "globex"
    write(nested / "docs" / "features" / "app" / "ops" / "qa-stack.md",
          "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
          "- entry-url: http://localhost:1111\n- working-directory: `.`\n\n"
          "## Steps\n\n### serve\n\n- kind: service\n- run: docker compose up\n"
          "- health: curl -fsS localhost\n")
    graph = model.load(tmp_path, root_overrides={"features": "fixtures/globex/docs/features"})
    assert rb.system_root(graph) == nested
    manifest = rb.load_stack(graph=graph)
    assert manifest["app_cwd"] == str(nested.resolve())
    assert manifest["repo_root"] == str(nested.resolve())


# --- the doctor half: the book saying nothing, or saying something unrunnable ---


def codes(root: Path) -> list[str]:
    from ostler import doctor
    return [fd.code for fd in doctor.run(model.load(root)).findings]


def test_doctor_warns_once_when_no_stack_is_declared(tmp_path: Path) -> None:
    # The finding that moves the greenfield hole from turn 61 to author time.
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "app" / "gui" / "screens" / "home.md",
          "---\ntype: screen\nslug: home\n---\n\n# Home\n\nprose\n")
    assert codes(tmp_path).count("runbook-missing") == 1


def test_doctor_asks_for_no_stack_from_a_book_with_nothing_to_serve(tmp_path: Path) -> None:
    """A CLI, a library and an infrastructure program have nothing to bring up.

    The warning is about a surface that cannot be reached until a process answers — a
    `screen` or a `server`. Asking a book with neither to declare a stack would be asking
    it to declare a stack for nothing, and a repo whose doctor is red for being what it is
    teaches its authors to stop reading the doctor.
    """
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "tally" / "tally.md",
          "---\ntype: cli\nslug: tally\n---\n\n# tally\n\nprose\n")
    assert "runbook-missing" not in codes(tmp_path)


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
    write(tmp_path / "docs" / "features" / "app" / "gui" / "screens" / "home.md",
          "---\ntype: screen\nslug: home\n---\n\n# Home\n\nprose\n")
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# Rotate the keys\n\n- driver: cli\n"
                 "\n## Steps\n\n### rotate\n\n- kind: run\n- run: ./rotate.sh\n",
                 name="rotate-the-keys")
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


def test_doctor_reports_a_check_expression_on_a_service_health_bullet(tmp_path: Path) -> None:
    # `ensure_stack` shells `health:` verbatim — a check call there is a bullet written for
    # `verify:` and put on the wrong key, and bash would only ever answer with a syntax error.
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- entry-url: http://localhost:1\n\n## Steps\n\n### serve\n\n"
                 "- kind: service\n- run: ./serve.sh\n"
                 '- health: http_status(200, path="/healthz")\n')
    assert "check-expression-as-command" in codes(tmp_path)


def test_doctor_reports_a_check_expression_on_a_run_bullet(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- entry-url: http://localhost:1\n\n## Steps\n\n### serve\n\n"
                 "- kind: service\n"
                 '- run: http_status(200, path="/healthz")\n\n'
                 "### smoke\n\n- kind: run\n"
                 '- run: http_status(200, path="/healthz")\n')
    assert "check-expression-as-command" in codes(tmp_path)


def test_doctor_reports_the_scenario_frame_token_on_a_runbook_step(tmp_path: Path) -> None:
    """A runbook step runs at bring-up, before any scenario exists — the token names a
    frame that is not there yet, unlike on a fixture step, where it is exactly right."""
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- entry-url: http://localhost:1\n\n## Steps\n\n### serve\n\n"
                 "- kind: service\n- run: ./serve.sh\n\n"
                 "### seed\n\n- kind: seed\n- run: ./seed.sh\n"
                 "- working-directory: scenario:\n")
    assert "runbook-scenario-frame" in codes(tmp_path)


def test_doctor_stays_quiet_on_a_real_command(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- entry-url: http://localhost:1\n\n## Steps\n\n### serve\n\n"
                 "- kind: service\n- run: ./serve.sh\n"
                 "- health: curl -fsS http://localhost:1/healthz\n")
    assert "check-expression-as-command" not in codes(tmp_path)


def test_bring_up_stacks_stops_at_the_first_failure(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "local"))
    manifests, _ = rb.load_stacks(model.load(tmp_path))
    assert len(manifests) == 2

    calls: list[str] = []

    def fake_ensure_stack(manifest, *, repo_root, logger):
        calls.append(manifest["source"])
        return {"ready": "no", "failed_step": "health", "error": "never answered"}

    monkeypatch.setattr(rb.stack_mod, "ensure_stack", fake_ensure_stack)
    results = rb.bring_up_stacks(manifests, repo_root=str(tmp_path), logger=None)

    assert calls == [manifests[0]["source"]]
    assert len(results) == 1
    assert results[0]["ready"] == "no"


def test_cmd_stack_up_outcome_is_unchanged_for_success_and_failure(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "local"))

    def fake_ensure_stack_ok(manifest, *, repo_root, logger):
        return {"ready": "yes", "adopted": "no", "entry_url": manifest["entry_url"],
                "app_pid": "123", "app_pgid": "123"}

    monkeypatch.setattr(rb.stack_mod, "ensure_stack", fake_ensure_stack_ok)
    outcome = rb.cmd_stack_up(tmp_path)
    assert outcome.ok
    assert outcome.message == (
        "stack brought up and healthy at http://localhost:1111, http://localhost:2222 "
        "(2 services)")
    assert outcome.data["stacks"][0]["ready"] == "yes"
    assert outcome.data["stacks"][1]["ready"] == "yes"
    assert outcome.data["entry_url"] == "http://localhost:2222"

    def fake_ensure_stack_fails_second(manifest, *, repo_root, logger):
        if manifest["source"].endswith("web-stack.md"):
            return {"ready": "no", "failed_step": "health", "error": "never answered"}
        return {"ready": "yes", "adopted": "no", "entry_url": manifest["entry_url"]}

    monkeypatch.setattr(rb.stack_mod, "ensure_stack", fake_ensure_stack_fails_second)
    outcome = rb.cmd_stack_up(tmp_path)
    assert not outcome.ok
    assert outcome.message == (
        "stack bring-up failed for 'docs/features/app/ops/web-stack.md' at step 'health': "
        "never answered")
    assert len(outcome.data["stacks"]) == 2
    assert outcome.data["stacks"][0]["ready"] == "yes"
    assert outcome.data["stacks"][1]["ready"] == "no"
