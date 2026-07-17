"""Tests for running script nodes in-process (runner/script.InProcessScriptRunner).

Script nodes used to be spawned as child processes, which made them the one part
of a run telemetry could not see: a child has no ``otel._active``, so its spans
were inert and its logs died on a pipe that was consumed whole as JSON. They now
run here, and ``main(logger)`` is the entry point.

The invariant under test throughout is that a script cannot tell the difference:
argv, cwd, env and sys.path[0] all still look like ``python <script.py> <args>``,
``SystemExit`` is still a return code and not a crashed run, and stdout is still
the data channel. Runnable two ways:
    ./.venv/bin/python -m pytest tests/test_script_inprocess.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from workhorse.runner import script as script_runner
from workhorse.runner.script import InProcessScriptRunner, default_script_runner


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _run(path: Path, argv=(), cwd=None, env=None, node_id="n"):
    runner = InProcessScriptRunner()
    return runner.run(
        path, list(argv), str(cwd or path.parent), dict(env or os.environ), node_id
    )


def test_main_receives_the_logger(tmp_path, caplog):
    """The new contract: a script declaring main(logger) is handed one."""
    path = _write(tmp_path, "s.py", "import json\n"
                  "def main(logger):\n"
                  "    logger.warning('script said something')\n"
                  "    print(json.dumps({'ok': 1}))\n")
    with caplog.at_level(logging.WARNING):
        code, out, _err = _run(path, node_id="pick_item")
    assert code == 0
    assert out.strip() == '{"ok": 1}'
    assert "script said something" in caplog.text
    # Named per node, so console output says which script spoke.
    assert any(r.name == "script.pick_item" for r in caplog.records)


def test_legacy_main_without_a_logger_still_runs():
    """Every script in the library predates main(logger) and declares `def main()`,
    as does anything in a private overlay this repo cannot see. Passing them a
    logger would break all of them at once, so the signature decides."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = _write(Path(td), "s.py", "import json, sys\n"
                      "def main():\n"
                      "    print(json.dumps({'ok': 'legacy'}))\n"
                      "if __name__ == '__main__':\n"
                      "    main()\n")
        code, out, _err = _run(path)
    assert code == 0
    # Exactly once: the guard must NOT also fire, or the script runs twice and any
    # side effect (a commit, a counter bump) is duplicated.
    assert out.count("legacy") == 1


def test_script_with_no_main_runs_at_top_level():
    """The 19 library scripts that are pure top-level code have no main to call;
    they must still execute, under __main__ as before."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = _write(Path(td), "s.py", "import json\nprint(json.dumps({'ok': 'top'}))\n")
        code, out, _err = _run(path)
    assert code == 0
    assert "top" in out


def test_sys_exit_is_a_return_code_not_a_dead_run():
    """await_operator exits 2 to mean 'operator input required'; the engine maps
    that to its own exit code. In-process, SystemExit must therefore be caught —
    unhandled it would tear down the whole run instead of ending one node."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = _write(Path(td), "s.py", "import sys\n"
                      "def main(logger):\n"
                      "    sys.exit(2)\n")
        code, _out, _err = _run(path)
    assert code == 2


def test_emit_style_exit_zero_keeps_its_stdout():
    """The library's `emit()` helper prints JSON then sys.exit(0) from inside main —
    normal control flow here, not an error. The payload printed before the exit
    must survive, or every script using emit() loses its outputs."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = _write(Path(td), "s.py", "import json, sys\n"
                      "def emit(**kw):\n"
                      "    print(json.dumps(kw))\n"
                      "    sys.exit(0)\n"
                      "def main(logger):\n"
                      "    emit(has_item='yes')\n")
        code, out, _err = _run(path)
    assert code == 0
    assert '"has_item": "yes"' in out


def test_a_crash_is_exit_1_with_a_traceback_not_a_raise():
    """A script that raises must come back as a failed node, exactly as a crashing
    child process did — not propagate into the engine's own stack."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = _write(Path(td), "s.py", "def main(logger):\n"
                      "    raise ValueError('boom')\n")
        code, _out, err = _run(path)
    assert code == 1
    assert "ValueError: boom" in err
    assert "Traceback" in err


