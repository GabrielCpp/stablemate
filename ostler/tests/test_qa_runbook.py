"""`ostler.qa.runbook` — the book's ops nodes read as the manifest `ensure_stack` takes."""

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
    assert [s["run"] for s in manifest["health"]] == [
        "curl -fsS http://localhost:18084/healthz"]


def test_a_check_expression_on_run_or_health_is_not_shelled(tmp_path: Path) -> None:
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
    """No scenario directory exists at manifest-build time, so `_step_command` must not invent a fake absolute path for the token — it hands the frame on as a marker for the harness to resolve at run time."""
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
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "app" / "home.md",
          "---\ntype: feature\nslug: home\n---\n\n# Home\n\nprose\n")
    assert rb.load_stack(tmp_path) == {}


def test_falls_back_to_the_books_server(tmp_path: Path) -> None:
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
""")
    manifest = rb.load_stack(tmp_path)
    assert manifest["launch"] == "npm start"
    assert manifest["entry_url"] == "http://localhost:3000"
    assert manifest["app_cwd"] == str((tmp_path / "api").resolve())


def test_several_servers_fall_back_to_the_first_by_id(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    for slug, port in (("one", 3001), ("two", 3002)):
        write(tmp_path / "docs" / "features" / "api" / f"{slug}.md",
              f"---\ntype: server\ntitle: {slug}\n---\n\n# {slug}\n\n"
              f"- launch: npm start\n- entry-url: http://localhost:{port}\n")
    assert rb.load_stack(tmp_path)["entry_url"] == "http://localhost:3001"


def test_named_runbook_selects_and_a_wrong_name_does_not_guess(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    for name, port in (("qa-stack", 1111), ("release", 2222)):
        make_runbook(tmp_path, f"---\ntype: runbook\n---\n\n# {name}\n\n"
                     f"- driver: web\n- entry-url: http://localhost:{port}\n\n"
                     "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
                     "- health: curl -fsS localhost\n", name=name)
    assert rb.load_stack(tmp_path, name="release")["entry_url"] == "http://localhost:2222"
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


def test_several_environments_and_no_name_settle_on_the_first_by_path(tmp_path: Path) -> None:
    """`local` and `staging` are both environments this book says QA may boot, so which of them the bring-up starts is a question about the tooling, not about the system being described."""
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "staging"))
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")
    assert [n.path.stem for n in selection.runbooks] == ["api-stack"]


def test_stack_runbooks_binding_no_environment_are_a_refusal_not_an_absence(
        tmp_path: Path) -> None:
    """The refusal that is left, and the only one: two stack runbooks, neither naming an `environment:`."""
    (tmp_path / ".git").mkdir()
    for name, port in (("api-stack", 1111), ("web-stack", 2222)):
        make_runbook(tmp_path, f"---\ntype: runbook\n---\n\n# {name}\n\n"
                     f"- driver: web\n- entry-url: http://localhost:{port}\n\n"
                     "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
                     "- health: curl -fsS localhost\n", name=name)
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == "ambiguous"
    assert len(selection.candidates) == 2
    outcome = rb.cmd_stack_up(tmp_path)
    assert not outcome.ok and outcome.status == "ambiguous"
    assert "--runbook" in outcome.message
    assert rb.cmd_stack_down(tmp_path).status == "ambiguous"


def test_a_settled_stack_outranks_a_servers_launch_contract(tmp_path: Path) -> None:
    """`load_stack` falls through to a `server` node only when nothing in the book resolves to a stack at all."""
    (tmp_path / ".git").mkdir()
    _two_stacks(tmp_path, environments=("local", "staging"))
    write(tmp_path / "docs" / "features" / "other" / "server.md", """---
type: server
title: Other
---

# Other

- launch: npm start
- entry-url: http://localhost:9000/
""")
    assert rb.load_stack(tmp_path)["entry_url"] == "http://localhost:1111"


def test_a_single_environment_with_two_runbooks_has_no_single_manifest(tmp_path: Path) -> None:
    """globex's shape: two runbooks, one environment."""
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


