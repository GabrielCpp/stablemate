"""Integrity tests for the `globex` app.

`globex` is not yet a frozen-app fixture in the sense `test_seat_booking_app.py` and
`test_policy_desk_app.py` check: it has no `stories/`, no `defects.yml`, no `docs/specs/`,
so there is no manifest chain, no materialization and no answer key to gate here yet.
Authoring that corpus is separate work. What this file covers is what already exists and
can already rot silently — the book, and the one manifest globex does have: `compose.yml`,
which is what a round (once it has an answer key to run) actually brings up.

* **A documented selector must be a form `ostler vet`'s render scan can resolve.** This is
  the same grammar `test_seat_booking_app.py` gates, and for the same concrete reason:
  globex shipped both a web surface (CSS selectors) and a mobile surface (`testID=`
  selectors) addressed against the same render scan, and both directions have already
  regressed here once — a mobile control addressed by a form the census could never confirm,
  and a screen missing the accessible name the census needs to resolve a role selector at
  all (`46fb5028`, `d8a0ba20`). Neither failure is loud: the book stays `doctor`-clean, and
  the component simply reads `missing` on every render, which makes whatever defect targets
  it unmeasurable.
* **`compose.yml` must still point at dockerfiles and contexts that exist.** It is the only
  manifest globex has today, and it is also the thing `_frozenapp.py`'s citation
  (`code: compose.yml @<hash>`) on every `ops/*-stack.md` page names — a service renamed or
  moved out from under it is invisible to `doctor`, which reads the citation's hash and not
  the file it names, and would only surface once a round tried to build the image.
* **The ops pages' entry points must still match what `compose.yml` actually serves.** The
  port a runbook tells an agent to reach is prose; `compose.yml` is what is actually bound.
  Nothing keeps those in sync structurally, so a port changed in one and not the other reads
  as a healthy stack that answers on the wrong door.

No docker and no agent here — this is the book and the compose manifest, nothing that costs
money to check.
"""

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

#: The two services `compose.yml` actually brings up. `mobile-app` ships a book and a
#: Maestro flow but no service of its own — Metro is started by hand, not by compose — so
#: it is not a third entry here.
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
    # The registry is module-global and a task module declares into it at import: reset it
    # around the load, exactly as `paddock.loader` does, or the second task loaded in this
    # process refuses on a name the first one claimed.
    REGISTRY.reset()
    with _tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module


TASK = _load("_task_under_test", DATA / "tasks" / "globex_qa.py")


# ── the book ──────────────────────────────────────────────────────────────────────────


def test_every_screen_selector_is_one_the_render_scan_can_address() -> None:
    """A documented selector must be a form `ostler vet` can resolve, or the node reads missing.

    `ostler.vet.placement.is_addressable` is the one spelling of this grammar — the same
    function backs the doctor's `unaddressable-selector` check (so the shared
    `test_app_books.py::test_doctor_is_clean` already fails on a regression here too), and
    this test exists to name the offending selector directly across *both* screen surfaces:
    the web book's CSS-shaped selectors and the mobile book's `testID=` ones.
    """
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
    # The scan is a line-prefix match, not a parse: an authoring change that indents these
    # bullets under their component would make every assertion above unreachable and leave
    # the test green. Both surfaces ship them today, so zero means the scan broke.
    assert checked, f"no `- selector:` bullet matched across {len(screens)} screen files"


def test_the_fixture_ships_the_screens_it_claims() -> None:
    """Every screen file under `docs/features` is a screen node `ostler` actually parses."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    screens = sorted((APP / "docs" / "features").rglob("gui/screens/*.md"))
    paths = {node["path"] for node in Ostler(APP).list("screen")}
    for screen in screens:
        rel = screen.relative_to(APP).as_posix()
        assert rel in paths, f"{rel} is a screen file the graph never mints a screen node for"


# ── the manifest globex has: `compose.yml` ──────────────────────────────────────────────


def _compose() -> dict:
    return yaml.safe_load((APP / "compose.yml").read_text(encoding="utf-8"))


def test_compose_declares_exactly_the_services_this_fixture_brings_up() -> None:
    services = _compose()["services"]
    assert set(services) == set(COMPOSE_SERVICES)


@pytest.mark.parametrize("service", sorted(COMPOSE_SERVICES), ids=sorted(COMPOSE_SERVICES))
def test_compose_dockerfile_exists_in_the_app_tree(service: str) -> None:
    """A renamed or moved Dockerfile is invisible to `doctor` — it reads the ops page's
    citation hash on `compose.yml`, not the paths `compose.yml` itself names — and would
    only surface once a round tried to build the image."""
    build = _compose()["services"][service]["build"]
    dockerfile = Path(build["dockerfile"])
    assert dockerfile.as_posix() == COMPOSE_SERVICES[service]["dockerfile"]
    assert (APP / dockerfile).is_file(), f"{service}: {dockerfile} is not in the app tree"


@pytest.mark.parametrize("service", sorted(COMPOSE_SERVICES), ids=sorted(COMPOSE_SERVICES))
def test_compose_port_matches_the_ops_page_entry_url(service: str) -> None:
    """The port an ops runbook tells an agent to reach must be the port `compose.yml` binds.

    Nothing structural keeps the two in sync — `compose.yml`'s `ports:` is executable, the
    runbook's `entry-url:` is prose — so a port changed in one and not the other reads as a
    healthy stack answering on the wrong door.
    """
    published = _compose()["services"][service]["ports"]
    port = COMPOSE_SERVICES[service]["port"]
    assert f"{port}:{port}" in published, f"{service}: compose.yml does not publish {port}"

    runbook = APP / "docs" / "features" / service / "ops" / f"{service}-stack.md"
    text = runbook.read_text(encoding="utf-8")
    assert f"entry-url: http://localhost:{port}" in text, (
        f"{service}: {runbook.name} does not name port {port}"
    )


# ── the registration ──────────────────────────────────────────────────────────────────


def test_the_task_points_at_the_app_and_names_the_trial_dir() -> None:
    """The two paths a frozen-app task has to get right, whether or not it has an answer
    key yet: what app it points at, and what a trial would materialize it as."""
    assert DATA / TASK.FIXTURE.app == APP
    # farrier derives generated skill names from the basename; anything else dangles.
    assert TASK.FIXTURE.repo_dir == "globex"
