from __future__ import annotations

import io
import json
import subprocess
from typing import cast

import pytest

from ostler.qa.harness_host import load_harness_module

hierarchy = load_harness_module("ostler_qa_hierarchy")


class _StubMaestro:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.stdin = io.StringIO()
        self.stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in messages))
        self._stopped = False

    def poll(self) -> int | None:
        return 0 if self._stopped else None

    def kill(self) -> None:
        self._stopped = True

    def terminate(self) -> None:
        self._stopped = True

    def wait(self, timeout: float | None = None) -> int:
        return 0


def test_resident_reader_falls_back_to_inspect_screen_and_expands_ui_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    schema_reply = json.dumps({
        "ui_schema": {
            "platform": "android",
            "abbreviations": {
                "b": "bounds",
                "txt": "text",
                "rid": "resource-id",
                "a11y": "content-desc",
                "hint": "hintText",
                "cls": "class",
                "scroll": "scrollable",
                "c": "children",
            },
            "defaults": {"enabled": True, "txt": "", "hint": "", "rid": "", "a11y": "", "cls": ""},
        },
        "elements": [{
            "b": "[0,0][1080,2400]",
            "cls": "android.widget.FrameLayout",
            "c": [{
                "b": "[40,2000][1040,2160]",
                "rid": "com.example.app:id/submit",
                "a11y": "Get Started",
                "cls": "android.widget.Button",
            }],
        }],
    })
    messages: list[dict[str, object]] = [
        {"jsonrpc": "2.0", "id": 1, "result": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"isError": True, "content": [{"type": "text", "text": "Tool inspect_view_hierarchy not found"}]},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "content": [
                    {"type": "text", "text": "Maestro Viewer ready"},
                    {"type": "text", "text": schema_reply},
                ],
            },
        },
    ]
    stub = _StubMaestro(messages)
    reader = hierarchy.ResidentReader(lambda: cast(subprocess.Popen[str], stub), lambda timeout: "emulator-5554")
    monkeypatch.setattr(hierarchy, "RESIDENT", reader)

    parsed = json.loads(hierarchy.resident_reader(5))
    button = parsed["children"][0]["children"][0]["attributes"]
    assert button["accessibilityText"] == "Get Started"
    assert button["resource-id"] == "com.example.app:id/submit"
    assert button["enabled"] == "true"