def _environment_file(root: Path, env: str, *, local_only: bool | None) -> None:
    """One `environment` node under `app/ops`, its `local-only` bullet set explicitly."""
    bullets = ""
    if local_only is not None:
        bullets += f"- local-only: {'true' if local_only else 'false'}\n"
    write(root / "docs" / "features" / "app" / "ops" / f"{env}.md",
          f"---\ntype: environment\n---\n\n# {env}\n\n{bullets}")


def test_the_local_only_environment_outranks_the_path_order(tmp_path: Path) -> None:
    """Two stack runbooks bind to `staging`, one to `prod`, and only `staging` is declared `local-only: true`."""
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "prod", local_only=False)
    _environment_file(tmp_path, "staging", local_only=True)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "staging")
    _local_stack_runbook(tmp_path, "web-stack", 2222, "staging")
    _local_stack_runbook(tmp_path, "worker-stack", 3333, "prod")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("staging.md")
    assert {n.path.stem for n in selection.runbooks} == {"api-stack", "web-stack"}


def test_two_local_only_environments_settle_on_the_first_by_path(tmp_path: Path) -> None:
    """Two honestly local environments — two docker-compose profiles, say — both survive the filter, and the book has nothing further to say about which of them the tooling starts."""
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=True)
    _environment_file(tmp_path, "staging", local_only=True)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "web-stack", 2222, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")
    assert {n.path.stem for n in selection.runbooks} == {"api-stack"}


def test_a_book_declaring_no_local_only_anywhere_still_settles(tmp_path: Path) -> None:
    """The filter keeps nothing when no candidate declares itself local, and keeping nothing must not mean discarding everything: an absent `local-only` is silence, not a refusal, and silence must not cost a book its own environments."""
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=None)
    _environment_file(tmp_path, "staging", local_only=False)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "worker-stack", 3333, "staging")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")


def test_a_single_local_only_environment_still_early_returns(tmp_path: Path) -> None:
    """A book with one environment never reaches the `local-only` filter at all — it resolves earlier, on every stack runbook sharing that one environment."""
    (tmp_path / ".git").mkdir()
    _environment_file(tmp_path, "local", local_only=True)
    _local_stack_runbook(tmp_path, "api-stack", 1111, "local")
    _local_stack_runbook(tmp_path, "web-stack", 2222, "local")
    selection = rb.select_stack(model.load(tmp_path))
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")
    assert len(selection.runbooks) == 2


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


def test_near_narrows_the_selection_to_its_surfaces_environment(tmp_path: Path) -> None:
    """web-app and api-service bind to different environments; mobile-app binds to the same environment as web-app despite sitting in a third surface."""
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, "web-app", "local")
    _environment(tmp_path, "api-service", "staging")
    _stack_runbook(tmp_path, "web-app", "web-stack", 1111, "local.md")
    _stack_runbook(tmp_path, "api-service", "api-stack", 2222, "staging.md")
    _stack_runbook(tmp_path, "mobile-app", "mobile-stack", 3333, "../../web-app/ops/local.md")
    graph = model.load(tmp_path)

    baseline = rb.select_stack(graph)
    assert baseline.environment.endswith("api-service/ops/staging.md")
    assert [n.path.stem for n in baseline.runbooks] == ["api-stack"]

    near = tmp_path / "docs" / "features" / "web-app" / "specs" / "home.md"
    selection = rb.select_stack(graph, near=near)
    assert selection.reason == ""
    assert {n.path.stem for n in selection.runbooks} == {"web-stack", "mobile-stack"}
    assert selection.environment.endswith("local.md")


