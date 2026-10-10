"""The run brings up the stack its own book declares, not the first stack another book declares, and stops only what it started."""
from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from ostler import index

from workhorse_workflows.kit.qa import runner
from workhorse_workflows.okf_book.shared import book_run, scenarios
from workhorse_workflows.okf_book.shared.book_run import (
    ExerciseResult,
    StackReadiness,
    bring_up,
    compile_scenarios,
    release,
    run_plan,
    stack_down_failures,
    stack_down_result,
    stack_pages,
    unplanned_problem,
    unstarted_failures,
    with_app_logs,
)
from ostler.qa.plan import PlanDocument
from workhorse_workflows.okf_book.shared.scenarios import RunSummary, ScenarioOutcome, plan_scenarios

PREVIEW = (
    "---\ntype: environment\nslug: preview\ntitle: Preview\n---\n# Preview\n\n"
    "- selector: local-only\n- local-only: true\n"
)
WEB_STACK = Path("docs/features/web-app/ops/web-app-stack.md")
SERVING = StackReadiness(up=True, serving=True, notes="")


def _repo_with_web_app_on_preview(repo: Path) -> Path:
    _ = (repo / WEB_STACK.parent / "preview.md").write_text(PREVIEW, encoding="utf-8")
    stack = repo / WEB_STACK
    text = stack.read_text(encoding="utf-8")
    _ = stack.write_text(text.replace("[local](../../api-service/ops/local.md)", "[preview](preview.md)"), encoding="utf-8")
    return repo


