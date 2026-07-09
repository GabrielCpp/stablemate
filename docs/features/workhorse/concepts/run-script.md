---
type: concept
slug: run-script
title: run_script — execute a script node
---
# run_script — execute a script node

The handler [workflow execution](workflow.md#execution)'s `ScriptNode` branch calls: renders a
[`ScriptNode`](../workflow-format.md#script)'s `args`/`cwd`/`env` via
[`render_string`](render-prompt.md#render_string-sibling), runs its `script` as a subprocess with an
interpreter prefix chosen from the file extension, and captures one JSON object from its stdout as
the node's `outputs` via [`_extract_outputs`](#_extract_outputsstdout-node-private).

- code: `workhorse/workhorse/runner/script.py::run_script`

## Contract

- **Input:**
  - `node: ScriptNode` — supplies `node.script` (path, relative to `workflow_dir`), `node.args`
    (Jinja2 template strings, positional), `node.cwd` (optional Jinja2 template for the subprocess
    working directory), `node.env` (Jinja2-templated extra env vars), and `node.outputs`
    (`list[OutputSpec]`, the keys to pull out of stdout — see
    [`OutputSpec`](../workflow-format.md#outputspec)).
  - `context: WorkflowContext` — rendered via [`as_dict()`](workflow-context.md#as_dict---dict) once
    into `ctx`, the base every `render_string` call in this function renders against.
  - `workflow_dir: Path` — the workflow's own directory; `node.script` is resolved relative to it,
    and it is the last-resort fallback for the subprocess `cwd`.
  - `graph_env: dict[str, str] | None` — the [`Workflow`](workflow.md#context--vars-and-env)-level
    `env` map from the containing graph, merged in **before** `node.env` so a node's own `env` key
    overrides the graph-level default for the same key.
- **Output:** `(cmd_str, outputs)` — `cmd_str: str` is the assembled command joined with spaces (the
  string [written to the run artifact](artifact-writer.md#write_stepnode_id-prompt-output-context_after-next_nodenone),
  not re-parsed or re-executed); `outputs: dict[str, Any]` is
  [`_extract_outputs`](#_extract_outputsstdout-node-private)'s result.
- **Raises:** `ScriptExitError(script, exit_code, stderr)` when the subprocess exits non-zero — the
  [workflow execution loop](workflow.md#execution) catches this specifically and turns it into
  `sys.exit(exit_code)`, ending the whole run process rather than propagating like other exceptions
  (so a script's own chosen exit code — e.g. `2` for "operator input required" vs. `1` for a crash —
  reaches the process's exit status faithfully). A malformed-JSON or missing-key stdout instead
  raises a plain `RuntimeError` from `_extract_outputs`, which the loop's generic `except Exception`
  branch logs and re-raises (uncaught by `run_script` itself).

## Algorithm

1. **Render the context once.** `ctx = context.as_dict()` — every subsequent `render_string` call in
   this function renders against this one snapshot; a script node never sees context mutations made
   by its own args/env rendering.
2. **Resolve the script path.** `script_path = workflow_dir / node.script`.
3. **Render `args`.** `rendered_args = [render_string(arg, ctx) for arg in node.args]` — each
   template string in `node.args` (an ordered list, unlike an agent node's `args` dict) becomes one
   positional argument to the subprocess, in declaration order.
4. **Resolve the working directory**, first match wins:
   1. `render_string(node.cwd, ctx).strip()` if `node.cwd` is set and renders non-empty.
   2. Else the `WORKHORSE_DEFAULT_SCRIPT_CWD` environment variable, if set — a hook the
      [test sandbox](testing.md) injects (`WORKHORSE_SHIM_DIR`/`WORKHORSE_DEFAULT_SCRIPT_CWD`), not
      normally set in production.
   3. Else `str(workflow_dir)`.
5. **Choose the interpreter prefix from the script's file suffix** (case-insensitive), so a script
   need not be marked executable on disk:
   - `.py` → `[sys.executable, str(script_path), *rendered_args]`.
   - `.sh` / `.bash` → `["bash", str(script_path), *rendered_args]`.
   - anything else → `[str(script_path), *rendered_args]` (invoked directly; must be executable).
   `cmd_str = " ".join(cmd)` is built from this same list, for the artifact/log record.
6. **Build the subprocess environment**, layered in order (later layers override same-key earlier
   ones): `os.environ` (the controller's own environment) → `graph_env`, each value
   `render_string`-rendered against `ctx`, if the graph declares one → `node.env`, each value
   `render_string`-rendered against `ctx`, if the node declares one. This is how a graph-level
   default (e.g. a shared `CODER_WORKSPACE`) is set once and overridden per-node when needed.
7. **Run the subprocess.** `subprocess.run(cmd, capture_output=True, text=True, cwd=effective_cwd,
   env=env)` — blocks until the process exits; stdout/stderr are captured as text, not streamed.
   Unlike [`run_agent`](run-agent.md), there is no timeout, retry, or reframe — a script node either
   succeeds or the whole run halts (see Raises above).
8. **Non-zero exit → raise `ScriptExitError(node.script, proc.returncode, proc.stderr)`** —
   short-circuits before any stdout parsing; a failed script's stdout (if any) is discarded.
9. **Zero exit → extract outputs.** `_extract_outputs(proc.stdout, node)` and return
   `(cmd_str, outputs)`.

## `ScriptExitError` — script's own exit code, faithfully propagated

- code: `workhorse/workhorse/runner/script.py::ScriptExitError`

An `Exception` subclass carrying the script's `exit_code: int` (set in `__init__`, read by
[workflow execution](workflow.md#execution) to call `sys.exit(exit_code)`) alongside the standard
message text (`f"Script '{script}' exited with code {exit_code}.\nstderr: {stderr.strip()}"`). The
distinction this preserves: a workflow script (e.g. an `await_operator` script) can `exit(2)` to mean
"blocked, needs operator input" — a deliberate, meaningful halt — distinct from `exit(1)` signaling
an unexpected crash. Because `run_script` re-raises this specific type rather than a generic one, the
caller can tell the two apart and exit the *process* with the same code the script chose, instead of
collapsing every non-zero exit to a single generic failure.

## `_extract_outputs(stdout, node)` — private

- code: `workhorse/workhorse/runner/script.py::_extract_outputs`

Parses the node's declared `outputs` out of the subprocess's stdout. Unlike
[agent.py's `_extract_outputs`](extract-outputs.md) (which recovers JSON embedded in a model's prose
via a strict-then-tolerant pipeline), this version requires stdout to be **exactly one JSON object
and nothing else** — a script is expected to print JSON on demand, not free text.

- **Input:** `stdout: str` — the subprocess's captured stdout; `node: ScriptNode`.
- **Output:** `dict[str, Any]` — one entry per `spec.key` in `node.outputs`, valued from the parsed
  JSON. `{}` immediately if `node.outputs` is empty (stdout is never even parsed in that case).
- **Raises:** `RuntimeError` when:
  - `json.loads(stdout.strip())` raises `json.JSONDecodeError` — message: `"Script '{node.script}'
    stdout is not valid JSON: {e}\nstdout: {stdout[:500]}"` (stdout truncated to 500 chars).
  - the parsed object is missing one of the declared keys — message: `"Node '{node.id}': expected
    output key '{spec.key}' not found in script JSON"` (raised on the first missing key found, in
    `node.outputs` order).

Algorithm:
```
def _extract_outputs(stdout, node):
    if not node.outputs: return {}
    parsed = json.loads(stdout.strip())   # raises RuntimeError on failure (see above)
    result = {}
    for spec in node.outputs:
        if spec.key not in parsed: raise RuntimeError("... key not found ...")
        result[spec.key] = parsed[spec.key]
    return result
```
1. **Short-circuit.** No declared `outputs` → `{}`, stdout untouched.
2. **Parse the whole stripped stdout as one JSON value.** No fenced-block search, no multi-object
   disambiguation, no repair pass — a script's stdout is expected to be exactly the JSON object
   (leading/trailing whitespace only).
3. **Require every declared key**, raising on the first absent one.
4. **Return only the declared subset** — extra keys the script printed are dropped.

## Consumers

- [Workflow execution](workflow.md#execution) (`workhorse/workhorse/main.py::_step_loop`) — the only
  caller, once per `ScriptNode` step. On success it merges `outputs` into the
  [`WorkflowContext`](workflow-context.md#mergedata---none), refuels the
  [gas tank](gas-tank.md#refuelnode_id-value) if `node.refuel` is set, writes the step artifact, and
  advances to `node.next`. On `ScriptExitError` it exits the process with the script's own code
  instead of propagating.
