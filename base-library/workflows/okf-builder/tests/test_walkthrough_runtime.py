from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).parents[1] / "scripts"
WORKFLOW = Path(__file__).parents[1] / "workflow.yaml"


def load_script(name: str):
    path = SCRIPTS / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py").replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_detect_webapp_reads_server_launch_contract(tmp_path: Path) -> None:
    detect = load_script("detect-webapp.py")
    source = tmp_path / "web"
    source.mkdir()
    text = """\
---
type: server
---
- launch: `npm run dev -- --host 127.0.0.1 --port 4173`
- working-directory: `web`
- entry-url: `http://127.0.0.1:4173/`
- health-path: `/`
- identity: `<title>Acme</title>`
"""

    contract = detect.parse_launch_contract(text, str(tmp_path), str(source))

    assert contract == {
        "launch_cmd": "npm run dev -- --host 127.0.0.1 --port 4173",
        "entry_url": "http://127.0.0.1:4173",
        "health_path": "/",
        "app_cwd": str(source),
        "app_identity": "<title>Acme</title>",
        "stop_cmd": "",
        "boot_timeout": "",
        "walkthrough": "",
    }


def test_detect_webapp_ignores_prose_after_the_backticked_value(tmp_path: Path) -> None:
    """Real books explain their bullets; the backticks fence the machine-facing part."""
    detect = load_script("detect-webapp.py")
    source = tmp_path / "web"
    source.mkdir()
    text = """\
---
type: server
---
- launch: `npm run dev` (`react-router dev`, the Vite dev server; starts from source, no
  build step)
- working-directory: `web`
- entry-url: `http://localhost:5173` — Vite's default dev port
- health-path: `/` — this shell has no dedicated JSON health endpoint; any GET of `/`
  returns the shell HTML
- identity: `<title>Acme</title>`
"""

    contract = detect.parse_launch_contract(text, str(tmp_path), str(source))

    assert contract == {
        "launch_cmd": "npm run dev",
        "entry_url": "http://localhost:5173",
        "health_path": "/",
        "app_cwd": str(source),
        "app_identity": "<title>Acme</title>",
        "stop_cmd": "",
        "boot_timeout": "",
        "walkthrough": "",
    }


def test_detect_webapp_reads_the_bring_up_bullets(tmp_path: Path) -> None:
    """A command that returns once a stack is up needs a stop recipe and a real ceiling."""
    detect = load_script("detect-webapp.py")
    (tmp_path / "api").mkdir()
    text = """\
---
type: server
---
- launch: `make dev-stack-test-db` — the fully dockerized stack bound to the loaded dump
- working-directory: `api`
- entry-url: `http://localhost:3000`
- boot-timeout: `1800` — a cold build runs npm ci + vite build + go build
- identity: `<title>Acme</title>`
"""

    contract = detect.parse_launch_contract(text, str(tmp_path), "api")

    assert contract["launch_cmd"] == "make dev-stack-test-db"
    assert contract["boot_timeout"] == "1800"
    # No `stop:` documented -> teardown leaves the stack up for the next walk.
    assert contract["stop_cmd"] == ""


def _contract(name: str, marked: str = "") -> dict[str, str]:
    return {"launch_cmd": f"run {name}", "entry_url": f"http://localhost/{name}",
            "walkthrough": marked}


def test_select_server_prefers_the_one_marked_production_like(caplog) -> None:
    """Two ways to run one app: the marked server wins regardless of file order."""
    detect = load_script("detect-webapp.py")
    paths = ["docs/features/web/http/web-shell.md", "docs/features/web/http/web-static.md"]
    marks = {paths[1]: "true"}

    picked = detect.select_server(
        paths, lambda p: _contract(p, marks.get(p, "")), logging.getLogger("detect"),
    )

    assert picked["launch_cmd"] == f"run {paths[1]}"