@pytest.fixture
def brought_up(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sources: list[str] = []

    def _bring_up(manifests: list[dict[str, object]], **_kwargs: object) -> list[dict[str, str]]:
        sources.extend(str(manifest.get("source", "")) for manifest in manifests)
        return [{"ready": "yes"}]

    monkeypatch.setattr(runner.runbook, "bring_up_stacks", _bring_up)
    return sources


def test_a_service_brings_up_the_stack_its_own_book_declares(app: Callable[[str], Path], brought_up: list[str]) -> None:
    repo = _repo_with_web_app_on_preview(app("globex"))

    readiness = bring_up(logging.getLogger(__name__), repo, "web-app")

    assert readiness.serving
    assert brought_up == [WEB_STACK.as_posix()]


def test_another_service_leaves_that_stack_down(app: Callable[[str], Path], brought_up: list[str]) -> None:
    repo = _repo_with_web_app_on_preview(app("globex"))

    _ = bring_up(logging.getLogger(__name__), repo, "api-service")

    assert "docs/features/api-service/ops/api-service-stack.md" in brought_up
    assert WEB_STACK.as_posix() not in brought_up


def test_a_stack_that_cannot_come_up_is_a_problem_on_each_runbook_of_its_own_book(app: Callable[[str], Path]) -> None:
    repo = app("globex")
    down = stack_down_result(("gap: okf:a:does:1: k: d",), "port 8080 is held by groom")

    failures = stack_down_failures(repo, "web-app", down)

    assert "docs/features/api-service/ops/api-service-stack.md" not in failures
    assert {page: [problem.text for problem in problems] for page, problems in failures.items()} == {
        WEB_STACK.as_posix(): [f"{WEB_STACK.as_posix()}: the app's stack cannot come up: port 8080 is held by groom"]
    }
    assert stack_down_failures(repo, "web-app", ExerciseResult(lines=("problem: the book compiles to no plan",))) == {}


def test_a_book_that_compiles_to_no_plan_says_when_its_index_declares_it_unexercised(app: Callable[[str], Path]) -> None:
    repo = app("tally-cli")
    before = unplanned_problem(repo, "tally")
    _ = (repo / "docs/features/tally/index.md").write_text("---\ntitle: tally\nexercised: false\n---\n# tally\n", encoding="utf-8")

    assert before == "the book compiles to no plan"
    assert unplanned_problem(repo, "tally") == "the book's index declares it unexercised, so it compiles to no plan and the run exercises nothing"


def _bring_up_returns(monkeypatch: pytest.MonkeyPatch, results: list[dict[str, str]]) -> None:
    def _bring_up(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
        return results

    monkeypatch.setattr(runner.runbook, "bring_up_stacks", _bring_up)
    monkeypatch.setattr(runner, "_group_running", _running)


def _running(_pgid: int) -> bool:
    return True


def test_a_bring_up_owns_the_servers_it_started_and_not_one_it_adopted(
    app: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _bring_up_returns(monkeypatch, [
        {"ready": "yes", "app_pgid": "11"},
        {"ready": "yes", "app_pgid": "22", "adopted": "yes"},
        {"ready": "yes", "app_pgid": "33"},
    ])
    reaped: list[str] = []

    def _teardown(pgid: str, *_args: object, **_kwargs: object) -> dict[str, str]:
        reaped.append(pgid)
        return {"torn_down": "yes"}

    monkeypatch.setattr(runner.stack, "teardown_app", _teardown)

    readiness = bring_up(logging.getLogger(__name__), app("globex"), "web-app")
    release(logging.getLogger(__name__), readiness)

    assert readiness.owned == ("11", "33")
    assert reaped == ["33", "11"]


def test_a_failed_bring_up_still_owns_the_servers_it_started(app: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch) -> None:
    _bring_up_returns(monkeypatch, [{"ready": "yes", "app_pgid": "11"}, {"ready": "no", "failed_step": "launch", "app_pgid": ""}])

    readiness = bring_up(logging.getLogger(__name__), app("globex"), "web-app")

    assert not readiness.up
    assert readiness.owned == ("11",)


def test_a_run_scoped_to_a_flow_page_compiles_the_whole_book_and_runs_only_that_flow(app: Callable[[str], Path], tmp_path: Path) -> None:
    flow_page = "docs/features/api-service/flows/add-widget-via-api.md"

    outcome = compile_scenarios(app("globex"), "api-service", tmp_path / "spec", (flow_page,))

    assert outcome.planned
    assert outcome.only == ("docs-features-api-service-flows-add-widget-via-api-journey",)
    assert all(f"okf:{flow_page}" in gap for gap in outcome.gaps)


def _described(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    described: list[Path] = []
    loading = scenarios.load_plan

    def _load_plan(plan_file: Path, spec_dir: Path, root: Path) -> tuple[PlanDocument | None, list[str]]:
        described.append(plan_file)
        return loading(plan_file, spec_dir, root)

    monkeypatch.setattr(scenarios, "load_plan", _load_plan)
    return described


def test_a_check_describes_its_compiled_plan_once_to_pick_and_run_its_scenarios(
    app: Callable[[str], Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, spec = app("globex"), tmp_path / "spec"
    described = _described(monkeypatch)

    outcome = compile_scenarios(repo, "api-service", spec, ("docs/features/api-service/flows/add-widget-via-api.md",))
    planned, _problems = plan_scenarios(repo, spec)

    assert set(outcome.only) <= {scenario.id for scenario in planned}
    assert len(described) == 1


def test_a_plan_compiled_again_is_described_again(app: Callable[[str], Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, spec = app("globex"), tmp_path / "spec"
    flow_page = "docs/features/api-service/flows/add-widget-via-api.md"
    described = _described(monkeypatch)
    _ = compile_scenarios(repo, "api-service", spec, (flow_page,))

    _ = compile_scenarios(repo, "api-service", spec, (flow_page,))

    assert len(described) == 2

def test_a_bring_up_names_the_logs_of_the_apps_it_launched(app: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch) -> None:
    _bring_up_returns(monkeypatch, [{"ready": "yes", "app_log": "/cache/api.log"}, {"ready": "yes", "adopted": "yes"}])

    readiness = bring_up(logging.getLogger(__name__), app("globex"), "web-app")

    assert readiness.app_logs == ("/cache/api.log",)


def _ran(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    summary = RunSummary(status="failed", scenarios={"create-widget": ScenarioOutcome(status="failed", assertions=1, failures=1, message=message)})

    def _run_scenarios(*_args: object) -> RunSummary:
        return summary

    monkeypatch.setattr(book_run, "run_scenarios", _run_scenarios)


def _app_log(tmp_path: Path) -> str:
    log = tmp_path / "api.log"
    _ = log.write_text(
        "listening on :8080\n"
        "POST /widgets Authorization: Bearer eyJhbGciOi.eyJzdWIi.c2lnbmF0dXJl\n"
        "error cloning the default widget: relation widgets_default does not exist\n",
        encoding="utf-8")
    return str(log)


def test_a_check_the_app_answered_with_a_server_error_shows_the_end_of_its_log_without_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _ran(monkeypatch, "POST http://localhost:8080/widgets returned 500: internal error")
    log = _app_log(tmp_path)

    result = with_app_logs(run_plan(tmp_path, tmp_path / "spec", (), SERVING), (log,))

    assert f"the app answered a server error, and its log {log} ends with:" in result.lines
    assert "  error cloning the default widget: relation widgets_default does not exist" in result.lines
    assert not any("eyJ" in line or "c2lnbmF0dXJl" in line for line in result.lines)


def test_a_check_that_failed_without_a_server_error_leaves_the_log_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ran(monkeypatch, "GET http://localhost:8080/widgets returned 404: not found")

    result = with_app_logs(run_plan(tmp_path, tmp_path / "spec", (), SERVING), (_app_log(tmp_path),))

    assert not any("its log" in line for line in result.lines)


def test_a_port_no_runbook_starts_is_a_problem_on_each_runbook_of_its_own_book(app: Callable[[str], Path]) -> None:
    repo = app("globex")
    called = ExerciseResult(lines=(), unstarted=("the app called localhost:8080", "the app called localhost:8081"))

    failures = unstarted_failures(repo, "web-app", called)

    assert {page: [problem.text for problem in problems] for page, problems in failures.items()} == {
        WEB_STACK.as_posix(): [f"{WEB_STACK.as_posix()}: the app called localhost:8080\nthe app called localhost:8081"]
    }
    assert unstarted_failures(repo, "web-app", ExerciseResult(lines=())) == {}


def test_a_second_look_at_an_unchanged_book_reads_its_stack_from_the_index(
    app: Callable[[str], Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = app("globex")
    monkeypatch.setenv("OSTLER_INDEX_DIR", str(tmp_path / "index"))
    first = stack_pages(repo, "api-service")
    stores: list[index.IndexStore] = []
    opened = index.session

    @contextmanager
    def _session(root: Path) -> Generator[index.IndexStore]:
        with opened(root) as store:
            stores.append(store)
            yield store

    monkeypatch.setattr(index, "session", _session)

    second = stack_pages(repo, "api-service")

    assert second == first
    assert stores[0].hits
    assert stores[0].misses == 0
