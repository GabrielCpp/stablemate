"""Test utilities for workflow authors.

Workflow authors write pytest files in a ``tests/`` subdirectory of their workflow
directory and import from this module to set up sandboxes, install shims, and assert
on results.  The real ``workhorse`` CLI is invoked as a subprocess — no mocking of
workhorse internals.

Example::

    from pathlib import Path
    from workhorse.testing import WorkflowRun, assert_step_output, assert_json_file

    WORKFLOW = Path(__file__).parent.parent / "workflow.yaml"

    def test_select_story(tmp_path):
        epics = tmp_path / "docs" / "epics" / "epic-1"
        epics.mkdir(parents=True)
        (tmp_path / "docs" / "epics" / "epics-todo.json").write_text('["epic-1"]')
        ...

        wf = WorkflowRun(WORKFLOW, tmp_path)
        wf.mock_command("git", (0, ""))
        result = wf.run()

        assert result.passed()
        assert_step_output(result, "select_story", "has_story", "yes")
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "WorkflowRun",
    "RunResult",
    "assert_file",
    "assert_file_contains",
    "assert_json_file",
    "assert_step_output",
    "assert_prompt_contains",
    "assert_command_called",
]

# ── Shim scripts ──────────────────────────────────────────────────────────────

# The claude shim emits one stream-json result event per invocation.  Workhorse's
# _stream_events() in runner/agent.py looks for {"type": "result", ...} and
# extracts the "result" field as the agent response text.  The shim reads
# WORKHORSE_NODE_ID (injected by workhorse when it starts the claude subprocess)
# to look up the per-node mock and records every call so tests can inspect them.
_CLAUDE_SHIM = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

shim_dir = Path(os.environ.get("WORKHORSE_SHIM_DIR", ""))
node_id = os.environ.get("WORKHORSE_NODE_ID", "_unknown")
stdin_text = sys.stdin.read()

# Record call
calls_dir = shim_dir / "calls" / "claude"
calls_dir.mkdir(parents=True, exist_ok=True)
seq = len(list(calls_dir.glob("*.json")))
(calls_dir / f"{seq:06d}.json").write_text(
    json.dumps({"seq": seq, "node_id": node_id, "args": sys.argv[1:],
                "stdin": stdin_text, "cwd": os.getcwd()}, indent=2)
)

# Per-node call counter (drives sequence mocks)
counter_dir = shim_dir / "call_counts"
counter_dir.mkdir(parents=True, exist_ok=True)
counter_file = counter_dir / f"{node_id}.txt"
call_idx = int(counter_file.read_text().strip()) if counter_file.exists() else 0
counter_file.write_text(str(call_idx + 1))

# Look up mock
mock_file = shim_dir / "agent_mocks" / f"{node_id}.json"
if mock_file.exists():
    cfg = json.loads(mock_file.read_text())
    # Sequence support: cfg may be a list [{response, exit_code}, ...];
    # the last entry repeats once the list is exhausted.
    if isinstance(cfg, list):
        entry = cfg[min(call_idx, len(cfg) - 1)]
    else:
        entry = cfg
    response_text = entry.get("response", "{}")
    exit_code = entry.get("exit_code", 0)
    side_effects = entry.get("side_effects", [])
else:
    print(f"[test-shim] ⚠ no agent mock for node '{node_id}' — returning {{}}",
          file=sys.stderr)
    response_text = "{}"
    exit_code = 0
    side_effects = []

# Execute side effects (file writes) BEFORE emitting — simulates agent file I/O
for fx in side_effects:
    try:
        p = Path(fx["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(fx["content"], encoding="utf-8")
    except Exception as exc:
        print(f"[test-shim] ⚠ side_effect write failed: {exc}", file=sys.stderr)

# Emit the stream-json result event workhorse expects
print(json.dumps({
    "type": "result",
    "subtype": "success",
    "result": response_text,
    "is_error": False,
    "session_id": "test-session",
    "cost_usd": 0,
    "duration_ms": 1,
    "usage": {"input_tokens": 0, "cache_creation_input_tokens": 0,
              "cache_read_input_tokens": 0, "output_tokens": 0},
}))
sys.exit(exit_code)
"""