def test_select_server_warns_when_several_servers_and_none_is_marked(caplog) -> None:
    """An unmarked book is choosing by file order — say so rather than pick silently."""
    detect = load_script("detect-webapp.py")
    paths = ["docs/features/web/http/a.md", "docs/features/web/http/b.md"]

    with caplog.at_level(logging.WARNING):
        picked = detect.select_server(
            paths, lambda p: _contract(p), logging.getLogger("detect"),
        )

    assert picked["launch_cmd"] == f"run {paths[0]}"  # deterministic: first of the sorted list
    assert "none is marked" in caplog.text


def test_select_server_is_quiet_for_the_single_server_case(caplog) -> None:
    """One documented server is unambiguous — no bullet needed, no warning earned."""
    detect = load_script("detect-webapp.py")

    with caplog.at_level(logging.WARNING):
        picked = detect.select_server(
            ["docs/features/report/http/report.md"], lambda p: _contract(p),
            logging.getLogger("detect"),
        )

    assert picked["launch_cmd"].startswith("run ")
    assert caplog.text == ""


def test_select_server_warns_when_two_servers_both_claim_to_be_primary(caplog) -> None:
    detect = load_script("detect-webapp.py")
    paths = ["docs/features/web/http/a.md", "docs/features/web/http/b.md"]

    with caplog.at_level(logging.WARNING):
        picked = detect.select_server(
            paths, lambda p: _contract(p, "true"), logging.getLogger("detect"),
        )

    assert picked["launch_cmd"] == f"run {paths[0]}"
    assert "marked" in caplog.text


def test_select_server_ignores_servers_without_a_launch_contract() -> None:
    """A `server` node documenting no launch recipe cannot be walked — skip, don't pick."""
    detect = load_script("detect-webapp.py")
    paths = ["docs/features/web/http/prose-only.md", "docs/features/web/http/real.md"]

    picked = detect.select_server(
        paths, lambda p: {} if "prose-only" in p else _contract(p),
        logging.getLogger("detect"),
    )

    assert picked["launch_cmd"] == f"run {paths[1]}"


def test_walkthrough_uses_runtime_contract_and_current_flow_outputs() -> None:
    workflow = WORKFLOW.read_text()

    assert '- key: app_cwd' in workflow
    assert '- key: app_identity' in workflow
    assert '- key: stop_cmd' in workflow
    assert '- key: boot_timeout' in workflow
    assert '- "{{ app_cwd }}"' in workflow
    assert '- "{{ app_identity }}"' in workflow
    assert '- "{{ boot_timeout }}"' in workflow
    assert '- "{{ stop_cmd }}"' in workflow
    assert '- "{{ current_item }}"' in workflow
    assert '- "{{ discovered | tojson }}"' in workflow
    assert "get_node_output('select_wt', 'current_item')" not in workflow


SCREENS = "docs/features/web/gui/screens"


def _screen(slug: str, *, vet: bool = False, interaction_vet: bool = False) -> list[dict]:
    """A screen file node, optionally registered — on itself or on a child interaction."""
    nid = f"{SCREENS}/{slug}.md"
    nodes = [{
        "id": nid, "type": "screen", "kind": "file", "title": slug.title(),
        "path": nid, "bullets": {"vet": "x"} if vet else {}, "edges": [],
    }]
    if interaction_vet:
        nodes.append({
            "id": f"{nid}#mount-load", "type": "interaction", "kind": "section",
            "title": "mount-load", "path": nid, "bullets": {"vet": "x"}, "edges": [],
        })
    return nodes


def _flow(slug: str, touches: list[str]) -> dict:
    path = f"docs/features/web/flows/{slug}.md"
    return {
        "id": path, "type": "flow", "kind": "file", "title": slug.title(), "path": path,
        "bullets": {},
        "edges": [{"to": f"{SCREENS}/{s}.md", "via": "steps", "text": s} for s in touches],
    }


