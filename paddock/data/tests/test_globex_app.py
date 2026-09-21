"""Integrity tests for the `globex` app."""

from __future__ import annotations

import contextlib
import importlib.util
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from paddock.registry import REGISTRY

DATA = Path(__file__).parents[1]
APP = DATA / "apps" / "globex"

COMPOSE_SERVICES = {
    "api-service": {"dockerfile": "app/api-service/Dockerfile", "port": 18101},
    "web-app": {"dockerfile": "app/web-app/Dockerfile", "port": 18102},
}


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does when it loads a task."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    REGISTRY.reset()
    with _tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module


TASK = _load("_task_under_test", DATA / "tasks" / "globex_qa.py")




def test_every_screen_selector_is_one_the_render_scan_can_address() -> None:
    """A documented selector must be a form `ostler vet` can resolve, or the node reads missing."""
    from ostler.vet.placement import is_addressable  # noqa: PLC0415 - a heavy import only this test needs

    screens = sorted((APP / "docs" / "features").rglob("gui/screens/*.md"))
    assert screens, "the fixture documents no screens"
    checked = 0
    for screen in screens:
        for line in screen.read_text(encoding="utf-8").splitlines():
            if not line.startswith("- selector:"):
                continue
            checked += 1
            selector = line.split(":", 1)[1].strip().strip("`")
            assert is_addressable(selector), (
                f"{screen.name}: `{selector}` is a form the render scan never mints — "
                "address the element by id, by tag and class, by its ARIA role, or (mobile) "
                "by its `testID`"
            )
    assert checked, f"no `- selector:` bullet matched across {len(screens)} screen files"


def test_the_fixture_ships_the_screens_it_claims() -> None:
    """Every screen file under `docs/features` is a screen node `ostler` actually parses."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    screens = sorted((APP / "docs" / "features").rglob("gui/screens/*.md"))
    paths = {node["path"] for node in Ostler(APP).list("screen")}
    for screen in screens:
        rel = screen.relative_to(APP).as_posix()
        assert rel in paths, f"{rel} is a screen file the graph never mints a screen node for"




def _compose() -> dict:
    return yaml.safe_load((APP / "compose.yml").read_text(encoding="utf-8"))


def test_compose_declares_exactly_the_services_this_fixture_brings_up() -> None:
    services = _compose()["services"]
    assert set(services) == set(COMPOSE_SERVICES)


@pytest.mark.parametrize("service", sorted(COMPOSE_SERVICES), ids=sorted(COMPOSE_SERVICES))
def test_compose_dockerfile_exists_in_the_app_tree(service: str) -> None:
    """A renamed or moved Dockerfile is invisible to `doctor` — it reads the ops page's citation hash on `compose.yml`, not the paths `compose.yml` itself names — and would only surface once a round tried to build the image."""
    build = _compose()["services"][service]["build"]
    dockerfile = Path(build["dockerfile"])
    assert dockerfile.as_posix() == COMPOSE_SERVICES[service]["dockerfile"]
    assert (APP / dockerfile).is_file(), f"{service}: {dockerfile} is not in the app tree"


@pytest.mark.parametrize("service", sorted(COMPOSE_SERVICES), ids=sorted(COMPOSE_SERVICES))
def test_compose_port_matches_the_ops_page_entry_url(service: str) -> None:
    """The port an ops runbook tells an agent to reach must be the port `compose.yml` binds."""
    published = _compose()["services"][service]["ports"]
    port = COMPOSE_SERVICES[service]["port"]
    assert f"{port}:{port}" in published, f"{service}: compose.yml does not publish {port}"

    runbook = APP / "docs" / "features" / service / "ops" / f"{service}-stack.md"
    text = runbook.read_text(encoding="utf-8")
    assert f"entry-url: http://localhost:{port}" in text, (
        f"{service}: {runbook.name} does not name port {port}"
    )




def test_the_task_points_at_the_app_and_names_the_trial_dir() -> None:
    """The two paths a frozen-app task has to get right, whether or not it has an answer key yet: what app it points at, and what a trial would materialize it as."""
    assert DATA / TASK.FIXTURE.app == APP
    assert TASK.FIXTURE.repo_dir == "globex"