def test_near_narrowing_to_two_environments_falls_through_to_the_path_order(
        tmp_path: Path) -> None:
    """`near` narrows to the surface's own environments and stops there."""
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, "web-app", "local")
    _environment(tmp_path, "web-app", "staging")
    _stack_runbook(tmp_path, "web-app", "web-stack-a", 1111, "local.md")
    _stack_runbook(tmp_path, "web-app", "web-stack-b", 2222, "staging.md")
    graph = model.load(tmp_path)
    near = tmp_path / "docs" / "features" / "web-app" / "specs" / "home.md"
    selection = rb.select_stack(graph, near=near)
    assert selection.reason == ""
    assert selection.environment.endswith("local.md")
    assert [n.path.stem for n in selection.runbooks] == ["web-stack-a"]


def test_near_outside_the_features_root_leaves_the_book_wide_answer(tmp_path: Path) -> None:
    """A path that is not under `docs/features/` names no surface, so there is nothing to narrow by — `near` is simply not an argument this selection can use."""
    (tmp_path / ".git").mkdir()
    _environment(tmp_path, "web-app", "local")
    _environment(tmp_path, "api-service", "staging")
    _stack_runbook(tmp_path, "web-app", "web-stack", 1111, "local.md")
    _stack_runbook(tmp_path, "api-service", "api-stack", 2222, "staging.md")
    graph = model.load(tmp_path)
    selection = rb.select_stack(graph, near=tmp_path / "README.md")
    assert selection == rb.select_stack(graph)
    assert selection.environment.endswith("api-service/ops/staging.md")


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
    """The surface under audit decides, even when the only `local-only` environment in the book belongs to another surface."""
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




def codes(root: Path) -> list[str]:
    from ostler import doctor
    return [fd.code for fd in doctor.run(model.load(root)).findings]


def test_doctor_warns_once_when_no_stack_is_declared(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "app" / "gui" / "screens" / "home.md",
          "---\ntype: screen\nslug: home\n---\n\n# Home\n\nprose\n")
    assert codes(tmp_path).count("runbook-missing") == 1


def test_doctor_asks_for_no_stack_from_a_book_with_nothing_to_serve(tmp_path: Path) -> None:
    """A CLI, a library and an infrastructure program have nothing to bring up."""
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "tally" / "tally.md",
          "---\ntype: cli\nslug: tally\n---\n\n# tally\n\nprose\n")
    assert "runbook-missing" not in codes(tmp_path)


def test_doctor_stays_quiet_when_a_server_declares_a_launch(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    write(tmp_path / "docs" / "features" / "api" / "server.md",
          "---\ntype: server\ntitle: API\n---\n\n# API\n\n- launch: npm start\n"
          "- entry-url: http://localhost:3000\n")
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
    """A runbook that starts nothing is a procedure, not a broken stack."""
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
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- entry-url: http://localhost:1\n\n## Steps\n\n"
                 "### api\n\n- kind: service\n- run: ./api.sh\n\n"
                 "### web\n\n- kind: service\n- run: ./web.sh\n")
    assert "runbook-multi-service" in codes(tmp_path)


def test_doctor_refuses_a_local_only_environment_pointing_off_the_machine(
        tmp_path: Path) -> None:
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
    """A runbook step runs at bring-up, before any scenario exists — the token names a frame that is not there yet, unlike on a fixture step, where it is exactly right."""
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


def test_a_teardown_step_is_legal_and_is_not_a_bring_up_phase(tmp_path: Path) -> None:
    """A book documenting a whole lifecycle has to file its shutdown targets somewhere."""
    (tmp_path / ".git").mkdir()
    make_runbook(tmp_path, "---\ntype: runbook\n---\n\n# QA\n\n- driver: web\n"
                 "- entry-url: http://localhost:1\n\n## Steps\n\n"
                 "### build\n\n- kind: prepare\n- run: make\n\n"
                 "### serve\n\n- kind: service\n- run: ./serve.sh\n\n"
                 "### wipe\n\n- kind: teardown\n- run: docker compose down -v\n")
    assert "runbook-bad-kind" not in codes(tmp_path)
    manifest = rb.load_stack(graph=model.load(tmp_path))
    assert [step["run"] for step in manifest["prepare"]] == ["make"]
    assert "docker compose down -v" not in repr(manifest)