def _seeded(seed, tmp_path: Path, monkeypatch, capsys, nodes: list[dict],
            items: list[dict] | None = None) -> tuple[dict, list[dict]]:
    worklist = tmp_path / "web.walkthrough.json"
    worklist.write_text(json.dumps({"items": items or []}))
    monkeypatch.setattr(seed, "_book", lambda *_a, **_k: {"nodes": nodes})
    monkeypatch.setattr(seed.sys, "argv", [
        "seed-walkthrough.py", str(worklist), "web", str(tmp_path),
    ])
    with pytest.raises(SystemExit, match="0"):
        seed.main(logging.getLogger("test"))
    return json.loads(capsys.readouterr().out), json.loads(worklist.read_text())["items"]


def test_seed_walkthrough_seeds_only_unconfirmed_screens(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """The walk's delta is missing evidence, not changed source: registered screens are skipped."""
    nodes = [*_screen("dashboard", vet=True), *_screen("archive")]
    result, items = _seeded(load_script("seed-walkthrough.py"), tmp_path, monkeypatch, capsys, nodes)

    assert [i["target"] for i in items] == [f"{SCREENS}/archive.md"]
    assert result["unconfirmed_count"] == 1
    assert result["screen_count"] == 2


def test_vet_on_an_interaction_registers_its_screen(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """A vet report describes a state, so the bullet lands on the interaction that renders it.

    Counting only the screen's file node would re-walk every screen an earlier run confirmed.
    """
    nodes = _screen("profile", interaction_vet=True)
    result, items = _seeded(load_script("seed-walkthrough.py"), tmp_path, monkeypatch, capsys, nodes)

    assert items == []
    assert result["unconfirmed_count"] == 0


def test_seed_walkthrough_reopens_only_journeys_touching_unconfirmed_screens(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """A journey whose screens are all registered stays done — re-running must not redo it."""
    nodes = [
        *_screen("dashboard", vet=True), *_screen("archive"),
        _flow("settled", ["dashboard"]),        # all confirmed -> leave alone
        _flow("pending-work", ["archive"]),     # touches an unconfirmed screen -> reopen
    ]
    done = [
        {"kind": "journey", "target": "flow:settled", "context": "Old", "status": "done"},
        {"kind": "journey", "target": "flow:pending-work", "context": "Old", "status": "done"},
    ]
    _result, items = _seeded(load_script("seed-walkthrough.py"), tmp_path, monkeypatch, capsys, nodes, done)

    by_target = {i["target"]: i for i in items}
    assert by_target["flow:settled"]["status"] == "done"
    assert by_target["flow:pending-work"]["status"] == "pending"
    assert by_target["flow:pending-work"]["context"] == "Pending-Work"


def test_seed_walkthrough_is_idempotent_against_evidence(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """Re-seeding an unchanged book adds nothing — the gap closes only as evidence lands."""
    seed = load_script("seed-walkthrough.py")
    nodes = [*_screen("archive")]
    first, _ = _seeded(seed, tmp_path, monkeypatch, capsys, nodes)
    assert first["added"] == 1

    worklist = tmp_path / "web.walkthrough.json"
    existing = json.loads(worklist.read_text())["items"]
    second, items = _seeded(seed, tmp_path, monkeypatch, capsys, nodes, existing)
    assert second["added"] == 0
    assert len(items) == 1


def test_seed_walkthrough_seeds_nothing_when_the_graph_will_not_load(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """An unloadable graph is not an empty book: seed nothing rather than declare the walk done."""
    seed = load_script("seed-walkthrough.py")
    worklist = tmp_path / "web.walkthrough.json"
    worklist.write_text(json.dumps({"items": [
        {"kind": "screen", "target": "x", "context": "c", "status": "pending"},
    ]}))
    monkeypatch.setattr(seed, "_book", lambda *_a, **_k: None)
    monkeypatch.setattr(seed.sys, "argv", [
        "seed-walkthrough.py", str(worklist), "web", str(tmp_path),
    ])
    with pytest.raises(SystemExit, match="0"):
        seed.main(logging.getLogger("test"))

    result = json.loads(capsys.readouterr().out)
    assert result["pending_count"] == 1  # the existing item is preserved, not dropped
    assert result["added"] == 0
