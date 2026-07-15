"""Test utilities for workflow authors.

Workflow authors write pytest files in a ``tests/`` subdirectory of their workflow
directory and import from this module to set up sandboxes, mock agents, and assert
on results. The engine runs **in-process** — no ``workhorse`` CLI subprocess, no
PATH shims:

- Agent nodes are answered by a :class:`_MockBackend` injected through
  ``RunConfig.backend_factory`` (``mock_agent`` / ``mock_agent_sequence``).
- Script nodes run **in the current process** via :class:`InProcessScriptRunner`
  (``runpy``), so a test can ``monkeypatch`` the ``workhorse.scriptutil`` helpers a
  script calls — e.g. patch ``scriptutil.github_client`` to intercept GitHub, with no
  ``gh`` CLI. Local ``git`` runs for real against a throwaway repo (:func:`make_git_repo`).

Example::

    from pathlib import Path
    from workhorse.testing import WorkflowRun, assert_step_output

    WORKFLOW = Path(__file__).parent.parent / "workflow.yaml"

    def test_select_story(tmp_path):
        (tmp_path / "docs" / "epics" / "epic-1").mkdir(parents=True)
        (tmp_path / "docs" / "epics" / "epics-todo.json").write_text('["epic-1"]')

        wf = WorkflowRun(WORKFLOW, tmp_path)
        wf.mock_agent("plan", {"plan_result": {"status": "done"}})
        result = wf.run()

        assert result.passed()
        assert_step_output(result, "select_story", "has_story", "yes")
"""

from __future__ import annotations

import io
import json
import os
import runpy
import signal
import subprocess
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config_run import AgentResilience, RunConfig
from .main import Workhorse
from .runner.agent import BackendInvocationError

__all__ = [
    "WorkflowRun",
    "RunResult",
    "InProcessScriptRunner",
    "make_git_repo",
    "assert_file",
    "assert_file_contains",
    "assert_json_file",
    "assert_step_output",
    "assert_prompt_contains",
    "assert_command_called",
]


# ── Real throwaway git repo ────────────────────────────────────────────────────

