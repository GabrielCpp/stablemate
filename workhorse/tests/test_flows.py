"""Tests for `flows:` composable sub-workflows.

A workflow may declare named sub-graphs under `flows:` (each mirroring the top-level
structure — its own vars + nodes + terminal). A `type: flow` node calls one like a
function: render `args` into a FRESH child context, run the flow to its terminal, lift
the declared `outputs` back into the parent, then advance to `next`. A flow can also be
run STANDALONE (`workhorse run <workflow> <flow>`), which is the re-QA entrypoint — its
vars are the parameter contract.

These tests drive real runs through script/branch/flow/terminal nodes only (no agent
backend needed). Run: PYTHONPATH=. pytest tests/test_flows.py
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

m = importlib.import_module("workhorse.main")

# A tiny script node body: turn `key=value` argv into a JSON object on stdout, so a
# node can echo rendered template values back out as its declared outputs.
_EMIT = """\
import json, sys
out = {}
for a in sys.argv[1:]:
    k, _, v = a.partition("=")
    out[k] = v
print(json.dumps(out))
"""

# Fails (exit 7) the first time it runs, succeeds afterward — used to simulate a kill
# mid-flow so resume can be exercised across the flow boundary.
_FAIL_ONCE = """\
import json, os, sys
marker = sys.argv[1]
if not os.path.exists(marker):
    open(marker, "w").close()
    sys.exit(7)
print(json.dumps({"r2": "recovered"}))
"""


def _scaffold(tmp_path: Path, workflow_yaml: str, scripts: dict[str, str] | None = None) -> Path:
    wf_dir = tmp_path / "wf"
    wf_dir.mkdir()
    (wf_dir / "emit.py").write_text(_EMIT)
    for name, body in (scripts or {}).items():
        (wf_dir / name).write_text(body)
    wf = wf_dir / "workflow.yaml"
    wf.write_text(workflow_yaml)
    return wf


def _ctx_after(runs_dir: Path, run_name: str, node_id: str) -> dict:
    """The full run context captured right after ``node_id`` ran. (The run-end
    ``context.json`` is intentionally reset to ``{}`` by finish() for an external
    controller to fill, so per-node ``context_after.json`` is the reliable record.)"""
    return json.loads((runs_dir / run_name / node_id / "context_after.json").read_text())


# A workflow that calls a `sub` flow, then echoes the returned value, then ends.
_COMPOSE = """\
name: main
start: call_sub
vars: { topvar: hello }
nodes:
  - id: call_sub
    type: flow
    name: sub
    args: { x: "{{ topvar }}" }
    outputs: [{ key: r }]
    next: check
  - id: check
    type: script
    script: emit.py
    args: ["seen={{ r }}"]
    outputs: [{ key: seen }]
    next: done
  - id: done
    type: terminal
flows:
  sub:
    start: s_emit
    # x has no default (null) → required: a standalone `run(flow="sub")` must be given
    # x or it fails fast (main.py flags vars whose default is None and weren't supplied).
    vars: { x: null }
    nodes:
      - id: s_emit
        type: script
        script: emit.py
        args: ["r=got-{{ x }}"]
        outputs: [{ key: r }]
        next: s_done
      - id: s_done
        type: terminal
"""


def test_compose_outputs_merge_back_and_next_resumes_parent(tmp_path):
    wf = _scaffold(tmp_path, _COMPOSE)
    runs = tmp_path / "runs"
    rc = m.run(wf, runs, flow=None, params={})
    assert rc == 0
    ctx = _ctx_after(runs, "main-default", "check")
    # the flow's output landed in the parent context, and the parent node after the
    # flow node saw it (proving `next` resumed the parent with the merged value).
    assert ctx["r"] == "got-hello"
    assert ctx["seen"] == "got-hello"
    # the child ran under a nested artifact scope, not the top-level run dir.
    assert (runs / "main-default" / "call_sub" / "_flow" / "s_emit" / "output.json").is_file()


def test_args_isolate_child_context(tmp_path):
    # `secret` lives only in the parent; the sub does NOT receive it (only `args`
    # cross the boundary), so its attempt to read it renders empty.
    wf = _scaffold(tmp_path, """\
name: main
start: call_sub
vars: { secret: top }
nodes:
  - id: call_sub
    type: flow
    name: sub
    args: {}
    outputs: [{ key: leak }]
    next: done
  - id: done
    type: terminal
flows:
  sub:
    start: s
    vars: {}
    nodes:
      - id: s
        type: script
        script: emit.py
        args: ["leak={{ secret }}"]
        outputs: [{ key: leak }]
        next: s_done
      - id: s_done
        type: terminal
