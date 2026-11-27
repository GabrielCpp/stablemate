"""`ostler book missing`: the tracked source files of an app that no element of the book names."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ostler.book import App
from ostler.book.cli import cmd_missing
from ostler.book.service import Service


def _git(folder: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@example.com", *arguments],
                   check=True, capture_output=True)


@pytest.fixture
def app(tmp_path: Path) -> Path:
    root = tmp_path / "web-app"
    for name in ("web/routes/home.tsx", "web/routes/about.tsx", "web/routes/home.test.tsx", "web/styles/site.css", "docs/guide.md"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x\n")
    _git(tmp_path, "init", "--quiet", str(root))
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "init")
    return root


def _service(*source: str, roots: tuple[str, ...] = ("web",), ignore: tuple[str, ...] = (), declared: bool = True) -> Service[Any]:
    screen = SimpleNamespace(__name__="Home", source=source)
    book = App(roots=roots, verified="VERIFIED", ignore=ignore) if declared else None
    return cast("Service[Any]", SimpleNamespace(name="web", endpoints=(), records=(), screens=(screen,), interactions=(), outside=(), app=book, documentation=None))


def _run(service: Service[Any], app: Path, *under: str, files: bool = False) -> int:
    return cmd_missing(service, argparse.Namespace(app=str(app), under=list(under), files=files))


def test_a_tracked_file_under_a_root_that_no_element_names_is_listed_and_exits_1(app, capsys):
    code = _run(_service("web/routes/home.tsx", ignore=("*.test.tsx", "*.css")), app)
    out = capsys.readouterr().out
    assert code == 1
    assert "- web/routes/about.tsx" in out
    assert "1 of 4 files are in no element and under no ignore pattern" in out
    assert "nothing missing" not in out


def test_a_file_an_element_names_is_not_listed(app, capsys):
    code = _run(_service("web/routes/home.tsx::Home", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css")), app)
    out = capsys.readouterr().out
    assert code == 0
    assert "## Files no element names\n\n" in out
    assert out.rstrip().endswith("nothing missing")


def test_a_file_an_ignore_pattern_matches_is_not_listed_and_is_counted_under_the_pattern(app, capsys):
    _run(_service("web/routes/home.tsx", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css")), app)
    out = capsys.readouterr().out
    assert "- web/routes/home.test.tsx" not in out
    assert "- *.test.tsx: 1 files" in out
    assert "- *.css: 1 files" in out


def test_under_widens_the_universe_past_the_roots(app, capsys):
    service = _service("web/routes/home.tsx", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css"))
    assert _run(service, app) == 0
    capsys.readouterr()
    assert _run(service, app, "web", "docs") == 1
    assert "- docs/guide.md" in capsys.readouterr().out


def test_a_service_with_no_app_exits_2_and_says_how_to_declare_one(app, capsys):
    assert _run(_service(declared=False), app) == 2
    assert 'give Service app=App(roots=(...), verified="VERIFIED")' in capsys.readouterr().out


def test_a_folder_that_holds_no_tracked_file_exits_2_and_names_the_folder(app, capsys):
    assert _run(_service("web/routes/home.tsx"), app, "wbe") == 2
    out = capsys.readouterr().out
    assert "no tracked file under wbe" in out
    assert "nothing missing" not in out


def test_an_untracked_file_is_not_listed(app, capsys):
    (app / "web" / "routes" / "draft.tsx").write_text("x\n")
    _run(_service("web/routes/home.tsx", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css")), app)
    assert "draft.tsx" not in capsys.readouterr().out


def test_a_named_file_is_mapped_to_the_elements_that_name_it_with_their_kind(app, capsys):
    service = _service("web/routes/home.tsx::Home", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css"))
    _run(service, app)
    out = capsys.readouterr().out
    assert "## What the book names\n- web/routes/about.tsx: Home (screen)\n- web/routes/home.tsx: Home (screen)\n" in out
    assert out.index("## What the book names") < out.index("## Files no element names")


def test_files_lists_each_left_out_file_under_its_pattern_and_the_default_only_counts(app, capsys):
    service = _service("web/routes/home.tsx", "web/routes/about.tsx", ignore=("*.test.tsx", "*.css"))
    _run(service, app)
    assert "    web/routes/home.test.tsx" not in capsys.readouterr().out
    _run(service, app, files=True)
    assert "- *.test.tsx: 1 files\n    web/routes/home.test.tsx\n" in capsys.readouterr().out


PROTO = """syntax = "proto3";
package notifications.v1;
service NotificationsService {
  rpc Send(A) returns (B);
  rpc StreamNotifications(A) returns (stream B);
}
"""

OPENAPI = """openapi: 3.0.0
paths:
  /todos:
    get: {}
  /todos/{id}:
    delete: {}