# Generic command shim template.  {cmd_name} is replaced at write time.
_COMMAND_SHIM_TEMPLATE = r"""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

CMD_NAME = {cmd_name!r}

shim_dir = Path(os.environ.get("WORKHORSE_SHIM_DIR", ""))
node_id = os.environ.get("WORKHORSE_NODE_ID", "_unknown")
try:
    stdin_text = sys.stdin.read() if not sys.stdin.isatty() else ""
except Exception:
    stdin_text = ""

# Record call
calls_dir = shim_dir / "calls" / CMD_NAME
calls_dir.mkdir(parents=True, exist_ok=True)
seq = len(list(calls_dir.glob("*.json")))
(calls_dir / f"{seq:06d}.json").write_text(
    json.dumps({"seq": seq, "node_id": node_id, "args": sys.argv[1:],
                "stdin": stdin_text, "cwd": os.getcwd()}, indent=2)
)

# Look up mock
mock_file = shim_dir / "command_mocks" / f"{CMD_NAME}.json"
if not mock_file.exists():
    print(f"[test-shim] ⚠ no mock for command '{CMD_NAME}'", file=sys.stderr)
    sys.exit(0)

cfg = json.loads(mock_file.read_text())
first_arg = sys.argv[1] if len(sys.argv) > 1 else ""

# cfg is either a single {exit_code, stdout} dict or a per-first-arg dispatch dict
if isinstance(cfg, dict) and ("exit_code" in cfg or "stdout" in cfg):
    stdout = cfg.get("stdout", "")
    if stdout:
        sys.stdout.write(stdout)
    sys.exit(cfg.get("exit_code", 0))
elif isinstance(cfg, dict):
    entry = cfg.get(first_arg) or cfg.get("*")
    if entry:
        stdout = entry.get("stdout", "")
        if stdout:
            sys.stdout.write(stdout)
        sys.exit(entry.get("exit_code", 0))
    sys.exit(0)
else:
    sys.exit(0)
"""


