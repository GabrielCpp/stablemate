"""What makes a service real to the planner: it exists, and the repo declares it."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.coder.shared.contract import declared_service_paths, service_problems


def test_a_service_the_repo_declares_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "app" / "api").mkdir(parents=True)

    assert service_problems(tmp_path / "app" / "api", "acme::app/api", "app/api", ["app/api"]) == []


def test_a_directory_no_services_entry_names_is_refused(tmp_path: Path) -> None:
    (tmp_path / "app" / "web").mkdir(parents=True)

    problems = service_problems(tmp_path / "app" / "web", "acme::app/web", "app/web", ["app/api"])

    assert len(problems) == 1
    assert "not declared under `services:`" in problems[0]


def test_a_repo_that_declares_no_services_only_needs_a_directory(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()

    assert service_problems(tmp_path / "app", "acme::app", "app", []) == []
    assert service_problems(tmp_path / "gone", "acme::gone", "gone", []) != []


def test_a_path_is_compared_without_its_slashes(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()

    assert service_problems(tmp_path / "app", "acme::app/", "app/", ["app"]) == []


def test_a_service_with_no_path_is_declared_at_the_repo_root() -> None:
    assert declared_service_paths({"api": {"lint": "ruff"}, "web": {"path": "app/web/"}}) == [
        ".",
        "app/web",
    ]
    assert declared_service_paths(None) == []


def test_no_entry_declaring_a_path_leaves_the_check_lenient(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    declared = declared_service_paths({"api": {"lint": "ruff"}, "web": {"test": "npm test"}})

    assert declared == []
    assert service_problems(tmp_path / "app", "acme::app", "app", declared) == []


def test_one_entry_declaring_a_path_makes_the_check_strict(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    declared = declared_service_paths({"api": {"path": "svc/api"}, "web": {"test": "npm test"}})

    assert service_problems(tmp_path / "app", "acme::app", "app", declared) != []
