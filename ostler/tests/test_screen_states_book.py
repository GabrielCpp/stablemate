"""A screen page declares the requests it sends, its busy sign and its settled states: doctor reads them, and only a state owes a check."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ostler import registry
from ostler.cli import main
from ostler.qa.compile import Plan, compile_plan_gaps
from ostler.qa.context import build_context

from conftest import report_of, write

SCREEN = "docs/services/acme/gui/screens/results.md"

PAGE = """---
type: screen
title: Results
---
# Results

- route: /
- requires: none
- params: none
- requests:
  - GET /api/results
- busy: [Loading results](#loading-results)

## Components

### Loading results
- role: progressbar
- name: Loading results

### Results table
- role: table
- name: Results

### Load error
- role: alert
- name: Could not load results

### Open details
- role: button
- name: Open details
- code: app/r.py::go

## Interactions

### open-details-click
- on: [Open details](#open-details)
- trigger: click
- does:
  - request: opens
- code: app/r.py::go

## Screen states

### Loaded
- shows:
  - [Results table](#results-table)
  - [Load error](#load-error) absent

### Error
- shows:
  - [Load error](#load-error)
"""

FLOW = """---
type: flow
title: See
---
# See

- start: [results](../gui/screens/results.md)
- steps:
  - [Loaded](../gui/screens/results.md#loaded)
  - [open-details-click](../gui/screens/results.md#open-details-click)
- end: [results](../gui/screens/results.md)
- verify: visible(locator="../gui/screens/results.md#open-details")
"""


ENVIRONMENT = """---
type: environment
title: Local
---
# Local

- selector: `ACME_BIND=127.0.0.1`
- services:
  - results: `http://127.0.0.1:8787`
- local-only: true
"""

RUNBOOK = """---
type: runbook
title: QA stack
---

# QA stack

- driver: web
- entry-url: http://localhost:18084
- environment: [local](local.md)
- surfaces: [results](../gui/screens/results.md)

## Steps

### serve

- kind: service
- run: `run`
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def book(tmp_path: Path) -> Path:
    write(tmp_path / SCREEN, PAGE)
    write(tmp_path / "docs/services/acme/flows/see.md", FLOW)
    write(tmp_path / "app/r.py", "def go():\n    return 1\n")
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "x")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    return tmp_path


def test_the_registry_hosts_screen_states_on_screen_pages_only() -> None:
    assert registry.UI_HEADING_TO_TYPE["Screen states"] == "state"
    assert registry.UI_TYPES_BY_NAME["state"].host_page_types == ("screen",)


def test_doctor_reads_requests_busy_and_states_without_complaint(book: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["-C", str(book), "doctor", "--json"])
    findings = [f for f in report_of(capsys)["findings"] if f.get("path") == SCREEN]

    assert not [f for f in findings if any(word in f["message"] for word in ("requests", "busy", "shows", "Screen states"))]
    states = [f for f in findings if f.get("node", "").endswith(("#loaded", "#error"))]
    assert {f["code"] for f in states} <= {"undeclared-obligation"}


def test_a_state_owes_one_obligation_and_requests_and_busy_owe_none(book: Path) -> None:
    write(book / "app/r.py", "def go():\n    return 2\n")
    base = _git(book, "rev-parse", "HEAD")

    packet = build_context(book, base=base, source_roots={"acme": ["app"]})
    ids = {row["id"]: row for row in packet["obligations"]}

    loaded = ids[f"okf:{SCREEN}#loaded:contract"]
    assert loaded["nodeType"] == "state"
    assert "Results table" in loaded["requirement"] and "Load error" in loaded["requirement"]
    assert not [oid for oid in ids if oid.startswith(f"okf:{SCREEN}#loaded:shows")]
    assert not [oid for oid in ids if ":requests" in oid or ":busy" in oid]
    screen = ids[f"okf:{SCREEN}:contract"]
    assert screen["locators"]["requests"] == ["GET /api/results"]
    assert screen["locators"]["busy"] == ["[Loading results](#loading-results)"]


def test_a_walk_selected_by_its_flow_alone_still_waits_for_the_screens_requests(book: Path) -> None:
    flow = book / "docs/services/acme/flows/see.md"
    flow.write_text(flow.read_text().replace(
        "  - [open-details-click](../gui/screens/results.md#open-details-click)\n", "",
    ).replace(
        "- start:",
        '- fixture: none, because the screen loads the same rows for anyone\n'
        '- verify: visible(locator="../gui/screens/results.md#open-details")\n- start:',
        1,
    ))
    write(book / "docs/services/acme/ops/qa-stack.md", RUNBOOK)
    write(book / "docs/services/acme/ops/local.md", ENVIRONMENT)
    _git(book, "add", ".")
    _git(book, "commit", "-m", "runbook")
    base = _git(book, "rev-parse", "HEAD")

    packet = build_context(book, base=base, source_roots={"acme": ["app"]}, whole_book=True,
                           books=("docs/services/acme/flows",))
    result = compile_plan_gaps(packet, story="demo-story")

    assert isinstance(result, Plan), [(gap.kind, gap.detail) for gap in result.gaps]
    settle = result.source[result.source.index("qa.settle("):result.source.index("# step 1: stop at")]
    assert '("GET", "/api/results")' in settle
    assert '"role": "progressbar"' in settle


def test_a_fixture_under_a_state_reaches_its_obligation_and_none_because_says_it_arranges_nothing(book: Path) -> None:
    page = book / SCREEN
    page.write_text(page.read_text().replace(
        "### Error\n", "### Error\n- fixture: none, because the screen opens on the failing rows\n",
    ).replace(
        "### Loaded\n", "### Loaded\n- fixture: none, because the seeded world loads cleanly\n",
    ))
    write(book / "app/r.py", "def go():\n    return 2\n")
    base = _git(book, "rev-parse", "HEAD")

    packet = build_context(book, base=base, source_roots={"acme": ["app"]})
    ids = {row["id"]: row for row in packet["obligations"]}

    assert ids[f"okf:{SCREEN}#error:contract"]["arrangesNothing"] is True
    assert ids[f"okf:{SCREEN}#loaded:contract"]["arrangesNothing"] is True


FAIL_FIXTURE = """---
type: fixture
title: Results fail
---
# Results fail

## Steps

### fail

- kind: seed
- run: true
"""


def test_a_fixture_under_a_state_reaches_the_fixtures_of_its_obligation(book: Path) -> None:
    page = book / SCREEN
    page.write_text(page.read_text().replace(
        "### Error\n", "### Error\n- fixture: [Results fail](../../fixtures/results-fail.md)\n",
    ))
    write(book / "docs/services/acme/fixtures/results-fail.md", FAIL_FIXTURE)
    write(book / "app/r.py", "def go():\n    return 2\n")
    base = _git(book, "rev-parse", "HEAD")

    packet = build_context(book, base=base, source_roots={"acme": ["app"]})
    error = next(row for row in packet["obligations"] if row["id"] == f"okf:{SCREEN}#error:contract")

    assert [row["name"] for row in error["fixturesDeclared"]] == ["results-fail"]