def make_git_repo(path: Path, *, name: str = "test") -> Path:
    """Initialise a minimal real git repo at ``path`` with one commit.

    Git operations are tested against a REAL (cheap) repo rather than a mocked
    ``git`` — the ``test_multi_repo_git`` pattern, generalised. Returns ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "t"],
    ):
        subprocess.run(cmd, cwd=str(path), check=True, capture_output=True)
    readme = path / "README.md"
    if not readme.exists():
        readme.write_text(f"# {name}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-qm", "init"], cwd=str(path), check=True, capture_output=True
    )
    return path


# ── In-process script runner ───────────────────────────────────────────────────


class _HarnessTimeout(Exception):
    """Internal signal used by WorkflowRun timeout compatibility."""

class InProcessScriptRunner:
    """Execute a Python script node IN THE CURRENT PROCESS via ``runpy``.

    Mirrors ``python <script.py> <argv>`` — sets ``sys.argv``, the cwd, ``os.environ``
    and ``sys.path[0]`` (so ``from lib import ...`` resolves), captures stdout/stderr,
    and translates ``SystemExit`` into a return code — all restored afterwards. Because
    the script's ``workhorse.scriptutil`` / ``lib.*`` calls happen in this process, a
    test can monkeypatch them (e.g. ``scriptutil.github_client``) to intercept external
    services without a PATH shim or CLI subprocess."""

    def run(
        self, script_path: Path, argv: list[str], cwd: str, env: dict[str, str]
    ) -> tuple[int, str, str]:
        old_argv = sys.argv[:]
        old_cwd = os.getcwd()
        old_env = os.environ.copy()
        old_path = sys.path[:]
        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            sys.argv = [str(script_path), *argv]
            os.chdir(cwd)
            os.environ.clear()
            os.environ.update(env)
            sys.path.insert(0, str(Path(script_path).parent))
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    runpy.run_path(str(script_path), run_name="__main__")
                except SystemExit as exc:
                    c = exc.code
                    code = 0 if c is None else (c if isinstance(c, int) else 1)
                except _HarnessTimeout:
                    raise
                except Exception as exc:  # noqa: BLE001 — surface a script crash as exit 1
                    code = 1
                    err.write(f"\n{type(exc).__name__}: {exc}\n")
                    traceback.print_exc(file=err)
        finally:
            sys.argv = old_argv
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(old_env)
            sys.path[:] = old_path
        return code, out.getvalue(), err.getvalue()


# ── Mock agent backend ─────────────────────────────────────────────────────────

class _MockBackend:
    """Answers agent nodes from per-node mocks instead of running an agent CLI.

    Injected via ``RunConfig.backend_factory``. Returns the mocked response text (so
    the engine's real output-extraction / reframe / default-outputs ladder runs on
    it), applies ``side_effects`` file writes, records each call to
    ``<test_dir>/calls/<cli>/`` for :meth:`RunResult.calls`, and drives ``_sequence``
    mocks off a per-node counter. A non-zero ``exit_code`` raises
    ``BackendInvocationError`` (a non-recoverable backend failure), so a test can
    exercise the failure path."""

    supports_compaction = False

    def __init__(self, cli: str, mocks: dict[str, Any], test_dir: Path) -> None:
        self.name = cli
        self.default_model = "mock-model"
        self._mocks = mocks
        self._test_dir = test_dir
        self._counts: dict[str, int] = {}

    def run_turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None = None,
        model: str | None = None,
        timeout: float = 0,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        idx = self._counts.get(node_id, 0)
        self._counts[node_id] = idx + 1
        self._record(node_id, prompt, cwd)

        cfg = self._mocks.get(node_id)
        if cfg is None:
            # No mock for this node — mirror the old shim's "return {}" so a node the
            # test didn't stub defaults its outputs rather than crashing the run.
            print(f"[test-mock] ⚠ no agent mock for node '{node_id}' — returning {{}}",
                  file=sys.stderr)
            return "{}"
        entry = cfg[min(idx, len(cfg) - 1)] if isinstance(cfg, list) else cfg
        for fx in entry.get("side_effects", []):
            p = Path(fx["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(fx["content"], encoding="utf-8")
        exit_code = entry.get("exit_code", 0)
        if exit_code != 0:
            raise BackendInvocationError(
                f"mock agent for node '{node_id}' exited {exit_code}", transient=False
            )
        return entry.get("response", "{}")

    def compact(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def _record(self, node_id: str, prompt: str, cwd: str | None) -> None:
        calls_dir = self._test_dir / "calls" / self.name
        calls_dir.mkdir(parents=True, exist_ok=True)
        seq = len(list(calls_dir.glob("*.json")))
        (calls_dir / f"{seq:06d}.json").write_text(
            json.dumps(
                {"seq": seq, "node_id": node_id, "args": [], "stdin": prompt,
                 "cwd": cwd or os.getcwd()},
                indent=2,
            ),
            encoding="utf-8",
        )


# ── RunResult ─────────────────────────────────────────────────────────────────

@dataclass
class RunResult:
    """The outcome of a :class:`WorkflowRun.run` call."""

    exit_code: int
    stdout: str
    stderr: str
    #: Directory holding workhorse run artifacts for this test
    runs_dir: Path
    #: Base test directory (parent of runs_dir); agent calls are recorded here
    test_dir: Path

    # ── Run dir resolution ────────────────────────────────────────────────────

    @property
    def run_dir(self) -> Path | None:
        """The single run directory created under ``runs_dir``, or None."""
        if not self.runs_dir.is_dir():
            return None
        candidates = [d for d in self.runs_dir.iterdir() if d.is_dir()]
        return max(candidates, key=lambda d: d.stat().st_mtime) if candidates else None

    def _node_artifact(self, node_id: str, filename: str) -> Path | None:
        """Locate ``<node_id>/<filename>`` for a node that may live at the top level
        OR inside a ``flows:`` sub-graph. A flow call writes its child nodes under a
        nested scope ``<flow_node>/_flow/<node_id>/…`` (flows may nest, giving
        ``…/_flow/…/_flow/<node_id>/…``). Node ids are unique across a workflow, so
        we prefer the top-level path and otherwise return the first match under any
        ``_flow`` scope — this keeps ``step_outputs``/``prompt`` working unchanged
        whether a node was hoisted into a flow or not."""
        rd = self.run_dir
        if rd is None:
            return None
        direct = rd / node_id / filename
        if direct.is_file():
            return direct
        # rglob finds every `_flow` scope at any nesting depth; a flow's immediate
        # child node sits directly under its scope dir.
        for flow_dir in sorted(rd.rglob("_flow")):
            cand = flow_dir / node_id / filename
            if cand.is_file():
                return cand
        return None

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
        """Outputs extracted by workhorse for ``node_id`` (``output.json``).

        Resolves the node whether it ran at the top level or inside a ``flows:``
        sub-graph (nested ``_flow`` scope)."""
        f = self._node_artifact(node_id, "output.json")
        if f is None:
            return {}
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def prompt(self, node_id: str) -> str:
        """Rendered prompt that was sent to the agent for ``node_id`` (top level or
        inside a ``flows:`` sub-graph)."""
        f = self._node_artifact(node_id, "prompt.md")
        return f.read_text(encoding="utf-8") if f is not None else ""

    def calls(self, command: str) -> list[dict[str, Any]]:
        """All recorded agent-backend invocations for ``command`` (the agent CLI
        name, e.g. ``'claude'``), sorted by seq. External-tool calls (git/gh/ostler)
        are asserted via the test's own monkeypatched fakes, not here."""
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
    """Run a workflow IN-PROCESS against an isolated sandbox directory.

    Layout under ``sandbox/.workhorse-test/``::

        calls/   recorded agent-backend invocations (by CLI name)
        runs/    workhorse run artifacts

    Agent nodes are answered by :class:`_MockBackend` (``mock_agent`` /
    ``mock_agent_sequence``); script nodes run via :class:`InProcessScriptRunner`.
    Point script-node repo resolution at the sandbox by seeding it as a real git repo
    (:func:`make_git_repo`) and passing ``docs_path`` / workspace params.
    """

    def __init__(self, workflow: str | Path, sandbox: Path, *, repo: Path | None = None) -> None:
        self._workflow = Path(workflow).resolve()
        self._sandbox = Path(sandbox)
        self._repo = Path(repo) if repo is not None else self._sandbox
        self._test_dir = self._sandbox / ".workhorse-test"
        self._runs_dir = self._test_dir / "runs"
        self._agent_mocks: dict[str, Any] = {}

    # ── Mocking ───────────────────────────────────────────────────────────────

    def mock_agent(
        self,
        node_id: str,
        response: str | dict,
        exit_code: int = 0,
        side_effects: list[dict] | None = None,
    ) -> None:
        """Return a fixed response for agent node ``node_id``.

        ``response`` is the text the agent returns (a dict is JSON-serialised).
        ``side_effects`` is a list of ``{"path": str, "content": str}`` written to
        disk after the response is chosen, simulating file-system changes the real
        agent would make (e.g. writing "QA passed" to story.md)."""
        if isinstance(response, dict):
            response = json.dumps(response)
        self._agent_mocks[node_id] = {
            "response": response, "exit_code": exit_code, "side_effects": side_effects or []
        }

    def mock_agent_sequence(
        self,
        node_id: str,
        responses: list[str | dict],
        exit_code: int = 0,
    ) -> None:
        """Return successive responses for repeated calls to agent node ``node_id``.

        The last entry repeats once the list is exhausted, so a two-element list
        tests one rework cycle. Each item may be a ``str``/``dict`` response, or a
        fully-specified ``{"response": ..., "exit_code": ..., "side_effects": ...}``
        dict (its ``exit_code`` overrides the keyword arg for that entry)."""
        cfg = []
        for resp in responses:
            if isinstance(resp, dict) and "response" in resp:
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
        self._agent_mocks[node_id] = cfg

    # ── Execution ─────────────────────────────────────────────────────────────

    def run(
        self,
        *,
        params: dict[str, Any] | None = None,
        flow: str | None = None,
        cli: str = "claude",
        config: RunConfig | None = None,
        timeout: float | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> RunResult:
        """Execute the workflow in-process and return a :class:`RunResult`.

        Pass ``flow`` to run a named ``flows:`` sub-graph standalone; ``params`` must
        then supply every var the flow requires. ``config`` overrides the default
        harness :class:`RunConfig` (e.g. to raise ``max_rephrase_attempts`` for a
        test that specifically exercises the reframe ladder)."""
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        backend = _MockBackend(cli, self._agent_mocks, self._test_dir)

        if config is None:
            # Neutralize the recovery sleeps: with no reframe/output retries a
            # parse-miss defaults instantly, and the cap/backoff waits are zeroed.
            # A test exercising the retry/reframe path passes its own `config`.
            resilience = AgentResilience.from_env().with_overrides(
                max_output_retries=0,
                max_rephrase_attempts=0,
                max_compact_attempts=0,
                invoke_backoff_base_s=0.0,
                cap_default_wait_s=0.0,
                result_timeout_s=30.0,
                use_default_outputs=True,
            )
            config = RunConfig(
                resilience=resilience,
                backend_factory=lambda _cli: backend,
                script_runner=InProcessScriptRunner(),
            )
        else:
            # Honor a caller-supplied config but still inject the mock backend and the
            # in-process runner unless the caller set them explicitly.
            replacements: dict[str, Any] = {}
            if config.backend_factory is None:
                replacements["backend_factory"] = lambda _cli: backend
            if config.script_runner is None:
                replacements["script_runner"] = InProcessScriptRunner()
            if replacements:
                from dataclasses import replace as _replace

                config = _replace(config, **replacements)

        # Script nodes resolve the repo root from AGENT_REPO_DIR and their cwd from
        # WORKHORSE_DEFAULT_SCRIPT_CWD; point both at the sandbox for the duration of
        # the run (scoped + restored, so the test author never sets env). The test
        # supplies everything else (docs_path, workspace) via `params`.
        out, err = io.StringIO(), io.StringIO()
        prior_env = os.environ.copy()
        os.environ["AGENT_REPO_DIR"] = str(self._repo)
        os.environ["WORKHORSE_DEFAULT_SCRIPT_CWD"] = str(self._sandbox)
        os.environ["AGENT_CLI"] = cli
        if extra_env:
            os.environ.update(extra_env)
        code = 0
        old_handler = None

        def _timeout_handler(signum, frame):  # noqa: ARG001
            raise _HarnessTimeout

        try:
            if timeout is not None:
                # Compatibility with the old subprocess harness. These timeouts are
                # only used by tests that intentionally park at an operator gate. Cap
                # them below the legacy subprocess value, but leave enough room for
                # xdist workers under load to reach the gate before the signal fires.
                old_handler = signal.getsignal(signal.SIGALRM)
                signal.signal(signal.SIGALRM, _timeout_handler)
                signal.setitimer(signal.ITIMER_REAL, min(float(timeout), 5.0))
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    code = Workhorse(config).run(
                        self._workflow,
                        self._runs_dir,
                        params=params,
                        flow=flow,
                    )
                except SystemExit as exc:
                    # A script node's non-zero exit propagates as SystemExit (e.g.
                    # await_operator exits 2); surface its code faithfully.
                    c = exc.code
                    code = 0 if c is None else (c if isinstance(c, int) else 1)
                except _HarnessTimeout:
                    code = -1
        finally:
            if timeout is not None:
                signal.setitimer(signal.ITIMER_REAL, 0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)
            os.environ.clear()
            os.environ.update(prior_env)

        return RunResult(
            exit_code=code,
            stdout=out.getvalue(),
            stderr=err.getvalue(),
            runs_dir=self._runs_dir,
            test_dir=self._test_dir,
        )


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
    """Assert that at least one recorded invocation of ``command`` had ``args_contain``
    in its args. (For agent CLIs; external tools are asserted via test fakes.)"""
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
