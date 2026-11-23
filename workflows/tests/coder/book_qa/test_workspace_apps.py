"""The book lane in a multi-repo workspace: each service's code is read from the repo that holds it."""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from _workspace import Workspace

from workhorse_workflows.coder.book_qa import nodes as book_nodes
from workhorse_workflows.kit import find_book_package

Git = Callable[..., subprocess.CompletedProcess[str]]

SERVICE = """from ostler.book import App, Environment, Interaction, Screen, Service, State


class Home(Screen):
    route = "/"
    first = True
    source = ("src/api/x.py",)


class Reload(Interaction[None]):
    screen = Home
    leads_to = Home
    does = "reloads the page"
    source = ("src/api/x.py",)


service = Service(
    name="api",
    app=App(roots=("src/api",), verified="VERIFIED", ignore=()),
    languages=("en",),
    screens=(Home,),
    default_environment="local",
    environments={"local": Environment("local", {})},
    new_model=State,
    stack=lambda log: None,
    journeys=(),
    surface=lambda env: None,
)
"""

LAYOUTS = [
    pytest.param("services/api", "services.api", id="flat"),
    pytest.param("services/api/api", "services.api.api", id="namespaced"),
]


def _book(workspace: Workspace, git: Git, write: Callable[[Path, str], Path], folder: str) -> None:
    artifacts, api = workspace.artifacts, workspace.api
    write(api / "agents.yml", "repo:\n  id_prefix: X\nservices:\n  api:\n    path: .\n")
    write(api / "src/api/x.py", "one\n")
    git(api, "add", "agents.yml", "src")
    git(api, "commit", "-qm", "chore: base")
    base = git(api, "rev-parse", "HEAD").stdout.strip()
    write(artifacts / "services/__init__.py", "")
    if folder != "services/api":
        write(artifacts / f"{folder.rpartition('/')[0]}/__init__.py", "")
    write(artifacts / f"{folder}/__init__.py", "")
    write(artifacts / f"{folder}/service.py", SERVICE)
    write(artifacts / f"{folder}/VERIFIED", base + "\n")
    git(artifacts, "add", "services")
    git(artifacts, "commit", "-qm", "docs: add the book")
    write(api / "src/api/x.py", "two\n")
    git(api, "add", "src")
    git(api, "commit", "-qm", "feat(api): change\n\nStory: S-1")


@pytest.mark.parametrize(("folder", "module"), LAYOUTS)
def test_the_story_selects_the_service_from_the_repo_that_holds_its_code(
    workspace: Workspace, git: Git, write: Callable[[Path, str], Path], logger: logging.Logger, folder: str, module: str
) -> None:
    _book(workspace, git, write, folder)

    covered = book_nodes.covered_services(
        logger, None, str(workspace.artifacts), "s-1", "S-1", workspace="acme"
    )

    assert covered.services == ["api"], covered


@pytest.mark.parametrize(("folder", "module"), LAYOUTS)
def test_the_plan_reads_the_change_of_the_code_repo(
    workspace: Workspace, git: Git, write: Callable[[Path, str], Path], logger: logging.Logger, tmp_path: Path, folder: str, module: str
) -> None:
    _book(workspace, git, write, folder)

    plan = book_nodes.book_plan(
        logger, "api", str(tmp_path / "spec"), "s-1", "S-1", str(workspace.artifacts), workspace="acme"
    )

    assert plan.exit_code == 0, plan.output
    assert plan.changed == 1, plan


@pytest.mark.parametrize(("folder", "module"), LAYOUTS)
def test_the_check_builds_the_book_against_the_code_repo(
    workspace: Workspace, git: Git, write: Callable[[Path, str], Path], logger: logging.Logger, folder: str, module: str
) -> None:
    _book(workspace, git, write, folder)

    played = book_nodes.book_check(logger, "api", str(workspace.artifacts), workspace="acme")

    assert played.exit_code == 0, played


@pytest.mark.parametrize(("folder", "module"), LAYOUTS)
def test_the_stamp_records_the_head_of_the_code_repo(
    workspace: Workspace, git: Git, write: Callable[[Path, str], Path], logger: logging.Logger, folder: str, module: str
) -> None:
    _book(workspace, git, write, folder)

    played = book_nodes.stamp_books_verified(
        logger, ["api"], "s-1", "S-1", str(workspace.artifacts), workspace="acme"
    )

    stamped = (workspace.artifacts / folder / "VERIFIED").read_text(encoding="utf-8").strip()
    assert played.exit_code == 0, played
    assert git(workspace.api, "rev-parse", "HEAD").stdout.strip().startswith(stamped), (stamped, git(workspace.api, "rev-parse", "HEAD").stdout.strip())


def test_a_lone_repo_keeps_its_own_root_and_package(repo: Path, git: Git) -> None:
    from workhorse_workflows.coder.book_qa import apps

    found = apps.service_app(str(repo), "", "a")

    assert found is not None
    assert found.app == found.cwd == repo.resolve()
    assert found.package == find_book_package(str(repo))