def _write_shim(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


# ── RunResult ─────────────────────────────────────────────────────────────────

@dataclass
class RunResult:
    """The outcome of a :class:`WorkflowRun.run` call."""

    exit_code: int
    stdout: str
    stderr: str
    #: Directory holding workhorse run artifacts for this test
    runs_dir: Path
    #: Base test directory (parent of runs_dir); shim calls are recorded here
    test_dir: Path

    # ── Run dir resolution ────────────────────────────────────────────────────

    @property
    def run_dir(self) -> Path | None:
        """The single run directory created under ``runs_dir``, or None."""
        if not self.runs_dir.is_dir():
            return None
        candidates = [d for d in self.runs_dir.iterdir() if d.is_dir()]
        return max(candidates, key=lambda d: d.stat().st_mtime) if candidates else None

    # ── Inspection ────────────────────────────────────────────────────────────

    def passed(self) -> bool:
        return self.exit_code == 0

    def context(self) -> dict[str, Any]:
        """Final workflow context (``context.json``) or last checkpoint context."""
        rd = self.run_dir
        if rd is None:
            return {}
        for fname in ("context.json", "checkpoint.json"):
            f = rd / fname
            if f.is_file():
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    # checkpoint.json wraps context under a "context" key
                    return data.get("context", data) if isinstance(data, dict) else {}
                except json.JSONDecodeError:
                    pass
        return {}

    def step_outputs(self, node_id: str) -> dict[str, Any]:
        """Outputs extracted by workhorse for ``node_id`` (``output.json``)."""
        rd = self.run_dir
        if rd is None:
            return {}
        f = rd / node_id / "output.json"
        if not f.is_file():
            return {}
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def prompt(self, node_id: str) -> str:
        """Rendered prompt that was sent to the agent for ``node_id``."""
        rd = self.run_dir
        if rd is None:
            return ""
        f = rd / node_id / "prompt.md"
        return f.read_text(encoding="utf-8") if f.is_file() else ""

    def calls(self, command: str) -> list[dict[str, Any]]:
        """All recorded shim invocations for ``command``, sorted by seq."""
        calls_dir = self.test_dir / "calls" / command
        if not calls_dir.is_dir():
            return []
        result = []
        for f in sorted(calls_dir.glob("*.json")):
            try:
                result.append(json.loads(f.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        return result

    def has_warning(self, text: str) -> bool:
        """True if ``text`` appears anywhere in stdout or stderr."""
        return text in self.stdout or text in self.stderr

    def output_lines(self) -> list[str]:
        return self.stdout.splitlines()


# ── WorkflowRun ───────────────────────────────────────────────────────────────

class WorkflowRun:
    """Invoke the real ``workhorse`` CLI against an isolated sandbox directory.

    Layout under ``sandbox/.workhorse-test/``::

        bin/          shim executables (prepended to PATH)
        agent_mocks/  per-node mock config (written by mock_agent)
        command_mocks/  per-command mock config (written by mock_command)
        calls/        recorded shim invocations
        runs/         workhorse run artifacts (--runs-dir)
    """

    def __init__(self, workflow: str | Path, sandbox: Path) -> None:
        self._workflow = Path(workflow).resolve()
        self._sandbox = sandbox
        self._test_dir = sandbox / ".workhorse-test"
        self._shim_bin = self._test_dir / "bin"
        self._agent_mocks_dir = self._test_dir / "agent_mocks"
        self._command_mocks_dir = self._test_dir / "command_mocks"
        self._runs_dir = self._test_dir / "runs"

    # ── Mocking ───────────────────────────────────────────────────────────────

    def mock_agent(
        self,
        node_id: str,
        response: str | dict,
        exit_code: int = 0,
        side_effects: list[dict] | None = None,
    ) -> None:
        """Return a fixed response for agent node ``node_id``.

        ``response`` is the text the agent returns.  If a dict, it is
        JSON-serialised automatically.  The ``claude`` shim is written to the
        shim bin when :meth:`run` is called.

        ``side_effects`` is a list of ``{"path": str, "content": str}`` dicts
        that the shim writes to disk after returning the response, simulating
        file-system changes the real agent would make (e.g. writing "QA passed"
        to story.md).
        """
        if isinstance(response, dict):
            response = json.dumps(response)
        self._agent_mocks_dir.mkdir(parents=True, exist_ok=True)
        (self._agent_mocks_dir / f"{node_id}.json").write_text(
            json.dumps(
                {"response": response, "exit_code": exit_code,
                 "side_effects": side_effects or []},
                indent=2,
            ),
            encoding="utf-8",
        )

    def mock_agent_sequence(
        self,
        node_id: str,
        responses: list[str | dict],
        exit_code: int = 0,
    ) -> None:
        """Return successive responses for repeated calls to agent node ``node_id``.

        The last entry repeats once the list is exhausted, so a two-element list
        tests one rework cycle: first call gets ``responses[0]``, all subsequent
        calls get ``responses[1]``.

        Each item in ``responses`` may be:
        - a ``str`` or ``dict`` — the response text (exit_code from the keyword arg)
        - a ``dict`` with ``"response"`` and optional ``"exit_code"`` / ``"side_effects"``
          keys — a fully-specified entry (exit_code keyword arg is ignored for that entry)
        """
        cfg = []
        for resp in responses:
            if isinstance(resp, dict) and "response" in resp:
                # Fully-specified entry: {"response": ..., "exit_code": ..., "side_effects": ...}
                entry_resp = resp["response"]
                if isinstance(entry_resp, dict):
                    entry_resp = json.dumps(entry_resp)
                cfg.append({
                    "response": entry_resp,
                    "exit_code": resp.get("exit_code", exit_code),
                    "side_effects": resp.get("side_effects", []),
                })
            else:
                if isinstance(resp, dict):
                    resp = json.dumps(resp)
                cfg.append({"response": resp, "exit_code": exit_code, "side_effects": []})
        self._agent_mocks_dir.mkdir(parents=True, exist_ok=True)
        (self._agent_mocks_dir / f"{node_id}.json").write_text(
            json.dumps(cfg, indent=2),
            encoding="utf-8",
        )

    def mock_command(
        self,
        name: str,
        response: tuple[int, str] | dict[str, tuple[int, str]],
    ) -> None:
        """Install a PATH shim for ``name`` (e.g. ``'git'``, ``'gh'``).

        Pass a single ``(exit_code, stdout)`` tuple to respond identically to
        all invocations, or a dict mapping first-arg (or ``'*'``) to
        ``(exit_code, stdout)``.
        """
        self._command_mocks_dir.mkdir(parents=True, exist_ok=True)
        if isinstance(response, tuple):
            exit_code, stdout = response
            config: dict = {"exit_code": exit_code, "stdout": stdout}
        else:
            config = {
                k: {"exit_code": v[0], "stdout": v[1]}
                for k, v in response.items()
            }
        (self._command_mocks_dir / f"{name}.json").write_text(
            json.dumps(config, indent=2),
            encoding="utf-8",
        )

    # ── Execution ─────────────────────────────────────────────────────────────

    def run(
        self,
        *,
        params: dict[str, Any] | None = None,
        cli: str = "claude",
        timeout: float = 120,
        extra_env: dict[str, str] | None = None,
    ) -> RunResult:
        """Execute ``workhorse --workflow <path>`` as a subprocess.

        Environment (in precedence order, highest last):
        - Inherited from the calling process (``os.environ``)
        - ``extra_env`` — additional variables injected by the test (e.g.
          ``{"GH_TOKEN": "fake-token"}`` to enable CI-gate code paths)
        - Fixed test harness variables (PATH shim, AGENT_CLI, WORKHORSE_*)
        """
        self._setup_shims(cli)

        cmd = ["workhorse", "--workflow", str(self._workflow),
               "--runs-dir", str(self._runs_dir)]
        if params:
            cmd += ["--params", json.dumps(params)]

        env = {
            **os.environ,
            **(extra_env or {}),
            "PATH": str(self._shim_bin) + os.pathsep + os.environ.get("PATH", ""),
            "AGENT_CLI": cli,
            "WORKHORSE_SHIM_DIR": str(self._test_dir),
            "WORKHORSE_DEFAULT_SCRIPT_CWD": str(self._sandbox),
            # Pin the repo root to the sandbox so scripts that resolve it via
            # AGENT_REPO_DIR (every git-touching script: branch-*, commit-*,
            # *-pr.sh, merge-pr.sh, push-*.sh) operate ON THE SANDBOX, never on the
            # workflow library's own checkout. Without this a script that runs real
            # `git` (a test that doesn't mock it) would fall back to walking up from
            # its own location and mutate the library repo (cut branches, commit). The
            # sandbox is not a git repo unless the test makes one, so unmocked git
            # fails harmlessly instead of corrupting the library.
            "AGENT_REPO_DIR": str(self._sandbox),
        }

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self._sandbox),
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            stderr = (e.stderr or b"").decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
            return RunResult(
                exit_code=-1,
                stdout=stdout,
                stderr=f"[workhorse.testing] timed out after {timeout}s\n{stderr}",
                runs_dir=self._runs_dir,
                test_dir=self._test_dir,
            )

        return RunResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            runs_dir=self._runs_dir,
            test_dir=self._test_dir,
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _setup_shims(self, cli: str) -> None:
        """Write shim executables to shim_bin."""
        self._shim_bin.mkdir(parents=True, exist_ok=True)

        # Agent CLI shim: always install as 'claude'.  If a different CLI is chosen,
        # also install under that name so the correct binary is found in PATH.
        for name in sorted({"claude", cli}):
            _write_shim(self._shim_bin / name, _CLAUDE_SHIM)

        # Command shims for every entry in command_mocks/
        if self._command_mocks_dir.is_dir():
            for mock_file in self._command_mocks_dir.glob("*.json"):
                name = mock_file.stem
                shim_content = _COMMAND_SHIM_TEMPLATE.replace("{cmd_name!r}", repr(name))
                _write_shim(self._shim_bin / name, shim_content)


# ── Assertion helpers ─────────────────────────────────────────────────────────

def assert_file(sandbox: Path, rel: str) -> None:
    """Assert that ``sandbox / rel`` exists."""
    path = sandbox / rel
    assert path.exists(), f"Expected file {rel!r} to exist in sandbox, but it does not"


def assert_file_contains(sandbox: Path, rel: str, text: str) -> None:
    """Assert that ``sandbox / rel`` exists and contains ``text``."""
    path = sandbox / rel
    assert path.exists(), f"Expected file {rel!r} to exist in sandbox, but it does not"
    content = path.read_text(encoding="utf-8")
    assert text in content, (
        f"Expected {rel!r} to contain {text!r}\n"
        f"Actual content:\n{content}"
    )


def assert_json_file(sandbox: Path, rel: str, subset: dict | list) -> None:
    """Assert that ``sandbox / rel`` is valid JSON matching ``subset``.

    For dicts: every key/value pair in ``subset`` must be present with equal values.
    For lists: the parsed JSON must equal ``subset`` exactly.
    """
    path = sandbox / rel
    assert path.exists(), f"Expected JSON file {rel!r} to exist in sandbox, but it does not"
    try:
        actual = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AssertionError(f"File {rel!r} is not valid JSON: {e}") from e
    if isinstance(subset, list):
        assert actual == subset, (
            f"Expected {rel!r} to equal {subset!r}\nActual: {actual!r}"
        )
    else:
        for key, expected_val in subset.items():
            assert key in actual, (
                f"Expected key {key!r} in {rel!r}\nActual keys: {list(actual)}"
            )
            assert actual[key] == expected_val, (
                f"Expected {rel!r}[{key!r}] == {expected_val!r}\nActual: {actual[key]!r}"
            )


def assert_step_output(
    result: RunResult, node_id: str, key: str, expected: Any
) -> None:
    """Assert that ``result.step_outputs(node_id)[key] == expected``."""
    outputs = result.step_outputs(node_id)
    assert key in outputs, (
        f"Expected output key {key!r} for node {node_id!r}\n"
        f"Available keys: {list(outputs)}\n"
        f"Workhorse stdout:\n{result.stdout[-2000:]}"
    )
    actual = outputs[key]
    assert actual == expected, (
        f"Node {node_id!r} output {key!r}: expected {expected!r}, got {actual!r}"
    )


def assert_prompt_contains(result: RunResult, node_id: str, text: str) -> None:
    """Assert that the rendered prompt sent to agent node ``node_id`` contains ``text``."""
    prompt = result.prompt(node_id)
    assert prompt, (
        f"No prompt.md found for node {node_id!r} "
        f"(run_dir={result.run_dir})"
    )
    assert text in prompt, (
        f"Expected prompt for {node_id!r} to contain {text!r}\n"
        f"Prompt (first 500 chars):\n{prompt[:500]}"
    )


def assert_command_called(
    result: RunResult, command: str, args_contain: str
) -> None:
    """Assert that at least one invocation of ``command`` had ``args_contain`` in its args."""
    calls = result.calls(command)
    assert calls, (
        f"Command {command!r} was never called\n"
        f"Workhorse stdout:\n{result.stdout[-2000:]}"
    )
    found = any(
        args_contain in arg
        for call in calls
        for arg in call.get("args", [])
    )
    assert found, (
        f"Expected command {command!r} to be called with args containing {args_contain!r}\n"
        f"Actual calls:\n"
        + "\n".join(f"  {c.get('args', [])}" for c in calls)
    )