def test_int_return_from_main_is_the_exit_code():
    """`sys.exit(main())` is one of the two guard shapes in the library, so an int
    return has to mean the same thing when workhorse calls main itself."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = _write(Path(td), "s.py", "def main(logger):\n    return 3\n")
        code, _out, _err = _run(path)
    assert code == 3


def test_argv_cwd_and_env_look_like_a_subprocess(tmp_path):
    """The isolation contract: a script must not be able to tell it was imported."""
    work = tmp_path / "work"
    work.mkdir()
    path = _write(tmp_path, "s.py", "import json, os, sys\n"
                  "def main(logger):\n"
                  "    print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(),\n"
                  "                      'env': os.environ.get('MY_VAR'),\n"
                  "                      'path0': sys.path[0]}))\n")
    code, out, _err = _run(path, argv=["a", "b"], cwd=work, env={"MY_VAR": "set"})
    assert code == 0
    got = __import__("json").loads(out)
    assert got["argv"] == ["a", "b"]
    assert got["cwd"] == os.path.realpath(str(work))
    assert got["env"] == "set"
    # CPython puts a script's own dir on sys.path[0]; a sibling `from lib import ...`
    # resolved as a subprocess and must keep resolving here.
    assert got["path0"] == str(tmp_path)


def test_process_state_is_restored_after_the_script(tmp_path):
    """The flip side of the above: the engine shares this process, so a script that
    chdirs or edits os.environ must not leak that into the next node."""
    before_cwd, before_argv = os.getcwd(), sys.argv[:]
    before_env = os.environ.copy()
    work = tmp_path / "w"
    work.mkdir()
    path = _write(tmp_path, "s.py", "import os\n"
                  "def main(logger):\n"
                  "    os.chdir('/')\n"
                  "    os.environ['LEAKED'] = 'yes'\n")
    _run(path, argv=["x"], cwd=work, env={**os.environ, "TEMP_VAR": "1"})
    assert os.getcwd() == before_cwd
    assert sys.argv == before_argv
    assert os.environ.get("LEAKED") is None
    assert os.environ.get("TEMP_VAR") is None
    assert dict(os.environ) == dict(before_env)


def test_stdout_is_data_and_logs_bypass_it(tmp_path, caplog):
    """stdout is the node's JSON payload, so it is captured — but the console
    handler holds the real stderr from before that capture, which is what keeps a
    script's logs on the terminal instead of swallowing them into the JSON parse."""
    path = _write(tmp_path, "s.py", "import json\n"
                  "def main(logger):\n"
                  "    logger.info('diagnostic')\n"
                  "    print(json.dumps({'k': 'v'}))\n")
    with caplog.at_level(logging.INFO):
        code, out, _err = _run(path)
    assert code == 0
    # The log line must NOT be in stdout — that would make the outputs unparseable.
    assert "diagnostic" not in out
    assert out.strip() == '{"k": "v"}'
    assert "diagnostic" in caplog.text


def test_module_state_does_not_leak_between_runs(tmp_path):
    """okf-builder loops over select_item, so the same script runs many times in one
    process. Module-level state surviving between visits would make visit N+1
    behave differently from visit 1 — a bug a subprocess could never have."""
    counter = tmp_path / "count.txt"
    path = _write(tmp_path, "s.py", "import json\n"
                  "SEEN = []\n"
                  "def main(logger):\n"
                  "    SEEN.append(1)\n"
                  "    print(json.dumps({'seen': len(SEEN)}))\n")
    outs = [_run(path)[1] for _ in range(3)]
    assert [__import__("json").loads(o)["seen"] for o in outs] == [1, 1, 1], (
        f"module state leaked across runs: {outs}"
    )
    assert not counter.exists()


def test_default_runner_is_in_process_and_env_switches_it_back(monkeypatch):
    """The production default itself — the gap that let the in-process runner ship
    as dead code. RunConfig.get_script_runner() and run_script() each used to pick a
    default independently, so the engine always took the config's; every test
    injected a runner and none exercised the real path."""
    monkeypatch.setattr(script_runner, "_INPROCESS", True)
    assert isinstance(default_script_runner(), InProcessScriptRunner)

    from workhorse.config_run import RunConfig

    assert isinstance(RunConfig().get_script_runner(), InProcessScriptRunner)

    monkeypatch.setattr(script_runner, "_INPROCESS", False)
    assert isinstance(default_script_runner(), script_runner.SubprocessScriptRunner)
    assert isinstance(
        RunConfig().get_script_runner(), script_runner.SubprocessScriptRunner
    )


def test_non_python_script_is_rejected_with_the_escape_hatch(tmp_path):
    """A subprocess would honor a shebang; an import cannot. Say so, and name the
    way out, rather than failing with a SyntaxError from ast.parse."""
    path = _write(tmp_path, "s.sh", "#!/bin/bash\necho hi\n")
    try:
        _run(path)
    except script_runner.ScriptExitError as exc:
        assert "WORKHORSE_SCRIPT_INPROCESS=0" in str(exc)
    else:
        raise AssertionError("a .sh script must be rejected, not imported")


if __name__ == "__main__":
    import subprocess

    raise SystemExit(
        subprocess.call([sys.executable, "-m", "pytest", "-q", __file__])
    )
