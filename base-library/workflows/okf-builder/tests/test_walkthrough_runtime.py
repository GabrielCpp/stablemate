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


def test_walkthrough_uses_runtime_contract_and_current_flow_outputs() -> None:
    workflow = WORKFLOW.read_text()

    assert '- key: app_cwd' in workflow
    assert '- key: app_identity' in workflow
    assert '- "{{ app_cwd }}"' in workflow
    assert '- "{{ app_identity }}"' in workflow
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