""")
    runs = tmp_path / "runs"
    assert m.run(wf, runs, flow=None, params={}) == 0
    assert _ctx_after(runs, "main-default", "call_sub")["leak"] == ""


def test_args_pass_named_value_into_child(tmp_path):
    wf = _scaffold(tmp_path, """\
name: main
start: call_sub
vars: { secret: top }
nodes:
  - id: call_sub
    type: flow
    name: sub
    args: { secret: "{{ secret }}" }
    outputs: [{ key: leak }]
    next: done
  - id: done
    type: terminal
flows:
  sub:
    start: s
    vars: { secret: "" }
    nodes:
      - id: s
        type: script
        script: emit.py
        args: ["leak={{ secret }}"]
        outputs: [{ key: leak }]
        next: s_done
      - id: s_done
        type: terminal
""")
    runs = tmp_path / "runs"
    assert m.run(wf, runs, flow=None, params={}) == 0
    assert _ctx_after(runs, "main-default", "call_sub")["leak"] == "top"


def test_missing_flow_output_uses_declared_default(tmp_path):
    # The sub never emits `r2`; the flow node declares a default, so the parent gets it.
    wf = _scaffold(tmp_path, """\
name: main
start: call_sub
nodes:
  - id: call_sub
    type: flow
    name: sub
    args: {}
    outputs: [{ key: r2, default: DEFAULTED }]
    next: done
  - id: done
    type: terminal
flows:
  sub:
    start: s
    vars: {}
    nodes:
      - id: s
        type: script
        script: emit.py
        args: ["other=x"]
        outputs: [{ key: other }]
        next: s_done
      - id: s_done
        type: terminal
""")
    runs = tmp_path / "runs"
    assert m.run(wf, runs, flow=None, params={}) == 0
    assert _ctx_after(runs, "main-default", "call_sub")["r2"] == "DEFAULTED"


def test_unknown_flow_standalone_errors(tmp_path, capsys):
    wf = _scaffold(tmp_path, _COMPOSE)
    runs = tmp_path / "runs"
    rc = m.run(wf, runs, flow="nope", params={})
    assert rc == 1
    err = capsys.readouterr().err
    assert "no flow 'nope'" in err
    assert "sub" in err  # lists the available flow


def test_standalone_missing_required_param_errors(tmp_path, capsys):
    # `sub`'s `x` var has no default (null) → required; running it with no params fails fast.
    wf = _scaffold(tmp_path, _COMPOSE)
    runs = tmp_path / "runs"
    rc = m.run(wf, runs, flow="sub", params={})
    assert rc == 1
    err = capsys.readouterr().err
    assert "requires params" in err and "x" in err


def test_standalone_runs_flow_as_top_graph(tmp_path):
    # Supplying the contract runs just the flow, in its OWN run dir (named for the flow).
    wf = _scaffold(tmp_path, _COMPOSE)
    runs = tmp_path / "runs"
    rc = m.run(wf, runs, flow="sub", params={"x": "solo"})
    assert rc == 0
    # the standalone flow run is independent of any `main-*` run.
    assert not (runs / "main-default").exists()
    assert _ctx_after(runs, "sub-default", "s_emit")["r"] == "got-solo"


def test_nested_flow_depth_guard(tmp_path, monkeypatch):
    # Two levels of nesting with the ceiling pinned to 1 → the second level trips the
    # runaway-recursion backstop.
    monkeypatch.setattr(m, "_MAX_FLOW_DEPTH", 1)
    wf = _scaffold(tmp_path, """\
name: main
start: call_a
nodes:
  - id: call_a
    type: flow
    name: a
    args: {}
    outputs: []
    next: done
  - id: done
    type: terminal
flows:
  a:
    start: a_call_b
    vars: {}
    nodes:
      - id: a_call_b
        type: flow
        name: b
        args: {}
        outputs: []
        next: a_done
      - id: a_done
        type: terminal
    flows:
      b:
        start: b_s
        vars: {}
        nodes:
          - id: b_s
            type: terminal
""")
    runs = tmp_path / "runs"
    with pytest.raises(RuntimeError, match="flow nesting exceeded depth"):
        m.run(wf, runs, flow=None, params={})


def test_resume_across_flow_boundary(tmp_path):
    # s2 inside the flow crashes the first time; the run halts mid-flow. An auto
    # re-run resumes INTO the flow and finishes it.
    marker = tmp_path / "marker"
    wf = _scaffold(tmp_path, f"""\
name: main
start: call_sub
nodes:
  - id: call_sub
    type: flow
    name: sub
    args: {{}}
    outputs: [{{ key: r2 }}]
    next: done
  - id: done
    type: terminal
flows:
  sub:
    start: s1
    vars: {{}}
    nodes:
      - id: s1
        type: script
        script: emit.py
        args: ["a=1"]
        outputs: [{{ key: a }}]
        next: s2
      - id: s2
        type: script
        script: failonce.py
        args: ["{marker}"]
        outputs: [{{ key: r2 }}]
        next: s_done
      - id: s_done
        type: terminal
