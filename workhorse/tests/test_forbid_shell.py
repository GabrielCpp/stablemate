"""Shell script nodes are rejected — at load (ScriptNode validator) and at run
(the script runner's interpreter gate). Only Python script nodes are supported,
because the in-process test runner executes the script module directly.

    ./.venv/bin/python tests/test_forbid_shell.py
    ./.venv/bin/python -m pytest tests/test_forbid_shell.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workhorse.graph.nodes import ScriptNode
from workhorse.runner.script import ScriptExitError, _interpreter_cmd


def test_scriptnode_rejects_sh():
    with pytest.raises(ValueError, match="shell scripts are not supported"):
        ScriptNode(type="script", id="n", script="scripts/setup.sh")


def test_scriptnode_rejects_bash():
    with pytest.raises(ValueError, match="shell scripts are not supported"):
        ScriptNode(type="script", id="n", script="scripts/x.bash")


def test_scriptnode_accepts_py():
    node = ScriptNode(type="script", id="n", script="scripts/setup.py")
    assert node.script == "scripts/setup.py"


def test_interpreter_gate_rejects_sh():
    with pytest.raises(ScriptExitError):
        _interpreter_cmd(Path("scripts/setup.sh"))


def test_interpreter_cmd_python():
    cmd = _interpreter_cmd(Path("/tmp/x.py"))
    assert cmd[0].endswith("python") or "python" in cmd[0]
    assert cmd[1] == "/tmp/x.py"


if __name__ == "__main__":
    import sys

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    sys.exit(1 if failed else 0)
