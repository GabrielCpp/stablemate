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


def test_boot_health_requires_documented_identity(monkeypatch) -> None:
    boot = load_script("boot-app.py")

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return b"<title>groom</title>"

    monkeypatch.setattr(boot.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    assert boot._health_ok("http://127.0.0.1:8787", "<title>Acme</title>") is False
    assert boot._health_ok("http://127.0.0.1:8787", "<title>groom</title>") is True


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


def test_boot_timeout_falls_back_when_undocumented_or_junk() -> None:
    boot = load_script("boot-app.py")

    assert boot._boot_timeout("1800") == 1800.0
    assert boot._boot_timeout("") == boot.BOOT_TIMEOUT_S
    assert boot._boot_timeout("soon") == boot.BOOT_TIMEOUT_S
    assert boot._boot_timeout("0") == boot.BOOT_TIMEOUT_S


def test_boot_treats_a_clean_exit_as_a_bring_up_command(tmp_path: Path, monkeypatch, capsys):
    """`make dev-stack-test-db` exits 0 once the stack serves — that is not death."""
    boot = load_script("boot-app.py")

    # Healthy only from the third poll: the stack comes up strictly after make returns,
    # so a run that failed on the clean exit would never see it.
    polls = {"n": 0}

    def health(*_args, **_kwargs) -> bool:
        polls["n"] += 1
        return polls["n"] >= 3

    class Exited:
        pid = 4242
        returncode = 0

        def poll(self) -> int:
            return 0

    monkeypatch.setattr(boot, "_health_ok", health)
    monkeypatch.setattr(boot.subprocess, "Popen", lambda *_a, **_kw: Exited())
    monkeypatch.setattr(boot.os, "getpgid", lambda _pid: 4242)
    monkeypatch.setattr(boot, "POLL_INTERVAL_S", 0)
    monkeypatch.setattr(boot.sys, "argv", [
        "boot-app.py", "make dev-stack-test-db", "http://localhost:3000", "/",
        str(tmp_path), str(tmp_path), "", "60",
    ])

    with pytest.raises(SystemExit):
        boot.main(logging.getLogger("boot-app"))

    out = json.loads(capsys.readouterr().out)
    assert out["boot_ok"] == "yes"
    # Owns nothing: the stack lives in containers, so teardown must not killpg 4242.
    assert out["app_pgid"] == ""
    assert out["app_pid"] == ""


def test_boot_still_fails_when_the_launch_command_errors(tmp_path: Path, monkeypatch, capsys):
    """A nonzero exit is a real death — the detached path must not swallow it."""
    boot = load_script("boot-app.py")

    class Died:
        pid = 4242
        returncode = 2

        def poll(self) -> int:
            return 2

    monkeypatch.setattr(boot, "_health_ok", lambda *_a, **_kw: False)
    monkeypatch.setattr(boot.subprocess, "Popen", lambda *_a, **_kw: Died())
    monkeypatch.setattr(boot.os, "getpgid", lambda _pid: 4242)
    monkeypatch.setattr(boot, "POLL_INTERVAL_S", 0)
    monkeypatch.setattr(boot.sys, "argv", [
        "boot-app.py", "make dev-stack-test-db", "http://localhost:3000", "/",
        str(tmp_path), str(tmp_path), "", "60",
    ])

    with pytest.raises(SystemExit):
        boot.main(logging.getLogger("boot-app"))

    assert json.loads(capsys.readouterr().out)["boot_ok"] == "no"


def test_teardown_without_a_pgid_runs_the_documented_stop_recipe(monkeypatch, capsys) -> None:
    calls: list[list[str]] = []

    boot = load_script("boot-app.py")

    class Done:
        returncode = 0
        stderr = ""

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return Done()

    monkeypatch.setattr(boot.subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        boot._teardown("", "make dev-stack-test-db-down", ".", logging.getLogger("boot-app"))

    assert calls == [["make", "dev-stack-test-db-down"]]
    assert json.loads(capsys.readouterr().out)["torn_down"] == "yes"


def test_teardown_leaves_the_stack_up_when_no_stop_recipe_is_documented(monkeypatch, capsys):
    """The chosen policy: an expensive shared stack is cheaper to leave running."""
    boot = load_script("boot-app.py")
    monkeypatch.setattr(boot.subprocess, "run", lambda *_a, **_kw: pytest.fail("ran a command"))

    with pytest.raises(SystemExit):
        boot._teardown("", "", ".", logging.getLogger("boot-app"))

    assert json.loads(capsys.readouterr().out)["torn_down"] == "skipped"


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


def test_seed_walkthrough_reopens_journeys_completed_by_an_earlier_run(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    seed = load_script("seed-walkthrough.py")
    worklist = tmp_path / "web.walkthrough.json"
    worklist.write_text(json.dumps({"items": [
        {
            "kind": "journey", "target": "flow:project-lifecycle",
            "context": "Old title", "status": "done",
        },
        {
            "kind": "screen", "target": "screen:dashboard",
            "context": "Already checked", "status": "done",
        },
    ]}))
    monkeypatch.setattr(seed, "_search_flows", lambda _root: [{
        "path": "docs/features/web/flows/project-lifecycle.md",
        "title": "Project lifecycle",
    }])
    monkeypatch.setattr(seed.sys, "argv", [
        "seed-walkthrough.py", str(worklist), "web", str(tmp_path),
    ])

    with pytest.raises(SystemExit, match="0"):
        seed.main(logging.getLogger("test"))

    result = json.loads(capsys.readouterr().out)
    items = json.loads(worklist.read_text())["items"]
    assert items[0]["status"] == "pending"
    assert items[0]["context"] == "Project lifecycle"
    assert items[1]["status"] == "done"
    assert result == {"done_count": 1, "pending_count": 1, "added": 1}
