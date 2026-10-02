"""`ostler edit carve-endpoints` and doctor's server-membership check."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.carve import carve_endpoints
from ostler.cli import main
from ostler.model import load

from conftest import write

_SERVER = "docs/features/acme/http/server.md"

_SERVER_TEXT = """---
type: server
title: Acme API
---
# Acme API

- entry-url: http://localhost:8000
- code: `app.py`

## Endpoints

### get-widget

- method: GET
- path: /widgets/{id}
- status: 200
- verify: http_status(code=200, path="/widgets/1")

#### Caching

Widgets are cached for a minute.

### create-widget

- method: POST
- path: /widgets
- status: 201

## Invocations

### fetch-widget

- on: [get-widget](#get-widget)
- trigger: the home screen loads
"""

_SCREEN = "docs/features/acme/gui/screens/home.md"

_SCREEN_TEXT = """---
type: screen
title: Home
---
# Home

- route: /
- calls: [create a widget](../../http/server.md#create-widget)
- server: [the API](../../http/server.md)
"""


def _book(repo: Path) -> Path:
    write(repo / _SERVER, _SERVER_TEXT)
    write(repo / _SCREEN, _SCREEN_TEXT)
    write(repo / "app.py", "x = 1\n")
    return repo / _SERVER


def _codes(repo: Path) -> set[str]:
    return {f.code for f in doctor.run(load(repo)).findings}


def test_carve_dry_run_writes_nothing(repo: Path):
    server = _book(repo)
    plan = carve_endpoints(load(repo), "acme/http/server.md")
    assert not plan.error
    assert "2 endpoint page(s), 1 invocation(s)" in plan.render()
    assert server.read_text() == _SERVER_TEXT
    assert not (server.parent / "get-widget.md").exists()


def test_carve_moves_each_endpoint_and_its_invocation_to_a_page(repo: Path):
    server = _book(repo)
    carve_endpoints(load(repo), "acme/http/server.md").apply()

    page = (server.parent / "get-widget.md").read_text()
    assert page.startswith("---\ntype: endpoint\nslug: get-widget\ntitle: get-widget\n---\n")
    assert "# get-widget\n\n- server: [Acme API](server.md)\n- method: GET\n" in page
    assert "\n## Caching\n\nWidgets are cached for a minute.\n" in page
    assert "## Invocations\n\n### fetch-widget\n\n- on: [get-widget](get-widget.md)\n" in page

    slim = server.read_text()
    assert "## Endpoints\n\n- [get-widget](get-widget.md)\n- [create-widget](create-widget.md)\n" in slim
    assert "### " not in slim and "## Invocations" not in slim


def test_carve_relinks_the_pages_that_pointed_into_the_server(repo: Path):
    _book(repo)
    carve_endpoints(load(repo), "acme/http/server.md").apply()
    screen = (repo / _SCREEN).read_text()
    assert "[create a widget](../../http/create-widget.md)" in screen
    assert "[the API](../../http/server.md)" in screen


def test_carved_book_keeps_its_doctor_findings_and_passes_membership(repo: Path):
    _book(repo)
    before = _codes(repo)
    carve_endpoints(load(repo), "acme/http/server.md").apply()
    after = _codes(repo)
    assert after <= before
    assert not after & {"endpoint-without-server", "unlisted-endpoint"}
    endpoints = sorted(n.id for n in load(repo).ui_nodes_of_type("endpoint"))
    assert endpoints == ["docs/features/acme/http/create-widget.md",
                         "docs/features/acme/http/get-widget.md"]


def test_carve_refuses_a_page_that_is_not_a_server(repo: Path):
    _book(repo)
    plan = carve_endpoints(load(repo), "acme/gui/screens/home.md")
    assert plan.error == "home.md is not a server page"


def test_carve_refuses_to_overwrite_an_existing_page(repo: Path):
    server = _book(repo)
    write(server.parent / "create-widget.md", "taken\n")
    plan = carve_endpoints(load(repo), "acme/http/server.md")
    assert plan.error == "a page already exists for: create-widget"


def test_carve_refuses_a_server_with_no_endpoints(repo: Path):
    write(repo / _SERVER, "---\ntype: server\ntitle: A\n---\n# A\n\n## Endpoints\n")
    plan = carve_endpoints(load(repo), "acme/http/server.md")
    assert plan.error == "server.md holds no endpoint to carve"


def test_carve_cli_writes_with_write(repo: Path):
    server = _book(repo)
    assert main(["-C", str(repo), "edit", "carve-endpoints", "acme/http/server.md", "--write"]) == 0
    assert (server.parent / "create-widget.md").exists()


def test_endpoint_page_naming_no_server_is_reported(repo: Path):
    write(repo / "docs/features/acme/http/lone.md",
          "---\ntype: endpoint\ntitle: lone\n---\n# lone\n\n- method: GET\n- path: /lone\n")
    assert "endpoint-without-server" in _codes(repo)


def test_endpoint_page_its_server_does_not_list_is_reported(repo: Path):
    write(repo / "docs/features/acme/http/server.md",
          "---\ntype: server\ntitle: A\n---\n# A\n\n## Endpoints\n")
    write(repo / "docs/features/acme/http/lone.md",
          "---\ntype: endpoint\ntitle: lone\n---\n# lone\n\n- server: [A](server.md)\n- method: GET\n")
    codes = _codes(repo)
    assert "unlisted-endpoint" in codes and "endpoint-without-server" not in codes