"""


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "api-service"
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    _git(tmp_path, "init", "--quiet", str(root))
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "init")
    return root


def _rpc(call: str) -> Any:
    return SimpleNamespace(__name__=call.rpartition("/")[2], source=("api/notifications.proto",), carries=None, rpc=call, method="POST", path="/" + call)


def _endpoint(method: str, path: str) -> Any:
    return SimpleNamespace(__name__=f"{method}{path}", source=("api/openapi.yaml",), carries=None, method=method, path=path)


def _book(*endpoints: Any, ignore: tuple[str, ...] = ()) -> Service[Any]:
    return cast("Service[Any]", SimpleNamespace(name="api", endpoints=endpoints, records=(), screens=(), interactions=(), outside=(),
                                                app=App(roots=("api",), verified="VERIFIED", ignore=ignore), documentation=None))


def test_an_rpc_the_proto_lists_and_no_rpc_declares_is_named_and_exits_1(tmp_path, capsys):
    root = _repo(tmp_path, {"api/notifications.proto": PROTO})
    code = _run(_book(_rpc("notifications.v1.NotificationsService/Send")), root)
    out = capsys.readouterr().out
    assert code == 1
    assert "## Calls a contract lists that no element declares\n- api/notifications.proto: notifications.v1.NotificationsService/StreamNotifications (streams its answer)\n" in out
    assert "no ignore pattern, and 1 call a contract lists is declared by no element" in out
    assert "nothing missing" not in out


def test_a_proto_outside_the_roots_is_found_from_a_service_the_declared_calls_name(tmp_path, capsys):
    root = _repo(tmp_path, {"api/handler.go": "x\n", "proto/notifications.proto": PROTO})
    code = _run(_book(_rpc("notifications.v1.NotificationsService/Send")), root)
    out = capsys.readouterr().out
    assert code == 1
    assert "- proto/notifications.proto: notifications.v1.NotificationsService/StreamNotifications (streams its answer)" in out


def test_a_proto_outside_the_roots_that_no_declared_call_names_is_left_alone(tmp_path, capsys):
    root = _repo(tmp_path, {"api/handler.go": "x\n", "proto/notifications.proto": PROTO})
    assert _run(_book(_endpoint("GET", "/other"), ignore=("*.go",)), root) == 0


def test_an_openapi_operation_no_endpoint_declares_is_named_with_path_parameters_matched_by_position(tmp_path, capsys):
    root = _repo(tmp_path, {"api/openapi.yaml": OPENAPI})
    code = _run(_book(_endpoint("GET", "/todos"), _endpoint("PATCH", "/todos/{todo_id}")), root)
    out = capsys.readouterr().out
    assert code == 1
    assert "- api/openapi.yaml: DELETE /todos/{id}" in out
    assert "GET /todos\n" not in out.split("## Calls a contract lists")[1]
    assert _run(_book(_endpoint("GET", "/todos"), _endpoint("DELETE", "/todos/{todo_id}")), root) == 0


def test_an_ignore_pattern_on_a_call_leaves_it_out_and_exits_0(tmp_path, capsys):
    root = _repo(tmp_path, {"api/notifications.proto": PROTO})
    book = _book(_rpc("notifications.v1.NotificationsService/Send"), ignore=("api/notifications.proto::StreamNotifications",))
    assert _run(book, root) == 0
    assert out_ends(capsys) == "nothing missing"


def out_ends(capsys) -> str:
    return capsys.readouterr().out.rstrip().splitlines()[-1]


def test_a_book_that_declares_every_call_of_its_contract_prints_as_before(tmp_path, capsys):
    root = _repo(tmp_path, {"api/notifications.proto": PROTO})
    book = _book(_rpc("notifications.v1.NotificationsService/Send"), _rpc("notifications.v1.NotificationsService/StreamNotifications"))
    assert _run(book, root) == 0
    out = capsys.readouterr().out
    assert out == ("## What the book names\n- api/notifications.proto: Send (endpoint), StreamNotifications (endpoint)\n"
                   "\n## Files no element names\n\n## Left out by the book\n\n0 of 1 files are in no element and under no ignore pattern\nnothing missing\n")


M = "example.com/shop"
SEND = "(*github.com/aws/aws-sdk-go-v2/service/eventbridge.Client).PutEvents"
GRAPH = [
    f"(*{M}/cmd/orders/app.App).placeOrder\t(*{M}/cmd/orders/app.App).publishPlaced\tstatic method call\t{{root}}/cmd/orders/app/orders.go",
    f"(*{M}/cmd/orders/app.App).publishPlaced\t(*{M}/pkg/eventing.Publisher).Publish\tdynamic method call\t{{root}}/cmd/orders/app/orders.go",
    f"(*{M}/pkg/eventing.Publisher).Publish\t(*{M}/pkg/eventing.Publisher).Publish$1\tstatic function closure call\t{{root}}/pkg/eventing/publish.go",
    f"(*{M}/pkg/eventing.Publisher).Publish$1\t{SEND}\tdynamic method call\t{{root}}/pkg/eventing/publish.go",
    f"(*{M}/cmd/orders/app.App).listOrders\t{M}/pkg/pages.Each\tstatic function call\t{{root}}/cmd/orders/app/orders.go",
    f"{M}/pkg/pages.Each\t(*{M}/pkg/eventing.Publisher).Publish\tdynamic function call\t{{root}}/pkg/pages/each.go",
]


@pytest.fixture
def go_app(tmp_path: Path, monkeypatch) -> Path:
    root = _repo(tmp_path, {"go.mod": f"module {M}\n", "cmd/orders/app/orders.go": "package app\n"})
    monkeypatch.setattr("ostler.book.publishes.call_graph", lambda app_root, roots: ([line.format(root=root) for line in GRAPH], ""))
    return root


def _action(*source: str, emits: tuple[Any, ...] = ()) -> Any:
    return type("PlaceOrder", (), {"source": source, "emits": emits})


def _orders(*carried: Any, ignore: tuple[str, ...] = (), delivery: Any = None) -> Service[Any]:
    endpoints = tuple(SimpleNamespace(__name__=f"E{i}", source=("cmd/orders/app/orders.go",), carries=a, method="POST", path=f"/e{i}") for i, a in enumerate(carried)) or (
        SimpleNamespace(__name__="E", source=("cmd/orders/app/orders.go",), carries=None, method="POST", path="/e"),)
    return cast("Service[Any]", SimpleNamespace(name="orders", endpoints=endpoints, records=(), screens=(), interactions=(), outside=(),
                                                environments={"local": SimpleNamespace(delivery=delivery)},
                                                app=App(roots=("cmd/orders",), verified="VERIFIED", ignore=ignore), documentation=None))


PLACED = SimpleNamespace(name="OrderPlaced")


def test_a_function_under_the_roots_that_reaches_a_transport_through_shared_code_is_listed_and_exits_1(go_app, capsys):
    code = _run(_orders(), go_app)
    out = capsys.readouterr().out
    assert code == 1
    assert "## Publishes no action emits\n- cmd/orders/app/orders.go::App.publishPlaced sends through (*pkg/eventing.Publisher).Publish\n" in out
    assert "and 1 function publishes with no action emitting" in out


def test_a_call_through_a_function_value_is_not_followed(go_app, capsys):
    _run(_orders(), go_app)
    out = capsys.readouterr().out
    assert "listOrders" not in out
    assert "placeOrder" not in out


def test_an_action_that_emits_and_names_the_publishing_function_clears_it(go_app, capsys):
    book = _orders(_action("cmd/orders/app/orders.go::App.publishPlaced", emits=(PLACED,)), delivery=object())
    assert _run(book, go_app) == 0
    assert out_ends(capsys) == "nothing missing"


def test_an_action_that_names_the_function_and_emits_nothing_leaves_it_listed(go_app, capsys):
    assert _run(_orders(_action("cmd/orders/app/orders.go::App.publishPlaced")), go_app) == 1
    assert "::App.publishPlaced sends through" in capsys.readouterr().out


def test_an_ignore_pattern_on_the_function_clears_it(go_app, capsys):
    assert _run(_orders(ignore=("cmd/orders/app/orders.go::App.publishPlaced",)), go_app) == 0


def test_an_emitted_event_with_no_delivery_in_any_environment_is_listed_and_exits_1(go_app, capsys):
    book = _orders(_action("cmd/orders/app/orders.go::App.publishPlaced", emits=(PLACED,)))
    assert _run(book, go_app) == 1
    assert "## Events no environment taps\n- OrderPlaced (PlaceOrder): give an environment a delivery" in capsys.readouterr().out


def test_a_call_graph_that_cannot_be_read_is_reported_and_exits_1(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {"go.mod": f"module {M}\n", "cmd/orders/app/orders.go": "package app\n"})
    monkeypatch.setattr("ostler.book.publishes.call_graph", lambda app_root, roots: ([], "go is not on PATH"))
    assert _run(_orders(), root) == 1
    assert "## Publishes no action emits\n- not read: go is not on PATH\n" in capsys.readouterr().out