""", scripts={"failonce.py": _FAIL_ONCE})
    runs = tmp_path / "runs"

    # First run: s2 fails (exit 7), propagated as SystemExit.
    with pytest.raises(SystemExit) as exc:
        m.run(wf, runs, flow=None, params={})
    assert exc.value.code == 7
    # the flow was checkpointed mid-stream (s2 was the live node in the child scope).
    assert (runs / "main-default" / "call_sub" / "_flow" / "checkpoint.json").is_file()

    # Auto re-run: resumes the unfinished run, re-enters the flow, s2 now succeeds.
    rc = m.run(wf, runs, flow=None, params={})
    assert rc == 0
    assert _ctx_after(runs, "main-default", "call_sub")["r2"] == "recovered"


# A counter script: increment the count in the file argv[1] and emit it under key
# argv[2]. Used to prove a flow runs afresh each loop iteration (vs fast-forwarding
# past a prior invocation's cached completion).
_COUNTER = """\
import json, os, sys
f, key = sys.argv[1], sys.argv[2]
n = (int(open(f).read()) + 1) if os.path.exists(f) else 1
open(f, "w").write(str(n))
print(json.dumps({key: str(n)}))
"""


def test_flow_in_loop_reruns_each_iteration(tmp_path):
    """A flow node invoked once per loop iteration must RUN every time — not
    fast-forward through the first invocation's completed checkpoint. Regression guard
    for the subscope-keyed-by-node-id bug that made a per-story qa flow run once and
    then be silently skipped, looping the parent forever."""
    pcount = tmp_path / "parent.count"
    fcount = tmp_path / "flow.count"
    wf = _scaffold(tmp_path, f"""\
name: loop
start: tick
nodes:
  - id: tick
    type: script
    script: counter.py
    args: ["{pcount}", "i"]
    outputs: [{{ key: i }}]
    next: call
  - id: call
    type: flow
    name: work
    args: {{}}
    outputs: [{{ key: did }}]
    next: gate
  - id: gate
    type: branch
    path: i
    conditions: [{{ op: ">=", value: "3", next: done }}]
    default: tick
  - id: done
    type: terminal
flows:
  work:
    start: w
    vars: {{}}
    nodes:
      - id: w
        type: script
        script: counter.py
        args: ["{fcount}", "did"]
        outputs: [{{ key: did }}]
        next: w_done
      - id: w_done
        type: terminal
""", scripts={"counter.py": _COUNTER})
    runs = tmp_path / "runs"
    assert m.run(wf, runs, flow=None, params={}) == 0
    # The parent looped 3 times AND the flow body ran on every one of them.
    assert pcount.read_text() == "3"
    assert fcount.read_text() == "3"  # would be "1" if the flow fast-forwarded


def test_nonprogressing_loop_runs_out_of_gas(tmp_path, monkeypatch):
    """A cycle that never reaches a terminal and never refuels must HALT (non-zero)
    once the gas tank empties — not spin forever."""
    monkeypatch.setenv("WORKHORSE_GAS", "40")
    wf = _scaffold(tmp_path, """\
name: spin
start: a
nodes:
  - id: a
    type: script
    script: emit.py
    args: ["x=1"]
    outputs: [{ key: x }]
    next: b
  - id: b
    type: branch
    path: x
    default: a
  - id: stop
    type: terminal
""")
    runs = tmp_path / "runs"
    # Caught inside run(): an out-of-gas halt returns 1 (a failed run), not a hang.
    assert m.run(wf, runs, flow=None, params={}) == 1


def test_refuel_keeps_progressing_loop_alive(tmp_path, monkeypatch):
    """A loop that makes real progress each iteration (a refuel node's tracked value
    changes) tops the tank back up, so it completes even when the whole run needs far
    more steps than one tank holds."""
    monkeypatch.setenv("WORKHORSE_GAS", "20")  # < the ~45 steps this 15-iteration loop needs
    pcount = tmp_path / "p.count"
    wf = _scaffold(tmp_path, f"""\
name: progress
start: tick
nodes:
  - id: tick
    type: script
    script: counter.py
    args: ["{pcount}", "i"]
    outputs: [{{ key: i }}]
    refuel: i
    next: gate
  - id: gate
    type: branch
    path: i
    conditions: [{{ op: ">=", value: "15", next: done }}]
    default: tick
  - id: done
    type: terminal
""", scripts={"counter.py": _COUNTER})
    runs = tmp_path / "runs"
    assert m.run(wf, runs, flow=None, params={}) == 0
    assert pcount.read_text() == "15"  # ran all 15 iterations despite the 20-unit tank


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
