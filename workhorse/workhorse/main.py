from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
import shutil
import sys
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import otel
from .artifacts import ArtifactWriter
from .config import config_path, get_config_value, load_config, write_config_key
from .graph.context import WorkflowContext
from .graph.loader import load_workflow
from .graph.nodes import (
    AgentNode,
    BranchNode,
    CallNode,
    FlowNode,
    Graph,
    ScriptNode,
    TerminalNode,
)
from .runner import agent as agent_runner
from .runner import branch as branch_runner
from .runner import call as call_runner
from .runner import script as script_runner
from .runner.agent import BackendInvocationError
from .runner.script import ScriptExitError
from .templates import render_string

# Canonical skill directory per backend — must match farrier's install layout.
_BACKEND_SKILL_DIR: dict[str, str] = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "copilot": ".github/skills",
}


def run(
    workflow_path: Path,
    runs_dir: Path,
    resume_run_dir: Path | None = None,
    auto: bool = True,
    run_id: str | None = None,
    params: dict[str, Any] | None = None,
    context_manifest: dict[str, Any] | None = None,
    flow: str | None = None,
    no_cache: bool = False,
) -> int:
    graph = load_workflow(workflow_path)
    workflow_dir = workflow_path.parent

    # `workhorse run <workflow> <flow>`: run a named sub-graph standalone (the re-QA
    # entrypoint). The flow's `vars` are its parameter contract; treat the sub-graph
    # as the top graph for this run so it gets its own run dir, checkpoint, and
    # resume — independent of the parent workflow's run, so a story from a merged or
    # already-finished epic re-qualifies fine.
    if flow is not None:
        if flow not in graph.flows:
            available = ", ".join(sorted(graph.flows)) or "(none)"
            print(
                f"error: workflow '{graph.name}' has no flow '{flow}'. "
                f"Available flows: {available}",
                file=sys.stderr,
            )
            return 1
        supplied = params or {}
        missing = [
            k
            for k, v in graph.flows[flow].vars.items()
            if v is None and not supplied.get(k)
        ]
        if missing:
            contract = ", ".join(
                f"{k}={v!r}" for k, v in graph.flows[flow].vars.items()
            )
            print(
                f"error: flow '{flow}' requires params: {', '.join(missing)}\n"
                f"  contract (var=default): {contract}\n"
                f'  supply via --params \'{{"<var>": "<value>"}}\'',
                file=sys.stderr,
            )
            return 1
        graph = graph.flows[flow]

    # The per-repo context manifest (template values, instruction/prompt path maps,
    # selected-skills set) is the OUTER layer of every context: the workflow's own
    # vars, --params, and node outputs all override it, but it is always present so
    # the farrier template helpers (instruction_ref/isUsingInstruction/template.*)
    # resolve at render time. See workhorse/templates.py.
    manifest = context_manifest or {}

    # Default (auto): one stable run dir per (workflow, program) that we resume in
    # place. The run *is* the research session — its full context (counters, gate
    # selection, ladder position) lives in the checkpoint, so we continue the same
    # graph with the same state rather than re-deriving it. Delete the dir to start
    # over. If it has no checkpoint yet, start fresh IN that same stable dir. An
    # explicit resume_run_dir (manual --resume-*) overrides this.
    fresh_run_id = run_id
    if no_cache and resume_run_dir is None:
        rid = run_id or "default"
        stable = runs_dir / f"{graph.name}-{rid}"
        if stable.is_dir():
            shutil.rmtree(stable)
            print(f"[workhorse] --no-cache: cleared run dir {stable.name}")
    if resume_run_dir is None and auto:
        fresh_run_id, resume_run_dir = _auto_resolve(runs_dir, graph.name, run_id)

    # Set only when we re-enter a node that was interrupted mid-run, so that one
    # node resumes its Claude session; every other node starts from a clean context.
    resume_interrupted_node = False

    if resume_run_dir is not None:
        writer = ArtifactWriter.resume(resume_run_dir)
        checkpoint = writer.read_checkpoint()
        if checkpoint is None:
            print(
                f"error: no checkpoint found in {resume_run_dir}; cannot resume",
                file=sys.stderr,
            )
            return 1
        current_id = checkpoint["current_id"]
        if current_id not in graph.nodes:
            print(
                f"error: checkpoint node '{current_id}' not found in workflow "
                f"'{graph.name}' (did the workflow change?)",
                file=sys.stderr,
            )
            return 1
        ctx = WorkflowContext(initial={**manifest, **checkpoint["context"]})
        print(
            f"[workhorse] resuming '{graph.name}' at node '{current_id}' "
            f"(run: {writer.run_dir.name})"
        )
        # Idempotency: if this node ALREADY completed under the current checkpoint
        # (its done-marker seq matches), it was killed in the gap between finishing
        # and the cursor advancing — fast-forward past it instead of re-running its
        # side effects (e.g. a git commit or a PROGRESS append). A non-matching/absent
        # seq means it was killed mid-run (or the marker is a stale earlier visit), so
        # we re-run it as normal.
        done = writer.read_done(current_id)
        if _should_fast_forward(done, checkpoint):
            after = writer.read_context_after(current_id)
            if after is not None:
                ctx = WorkflowContext(initial={**manifest, **after})
            print(
                f"[workhorse] node '{current_id}' already completed under this "
                f"checkpoint — fast-forwarding to '{done['next']}'"
            )
            current_id = done["next"]
        else:
            # We're re-entering a node that was killed mid-run. It (and only it)
            # should resume its Claude session to continue where it left off; the
            # fast-forward case above lands on the NEXT node, which is a fresh start.
            resume_interrupted_node = True
    else:
        # Workflow params (a generic key→value map from --params/--params-file)
        # override the workflow's own `vars` in the starting context, so callers
        # can parameterize a run without editing the workflow (e.g. pick a research
        # program). They apply only on a fresh start; a resume restores the context
        # from the checkpoint, which already captured them.
        ctx = WorkflowContext(initial={**manifest, **graph.vars, **(params or {})})
        writer = ArtifactWriter(graph.name, runs_dir, run_id=fresh_run_id)
        current_id = graph.start
        print(f"[workhorse] starting '{graph.name}' (run: {writer.run_dir.name})")

    ctx.merge({"_run_dir": str(writer.run_dir)})

    session_id_path = writer.run_dir / ".session_id"

    tank = _GasTank(_configured_gas())

    # Opt-in telemetry (WORKHORSE_OTEL): the run's root span opens here and every
    # node/turn span nests under it; end_run flushes on every exit path below.
    otel.start_run(graph.name, writer.run_id)

    try:
        terminal_type = _step_loop(
            graph,
            writer,
            ctx,
            current_id,
            resume_interrupted_node,
            manifest=manifest,
            workflow_dir=workflow_dir,
            session_id_path=session_id_path,
            tank=tank,
            deadline=_runtime_deadline(writer.started_at),
        )
    except KeyboardInterrupt:
        agent_runner.terminate_active()
        print("\n[workhorse] interrupted — run paused.", file=sys.stderr)
        print(
            f"[workhorse] resume with: workhorse --resume-run {writer.run_dir}",
            file=sys.stderr,
        )
        otel.end_run("interrupted", error="KeyboardInterrupt")
        sys.exit(130)
    except OutOfGasError as e:
        # A never-terminating cycle: fail the run loudly (non-zero) instead of letting
        # it spin forever. The run dir is left intact for inspection.
        agent_runner.terminate_active()
        print(f"[workhorse] ERROR: {e}", file=sys.stderr)
        writer.finish(terminal="fail")
        otel.end_run("fail", error=str(e))
        return 1
    except RunBudgetExceeded as e:
        # The engine wall-clock budget (WORKHORSE_MAX_RUNTIME_S) ran out — the
        # self-defense backstop for a run nothing is watching. Fail loudly like
        # OutOfGasError; the run dir stays resumable if the operator raises the
        # budget (the clock counts from the ORIGINAL start, surviving --resume).
        agent_runner.terminate_active()
        print(f"[workhorse] ERROR: {e}", file=sys.stderr)
        writer.finish(terminal="fail")
        otel.end_run("fail", error=str(e))
        return 1
    except BackendInvocationError as e:
        # An agent-CLI turn failed in a way the resilience ladder couldn't recover
        # (a non-recoverable backend/CLI crash, or a transient that exhausted its
        # budget with defaulting disabled). End the run cleanly — a clear message
        # and a resume command — instead of letting it surface as a raw traceback.
        agent_runner.terminate_active()
        kind = "transient" if e.transient else "non-recoverable"
        print(f"[workhorse] ERROR: {kind} agent failure — {e}", file=sys.stderr)
        print(
            f"[workhorse] resume with: workhorse --resume-run {writer.run_dir}",
            file=sys.stderr,
        )
        writer.finish(terminal="fail")
        otel.end_run("fail", error=str(e))
        return 1
    else:
        writer.write_final_context(ctx.as_dict())
        writer.finish(terminal=terminal_type)
        otel.end_run(
            terminal_type, error=None if terminal_type == "terminal" else terminal_type
        )
        success = terminal_type == "terminal"
        print(f"[workhorse] {terminal_type.upper()} — run artifacts: {writer.run_dir}")
        return 0 if success else 1
    finally:
        # Backstop for exits that bypass the handlers above (e.g. a script node's
        # sys.exit propagating as SystemExit): close and flush whatever telemetry
        # is still open. A no-op when a handler (or the success path) already did.
        otel.end_run("aborted", error="run aborted before finalize")


# Hard ceiling on flow nesting (a flow calling a flow calling a flow …). Real
# compositions are shallow; this is a runaway-recursion backstop, not a design limit.
_MAX_FLOW_DEPTH = 16

# Gas-tank infinite-loop guard. A workflow that never reaches a terminal — a cycle
# whose exit branch never trips (e.g. a story loop whose "done" condition is never
# satisfied) — would otherwise spin FOREVER, silently burning an unattended week-long
# run with no failure ever surfaced. A hang reads as "still working", which is the
# worst outcome. Rather than a flat global step ceiling (which a legitimately long run
# could trip), the guard is PROGRESS-METERED: the run burns one unit of gas per node
# step and refuels to full whenever it makes real forward progress (a refuel node's
# tracked value changes — a new story, a new epic). A healthy run tops up at every
# progress point and never runs dry no matter how long it is; a loop that reprocesses
# the SAME unit forever burns exactly one tank and then halts LOUDLY with diagnostics.
# So the tank is sized to ONE unit of progress (one story), NOT the whole run. Override
# with WORKHORSE_GAS; set it to 0 to disable the guard entirely (not recommended).
_DEFAULT_GAS = 5000


class OutOfGasError(RuntimeError):
    """Raised when a run burns a full gas tank without forward progress — a loop."""


class RunBudgetExceeded(RuntimeError):
    """Raised when the run outlives its wall-clock budget (WORKHORSE_MAX_RUNTIME_S).

    A self-defense backstop complementary to the gas tank: gas catches a cycle
    that never progresses, this catches a run that progresses forever (or crawls)
    past the operator's absolute time ceiling with nothing watching it. Counted
    from the run's ORIGINAL start (writer.started_at), so it survives --resume.
    Unset/0 disables it (the default — most runs are bounded by their graph).
    """


def _configured_max_runtime_s() -> float:
    raw = (os.environ.get("WORKHORSE_MAX_RUNTIME_S") or "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        print(
            f"[workhorse] ⚠ ignoring non-numeric WORKHORSE_MAX_RUNTIME_S={raw!r}; "
            f"runtime budget disabled",
            file=sys.stderr,
        )
        return 0.0


def _runtime_deadline(started_at_iso: str) -> float | None:
    """Absolute unix-epoch deadline for this run, or None when no budget is set.
    Anchored to the writer's original ISO start time so a resumed run keeps the
    same deadline instead of restarting the clock."""
    budget = _configured_max_runtime_s()
    if budget <= 0:
        return None
    try:
        started = datetime.fromisoformat(started_at_iso)
    except ValueError:
        started = datetime.now(timezone.utc)
    return started.timestamp() + budget


def _configured_gas() -> int:
    raw = (os.environ.get("WORKHORSE_GAS") or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            print(
                f"[workhorse] ⚠ ignoring non-integer WORKHORSE_GAS={raw!r}; "
                f"using default {_DEFAULT_GAS}",
                file=sys.stderr,
            )
    return _DEFAULT_GAS


class _GasTank:
    """Progress-metered loop guard shared across the root graph AND every nested flow
    (one tank per run). ``burn`` spends a unit per node step and raises once the tank
    is empty; ``refuel`` refills it to full when a progress marker advances (a refuel
    node's tracked value changed). A sliding window of recent node ids lets the failure
    name the hottest nodes — the cycle whose exit condition never trips."""

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.gas = capacity
        self._last_refuel: dict[str, Any] = {}
        self._recent: deque[str] = deque(maxlen=2000)

    def refuel(self, node_id: str, value: Any) -> None:
        """Top the tank back up when this refuel node's tracked value has changed
        since we last saw it (forward progress), or on its first visit."""
        if self.capacity <= 0:
            return
        sentinel = self._last_refuel.get(node_id, _UNSEEN)
        if value != sentinel:
            self._last_refuel[node_id] = value
            self.gas = self.capacity
            otel.gas_refuel(node_id)
            otel.gas_level(self.gas, self.capacity)

    def burn(self, node_id: str) -> None:
        if self.capacity <= 0:  # guard disabled
            return
        self._recent.append(node_id)
        self.gas -= 1
        otel.gas_level(self.gas, self.capacity)
        if self.gas < 0:
            hot = ", ".join(
                f"{nid}×{n}" for nid, n in Counter(self._recent).most_common(8)
            )
            raise OutOfGasError(
                f"workflow ran out of gas — burned a full tank of {self.capacity} node "
                f"steps without forward progress (no new story/epic). Almost certainly "
                f"an infinite loop: the exit condition on the cycle is never tripping. "
                f"Hottest nodes in the last {len(self._recent)} steps: {hot}. The tank "
                f"refuels on real progress (a refuel node's value changing); if this run "
                f"legitimately needs more steps between progress points, raise "
                f"WORKHORSE_GAS."
            )


# Sentinel for "this refuel node has never been visited" (distinct from any real
# value, including None, so the first visit always counts as progress).
_UNSEEN = object()


def _step_loop(
    graph: Graph,
    writer: ArtifactWriter,
    ctx: WorkflowContext,
    current_id: str,
    resume_interrupted_node: bool,
    *,
    manifest: dict[str, Any],
    workflow_dir: Path,
    session_id_path: Path,
    tank: _GasTank,
    depth: int = 0,
    deadline: float | None = None,
) -> str:
    """Step ``graph`` from ``current_id`` until a TerminalNode, mutating ``ctx`` in
    place. Returns the terminal node's type ("terminal" | "fail") WITHOUT finalizing
    the writer — the caller (top-level run, or a flow handler) decides what to do with
    that result. This is the shared engine for both the root graph and every flow
    sub-graph (see the FlowNode branch). ``tank`` is the run-wide gas guard, shared
    across the root and all flows so a non-progressing cycle anywhere fails loudly;
    ``deadline`` is the run-wide wall-clock budget (unix epoch, None = unbounded),
    likewise shared so a flow can't outlive the run's ceiling."""
    while True:
        node = graph.nodes[current_id]

        if isinstance(node, TerminalNode):
            return node.type

        # Engine wall-clock budget: checked between nodes (not mid-turn) so a
        # node always finishes cleanly and the run dir stays resumable.
        if deadline is not None and time.time() > deadline:
            raise RunBudgetExceeded(
                f"run exceeded its WORKHORSE_MAX_RUNTIME_S wall-clock budget "
                f"(deadline passed {int(time.time() - deadline)}s ago, counted from "
                f"the run's original start). Raise the budget and resume, or "
                f"inspect the run dir for why it is still going."
            )

        # Infinite-loop guard: spend one unit of gas for this step (across root +
        # flows). Refuel happens below, after a progress-marking node advances.
        tank.burn(current_id)

        # Checkpoint the node we're about to run and the context going into it.
        # If this node crashes (e.g. spending cap), `--resume-run` re-enters here.
        writer.write_checkpoint(current_id, ctx.as_dict())

        if isinstance(node, AgentNode):
            print(f"[workhorse] agent  → {node.id}")
            try:
                # run_agent is self-healing: it retries transient failures, reframes
                # the prompt, and finally defaults the node's outputs so the run
                # advances rather than crashing. A BackendInvocationError only
                # escapes when the failure is non-recoverable (the backend/CLI
                # itself crashed) or defaulting is disabled (AGENT_USE_DEFAULT_OUTPUTS=false).
                prompt, outputs = agent_runner.run_agent(
                    node,
                    ctx,
                    workflow_dir,
                    session_id_path,
                    run_dir=writer.run_dir,
                    resume_session=resume_interrupted_node,
                )
                # The resume only applies to the first re-entered node; every node
                # the run advances to afterward is a fresh prompt / clean context.
                resume_interrupted_node = False

                ctx.merge(outputs)
                if node.next is None:
                    raise RuntimeError(
                        f"AgentNode '{node.id}' has no 'next' and is not terminal"
                    )
                writer.write_step(
                    node.id, prompt, outputs, ctx.as_dict(), next_node=node.next
                )
                current_id = node.next

            except BackendInvocationError as e:
                print(f"[workhorse] ERROR in node '{node.id}': {e}", file=sys.stderr)
                if e.transient:
                    print(
                        "[workhorse] This is a transient error - the workflow can be resumed",
                        file=sys.stderr,
                    )
                    print(
                        f"[workhorse] Resume command: --resume-run {writer.run_dir}",
                        file=sys.stderr,
                    )
                else:
                    print(
                        "[workhorse] This is a non-recoverable agent failure",
                        file=sys.stderr,
                    )
                raise

        elif isinstance(node, ScriptNode):
            # A re-entered script/branch carries no Claude session; clear the flag
            # so a later agent node isn't mistaken for an interrupted continuation.
            resume_interrupted_node = False
            print(f"[workhorse] script → {node.id}")
            try:
                cmd_str, outputs = script_runner.run_script(
                    node, ctx, workflow_dir, graph.env or None
                )
                ctx.merge(outputs)
                # Refuel the gas tank on forward progress: when a node declares a
                # `refuel` key (e.g. select_story → story_slug), a CHANGED value means
                # a new unit of work began, so top the tank back up. Reprocessing the
                # same story/epic leaves the value unchanged → no refuel → the loop
                # eventually runs dry and halts.
                if node.refuel:
                    tank.refuel(node.id, ctx.get_dotpath(node.refuel, None))
                if node.next is None:
                    raise RuntimeError(
                        f"ScriptNode '{node.id}' has no 'next' and is not terminal"
                    )
                writer.write_step(
                    node.id, cmd_str, outputs, ctx.as_dict(), next_node=node.next
                )
                current_id = node.next
            except ScriptExitError as e:
                # Propagate the script's own exit code so callers can distinguish
                # expected halts (e.g. await_operator exits 2 for "blocked") from
                # genuine crashes (exit 1).
                print(
                    f"[workhorse] ERROR in script node '{node.id}': {e}",
                    file=sys.stderr,
                )
                sys.exit(e.exit_code)
            except Exception as e:
                # Log script errors with context
                print(
                    f"[workhorse] ERROR in script node '{node.id}': {e}",
                    file=sys.stderr,
                )
                print(
                    "[workhorse] Script execution failed - workflow can be resumed after fixing",
                    file=sys.stderr,
                )
                print(
                    f"[workhorse] Resume command: --resume-run {writer.run_dir}",
                    file=sys.stderr,
                )
                raise

        elif isinstance(node, CallNode):
            resume_interrupted_node = False
            print(f"[workhorse] call   → {node.id}")
            label, outputs = call_runner.run_call(node, ctx, workflow_dir)
            ctx.merge(outputs)
            if node.refuel:
                tank.refuel(node.id, ctx.get_dotpath(node.refuel, None))
            if node.next is None:
                raise RuntimeError(
                    f"CallNode '{node.id}' has no 'next' and is not terminal"
                )
            writer.write_step(node.id, label, outputs, ctx.as_dict(), next_node=node.next)
            current_id = node.next

        elif isinstance(node, BranchNode):
            resume_interrupted_node = False
            print(f"[workhorse] branch → {node.id}")
            next_id, value = branch_runner.evaluate(node, ctx)
            writer.write_branch(node.id, node.path, value, next_id)
            current_id = next_id

        elif isinstance(node, FlowNode):
            # Capture whether THIS entry is a genuine mid-flow resume (the parent was
            # killed inside this flow node) BEFORE clearing the flag. Only a real
            # resume reuses the child's checkpoint; a fresh re-entry (a loop body
            # invoking the flow again) must re-run the flow from its start.
            is_flow_resume = resume_interrupted_node
            resume_interrupted_node = False
            outputs = _run_flow(
                node,
                graph,
                writer,
                ctx,
                manifest=manifest,
                workflow_dir=workflow_dir,
                session_id_path=session_id_path,
                tank=tank,
                depth=depth,
                deadline=deadline,
                resume=is_flow_resume,
            )
            ctx.merge(outputs)
            if node.next is None:
                raise RuntimeError(
                    f"FlowNode '{node.id}' has no 'next' and is not terminal"
                )
            writer.write_step(
                node.id,
                f"flow:{node.name}",
                outputs,
                ctx.as_dict(),
                next_node=node.next,
            )
            current_id = node.next

        else:
            raise RuntimeError(f"Unknown node type: {type(node)}")


def _enter(
    writer: ArtifactWriter,
    graph: Graph,
    manifest: dict[str, Any],
    initial: dict[str, Any],
) -> tuple[str, WorkflowContext, bool]:
    """Decide resume-vs-fresh for ``writer``'s run dir and return
    ``(current_id, ctx, resume_interrupted_node)``. With no checkpoint, start fresh
    from ``graph.start`` with ``initial`` context. With one, restore the context and
    either fast-forward past an already-completed node or re-enter the interrupted
    one. This is the same logic the root uses inline (kept separate there for its
    friendly messages); flows reuse it for resume across a flow boundary."""
    checkpoint = writer.read_checkpoint()
    if checkpoint is None:
        return graph.start, WorkflowContext(initial=initial), False
    current_id = checkpoint["current_id"]
    if current_id not in graph.nodes:
        raise ValueError(
            f"checkpoint node '{current_id}' not found in flow '{graph.name}' "
            f"(did the flow change?)"
        )
    ctx = WorkflowContext(initial={**manifest, **checkpoint["context"]})
    done = writer.read_done(current_id)
    if _should_fast_forward(done, checkpoint):
        after = writer.read_context_after(current_id)
        if after is not None:
            ctx = WorkflowContext(initial={**manifest, **after})
        return done["next"], ctx, False
    return current_id, ctx, True


def _run_flow(
    node: FlowNode,
    graph: Graph,
    writer: ArtifactWriter,
    parent_ctx: WorkflowContext,
    *,
    manifest: dict[str, Any],
    workflow_dir: Path,
    session_id_path: Path,
    tank: _GasTank,
    depth: int,
    deadline: float | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Run the flow named by ``node`` as a child graph and return its declared
    outputs. The child context is ``{manifest, flow.vars, rendered_args}`` — only the
    rendered ``args`` cross from the parent, so the boundary is explicit. The child
    runs under a nested artifact scope so a kill inside it resumes mid-flow.

    ``resume`` is the parent's "we were killed inside this flow node" signal; it gates
    whether the child reuses its checkpoint (true resume) or starts clean. A fresh
    re-entry (the same flow node reached again by normal forward stepping — e.g. a
    per-story loop calling the qa flow each iteration) must run the flow from scratch,
    NOT fast-forward through the previous invocation's completed checkpoint."""
    if depth + 1 > _MAX_FLOW_DEPTH:
        raise RuntimeError(
            f"flow nesting exceeded depth {_MAX_FLOW_DEPTH} at flow node '{node.id}' "
            f"(flow '{node.name}') — likely a flow cycle"
        )
    flow = graph.flows[node.name]  # existence validated at load time
    rendered = {k: render_string(v, parent_ctx.as_dict()) for k, v in node.args.items()}
    print(f"[workhorse] flow   → {node.id} ({node.name})")

    child_writer = writer.subscope(node.id, flow.name, resume=resume)
    initial = {**manifest, **flow.vars, **rendered}
    current_id, child_ctx, resume_interrupted_node = _enter(
        child_writer, flow, manifest, initial
    )
    term = _step_loop(
        flow,
        child_writer,
        child_ctx,
        current_id,
        resume_interrupted_node,
        manifest=manifest,
        workflow_dir=workflow_dir,
        session_id_path=child_writer.run_dir / ".session_id",
        tank=tank,
        depth=depth + 1,
        deadline=deadline,
    )
    child_writer.write_final_context(child_ctx.as_dict())
    child_writer.finish(terminal=term)

    # Lift the declared outputs out of the child's terminal context (missing key →
    # the spec's declared default, mirroring the agent/script output contract).
    return {
        spec.key: child_ctx.get_dotpath(spec.key, spec.default) for spec in node.outputs
    }


def _should_fast_forward(done: dict | None, checkpoint: dict) -> bool:
    """True iff the checkpoint node already completed under THIS checkpoint — i.e.
    its done-marker seq matches the checkpoint seq and names a next node. A missing
    marker, a mismatched seq (a stale earlier-visit run), or no next means re-run."""
    return bool(
        done is not None
        and done.get("seq") is not None
        and done.get("seq") == checkpoint.get("seq")
        and done.get("next")
    )


def _auto_resolve(
    runs_dir: Path, workflow_name: str, run_id: str | None = None
) -> tuple[str, Path | None]:
    """Resolve --auto's single stable run dir for this run id.

    The run id defaults to "default", giving one fixed dir per id (e.g.
    ``research-default``); pass ``--run-id`` to keep separate runs side by side.
    Returns ``(run_id, resume_dir)`` where ``resume_dir`` is that dir when it
    already holds a checkpoint to continue, else None (caller starts fresh).

    A run that already reached a terminal node is NOT resumed — re-running means a
    new run, not a no-op replay of the finished one (mirrors ``_find_latest_resumable``,
    which skips terminal runs). The fresh start reuses the same stable dir."""
    rid = run_id or "default"
    stable = runs_dir / f"{workflow_name}-{rid}"
    if not (stable / ArtifactWriter.CHECKPOINT_FILE).exists():
        return rid, None
    try:
        meta = json.loads((stable / "run.json").read_text())
    except (OSError, json.JSONDecodeError):
        meta = {}
    if meta.get("terminal") is not None:  # already finished — start a new run
        return rid, None
    return rid, stable


def _load_params(inline: str | None, file: str | None) -> dict[str, Any]:
    """Merge workflow params from --params-file then --params (inline wins).

    Each source must be a JSON object (key→value map). Exits with a clear error on
    a missing file, invalid JSON, or a non-object payload."""
    params: dict[str, Any] = {}
    if file is not None:
        try:
            inline_from_file = Path(file).read_text()
        except OSError as e:
            print(f"error: cannot read --params-file {file}: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        inline_from_file = None

    for label, raw in (("--params-file", inline_from_file), ("--params", inline)):
        if raw is None:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"error: {label} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(parsed, dict):
            print(
                f"error: {label} must be a JSON object (key→value map)", file=sys.stderr
            )
            sys.exit(1)
        params.update(parsed)
    return params


def _find_latest_resumable(runs_dir: Path) -> Path | None:
    """Newest run dir that crashed mid-flight (has a checkpoint, never finished)."""
    if not runs_dir.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for d in runs_dir.iterdir():
        if not d.is_dir() or not (d / ArtifactWriter.CHECKPOINT_FILE).exists():
            continue
        try:
            meta = json.loads((d / "run.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if meta.get("terminal") is None:  # never reached a terminal node
            candidates.append(((d / ArtifactWriter.CHECKPOINT_FILE).stat().st_mtime, d))
    if not candidates:
        return None
    return max(candidates)[1]


def _build_manifest_context(raw: dict[str, Any]) -> dict[str, Any]:
    """Shape a farrier context manifest into starting-context keys.

    The manifest's ``template``/``repo``/``vars`` become top-level context values
    (so ``{{ template.x }}`` / ``{{ repo.y }}`` resolve), while the path maps and
    the selected-skills set are stashed under reserved ``_``-prefixed keys read by
    the template helpers in workhorse/templates.py.

    When the active backend (``AGENT_CLI``) differs from the backend the manifest
    was generated for, instruction paths are rewritten from the manifest's
    ``skill_dir`` prefix to the active backend's directory.  All three backends
    share the ``{skill_dir}/{prefix}-{name}/SKILL.md`` structure, so a simple
    prefix substitution is sufficient.
    """
    ctx: dict[str, Any] = {}
    for key in ("template", "repo", "vars"):
        value = raw.get(key)
        if isinstance(value, dict):
            ctx[key] = value

    backend = os.environ.get("AGENT_CLI", "claude")
    manifest_skill_dir = raw.get("skill_dir") or ""
    target_skill_dir = _BACKEND_SKILL_DIR.get(backend, manifest_skill_dir)

    raw_instructions: dict[str, str] = raw.get("instructions") or {}
    if (
        manifest_skill_dir
        and target_skill_dir
        and target_skill_dir != manifest_skill_dir
    ):
        ctx["_instructions"] = {
            k: v.replace(manifest_skill_dir, target_skill_dir, 1)
            for k, v in raw_instructions.items()
        }
    else:
        ctx["_instructions"] = raw_instructions

    ctx["_prompts"] = raw.get("prompts") or {}
    ctx["_used_skills"] = raw.get("used_skills") or []
    if target_skill_dir or manifest_skill_dir:
        ctx["_skill_dir"] = target_skill_dir or manifest_skill_dir

    # Absolute repo root, so the renderer can locate hand-authored prompt flavor
    # overrides at <repo>/.agents/flavors/<workflow>/<node>.md (see templates.render).
    # The agent runs with its cwd at the repo root (AGENT_REPO_DIR); default to cwd.
    ctx["_repo_root"] = str(Path(os.environ.get("AGENT_REPO_DIR") or ".").resolve())
    return ctx


def _load_context_manifest(context_file: str | None) -> dict[str, Any]:
    """Load the per-repo farrier context manifest that library prompts render against.

    Resolution order: an explicit ``--context-file`` (which MUST exist — a typo'd
    path is a hard error), else auto-detect the per-assistant manifest for the active
    CLI (``$AGENT_REPO_DIR/.agents/agents-context.$AGENT_CLI.json``), then the generic
    ``$AGENT_REPO_DIR/.agents/agents-context.json``. The per-assistant file makes a
    Codex/Copilot run resolve ``instruction_ref`` to its own adapter files
    (``.github/skills`` etc.) rather than Claude's. When none is present the run
    proceeds with an empty manifest (the farrier helpers degrade to placeholders /
    ``False``) — manifest-free workflows like hello-world need no repo context.
    Workflows that DO need it (e.g. coder) always pass ``--context-file`` via the
    generated Makefile, so the miss is caught there."""
    if context_file:
        path = Path(context_file)
        if not path.is_file():
            print(
                f"error: --context-file not found: {path}\n"
                "Run `make agent-install` to generate .agents/agents-context.json.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        repo_dir = os.environ.get("AGENT_REPO_DIR", ".")
        agents_dir = Path(repo_dir) / ".agents"
        cli = os.environ.get("AGENT_CLI", "claude").strip().lower()
        per_cli = agents_dir / f"agents-context.{cli}.json"
        path = per_cli if per_cli.is_file() else agents_dir / "agents-context.json"
        if not path.is_file():
            return {}
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot read context manifest {path}: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(raw, dict):
        print(f"error: context manifest {path} must be a JSON object", file=sys.stderr)
        sys.exit(1)
    return _build_manifest_context(raw)


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workflow",
        default=None,
        help="Path to a workflow.yaml, OR a bare workflow NAME (e.g. 'coder') "
        "resolved from the configured prompt library as "
        "<library_dir>/workflows/<name>/workflow.yaml. The library dir comes from "
        "$WORKHORSE_LIBRARY_DIR or library_dir in ~/.config/farrier/config.toml. "
        "May also be given as the first positional argument: "
        "`workhorse run coder` or `workhorse run coder qa`.",
    )
    parser.add_argument(
        "positional",
        nargs="*",
        help="Positional form of --workflow [flow]: `workhorse run <name> [<flow>]`. "
        "The first token is treated as the workflow name when --workflow is omitted; "
        "the optional second token is the flow sub-graph to run standalone.",
    )
    parser.add_argument(
        "--context-file",
        default=None,
        metavar="PATH",
        help="Per-repo farrier context manifest (JSON). Default: "
        "$AGENT_REPO_DIR/.agents/agents-context.json. Provides the template "
        "values, instruction/prompt path maps, and selected-skills set the "
        "library prompts render against. Required.",
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Directory to write run artifacts (default: <cwd>/.agents/runs — "
        "deduced from the directory workhorse is launched in)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Name the stable run dir (<workflow>-<run-id>); default 'default'. "
        "Use distinct ids to keep separate runs of the same workflow side by side.",
    )
    parser.add_argument(
        "--params",
        default=None,
        metavar="JSON",
        help="Inline JSON object of workflow params (key→value) merged into the "
        "starting context, overriding the workflow's own vars. Combined with "
        "--params-file when both are given (inline wins).",
    )
    parser.add_argument(
        "--params-file",
        default=None,
        metavar="PATH",
        help="Path to a JSON file of workflow params (same effect as --params).",
    )
    parser.add_argument(
        "--cli",
        default=None,
        metavar="NAME",
        help="Agent CLI backend to drive this run: claude (default), codex, copilot, "
        "aider, or opencode. Overrides the AGENT_CLI env var. Selection is per-run, "
        "not per-node. To run on an OpenRouter model, use an OpenRouter-native "
        "backend (aider/opencode) and give nodes an 'openrouter/<slug>' model.",
    )
    resume_group = parser.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume-run",
        default=None,
        metavar="PATH_OR_RUN_ID",
        help="Resume a crashed run from its checkpoint. Accepts a run directory "
        "path or a run-dir name under --runs-dir.",
    )
    resume_group.add_argument(
        "--resume-latest",
        action="store_true",
        help="Resume the most recent unfinished run under --runs-dir (errors if none).",
    )
    resume_group.add_argument(
        "--no-cache",
        action="store_true",
        help="Delete the stable run directory before starting, forcing a clean run "
        "from scratch. Mutually exclusive with --resume-run and --resume-latest.",
    )


def _base_library_dir() -> Path | None:
    """The base library root, or None when the `stablemate-library` wheel is absent.

    Discovered with an *optional* import on purpose: the base package depends on
    workhorse (its workflows are run by this CLI), so a hard dependency the other way
    would close a cycle. Absent the wheel, workhorse behaves exactly as before —
    a workflow name resolves only against a configured library."""
    try:
        from stablemate_library import base_dir
    except ImportError:
        return None
    return base_dir()


def _library_layers() -> list[Path]:
    """The library search path for a bare workflow NAME, highest precedence first.

    1. ``$WORKHORSE_LIBRARY_DIR`` env var (explicit override), else the ``library_dir``
       key in workhorse's own config.toml (``workhorse config set-library <path>``) —
       the overlay.
    2. The base library shipped as the `stablemate-library` wheel.

    An overlay shadows the base name-for-name, so a private library can override a
    base workflow by defining one with the same name. Empty when neither exists."""
    layers: list[Path] = []
    env = os.environ.get("WORKHORSE_LIBRARY_DIR")
    if env:
        layers.append(Path(env).expanduser())
    else:
        lib = get_config_value("library_dir")
        if isinstance(lib, str) and lib:
            layers.append(Path(lib).expanduser())
    base = _base_library_dir()
    if base is not None:
        layers.append(base)
    return layers


def _resolve_library_dir() -> Path | None:
    """The highest-precedence library root, or None when there is none.

    Kept for callers that want a single directory; name resolution goes through
    :func:`_library_layers` so a base workflow is still found when an overlay is
    configured but does not define it."""
    layers = _library_layers()
    return layers[0] if layers else None


def _resolve_workflow_path(spec: str) -> Path:
    """Resolve ``--workflow`` as either an explicit path or a bare library name.

    A value that looks like a path — contains a separator, ends in ``.yaml``/
    ``.yml``, or names an existing filesystem entry — is used verbatim. Otherwise it is
    a bare workflow NAME, resolved as ``<layer>/workflows/<name>/workflow.yaml`` against
    each library layer in turn (overlay, then the base library wheel), so
    ``--workflow author`` runs the author workflow wherever it lives."""
    looks_like_path = (
        os.sep in spec
        or (os.altsep is not None and os.altsep in spec)
        or spec.endswith((".yaml", ".yml"))
        or Path(spec).exists()
    )
    if looks_like_path:
        return Path(spec).resolve()

    layers = _library_layers()
    if not layers:
        print(
            f"error: '{spec}' is not a path and no prompt library is available.\n"
            "Install the base library:\n"
            "    pip install stablemate-library\n"
            "or configure an overlay (`workhorse config set-library <path>` / export "
            "WORKHORSE_LIBRARY_DIR), or pass --workflow as a path to a workflow.yaml.",
            file=sys.stderr,
        )
        sys.exit(1)

    for layer in layers:
        candidate = layer / "workflows" / spec / "workflow.yaml"
        if candidate.is_file():
            return candidate.resolve()

    searched = "\n".join(f"  - {layer}" for layer in layers)
    print(
        f"error: no workflow named '{spec}' in any library layer.\nSearched:\n{searched}",
        file=sys.stderr,
    )
    sys.exit(1)


def _run_run(args: argparse.Namespace) -> None:
    # Resolve workflow name/path and optional flow from the two input shapes:
    #   explicit:   --workflow coder [--flow qa]  (args.workflow set, args.positional=[])
    #   positional: coder [qa]                    (args.workflow=None, args.positional=[name, flow?])
    workflow_spec = args.workflow
    flow = getattr(args, "flow", None)  # legacy: flow used to be its own positional
    positional = getattr(args, "positional", []) or []
    if workflow_spec is None:
        if not positional:
            print(
                "error: workflow is required — pass --workflow <name> or use the "
                "positional form: workhorse run <name> [<flow>]",
                file=sys.stderr,
            )
            sys.exit(1)
        workflow_spec = positional[0]
        if len(positional) > 1:
            flow = positional[1]
    elif positional:
        # --workflow given AND positionals present → first positional is the flow
        if len(positional) == 1:
            flow = positional[0]
        else:
            print(
                f"error: unexpected positional arguments {positional[1:]!r} — "
                "when --workflow is given, at most one positional (the flow name) is allowed",
                file=sys.stderr,
            )
            sys.exit(1)

    workflow_path = _resolve_workflow_path(workflow_spec)
    if not workflow_path.exists():
        print(f"error: workflow file not found: {workflow_path}", file=sys.stderr)
        sys.exit(1)

    # The consuming repo is the directory workhorse is launched in — same <cwd>
    # rule as the runs-dir default below. Library scripts (load-config,
    # await-operator, …) resolve the repo root from AGENT_REPO_DIR first and only
    # fall back to walking up from their cwd; but a library-installed workflow runs
    # its scripts with cwd = the workflow's own dir (inside the prompt library, a
    # different repo), so that walk would find the library, not the target repo.
    # Pin AGENT_REPO_DIR to the launch dir when the caller hasn't set it, so every
    # subprocess agrees on the repo without needing the farrier Makefile.
    os.environ.setdefault("AGENT_REPO_DIR", str(Path.cwd().resolve()))

    # --cli (else AGENT_CLI, else default claude) selects the backend for the run.
    if args.cli:
        os.environ["AGENT_CLI"] = args.cli

    # Validate the active backend now so an unknown name fails fast with a clear
    # message instead of mid-run.
    from .runner.backends import get_backend

    try:
        get_backend()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.runs_dir:
        runs_dir = Path(args.runs_dir).resolve()
    else:
        runs_dir = (Path.cwd() / ".agents" / "runs").resolve()

    params = _load_params(args.params, args.params_file)
    context_manifest = _load_context_manifest(args.context_file)

    resume_run_dir: Path | None = None
    if args.resume_run:
        candidate = Path(args.resume_run)
        if not candidate.is_absolute() and not candidate.exists():
            candidate = runs_dir / args.resume_run
        resume_run_dir = candidate.resolve()
        if not resume_run_dir.is_dir():
            print(f"error: resume run dir not found: {resume_run_dir}", file=sys.stderr)
            sys.exit(1)
    elif args.resume_latest:
        resume_run_dir = _find_latest_resumable(runs_dir)
        if resume_run_dir is None:
            print(f"error: no resumable run found under {runs_dir}", file=sys.stderr)
            sys.exit(1)

    # Default behavior is auto: a single stable run dir per program that is resumed
    # in place (continuing the same session/context), or started fresh in that dir
    # if absent. The explicit --resume-run/--resume-latest flags above are manual
    # overrides that target a specific dir instead. auto stays on either way — when
    # resume_run_dir is set, run() uses it directly and skips auto resolution.
    sys.exit(
        run(
            workflow_path,
            runs_dir,
            resume_run_dir,
            auto=True,
            run_id=args.run_id,
            params=params,
            context_manifest=context_manifest,
            flow=flow,
            no_cache=getattr(args, "no_cache", False),
        )
    )


def _add_test_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "workflow_dir",
        help="Directory containing workflow.yaml and a tests/ subdirectory",
    )
    parser.add_argument(
        "--filter",
        "-k",
        default=None,
        metavar="PATTERN",
        help="Only run tests matching this pytest -k expression",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Pass -v to pytest for verbose output",
    )


def _run_test(args: argparse.Namespace) -> None:
    workflow_dir = Path(args.workflow_dir).resolve()
    tests_dir = workflow_dir / "tests"
    if not tests_dir.is_dir():
        print(f"error: no tests/ directory found in {workflow_dir}", file=sys.stderr)
        sys.exit(1)
    try:
        import pytest as _pytest  # noqa: PLC0415
    except ImportError:
        print(
            "error: pytest is required to run workflow tests.\n"
            "Install it with: pip install 'workhorse-agent[test]'",
            file=sys.stderr,
        )
        sys.exit(1)
    pytest_args = [str(tests_dir)]
    if args.filter:
        pytest_args += ["-k", args.filter]
    if args.verbose:
        pytest_args += ["-v"]
    sys.exit(_pytest.main(pytest_args))


def _add_dot_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workflow", required=True, help="Path to workflow.yaml")
    parser.add_argument(
        "--pin",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help="Pin a branch variable so any branch on that path collapses to its "
        "single resolved edge (and the unreachable subgraph is pruned). Repeatable. "
        "For the coder workflow: --pin mode=epic or --pin mode=story.",
    )
    parser.add_argument(
        "--leaf",
        action="append",
        default=None,
        metavar="NODE",
        help="Render NODE as a dead-end: suppress its outgoing edges so reachability "
        "stops there. Use to cut a cross-view bridge not gated by a pinned branch. "
        "Repeatable. For the coder story view: --leaf replan_epic.",
    )
    parser.add_argument(
        "--name",
        default=None,
        metavar="NAME",
        help="Override the digraph identifier (default: sanitized workflow name).",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Write the DOT output to this file (default: stdout).",
    )


def _parse_pins(raw: list[str] | None) -> dict[str, str]:
    """Parse repeated --pin KEY=VALUE flags into a dict (exits on a malformed entry)."""
    pins: dict[str, str] = {}
    for item in raw or []:
        key, sep, value = item.partition("=")
        if not sep or not key:
            print(f"error: --pin must be KEY=VALUE (got '{item}')", file=sys.stderr)
            sys.exit(1)
        pins[key] = value
    return pins


def _run_dot(args: argparse.Namespace) -> None:
    from .graph.dot import to_dot

    workflow_path = Path(args.workflow).resolve()
    if not workflow_path.exists():
        print(f"error: workflow file not found: {workflow_path}", file=sys.stderr)
        sys.exit(1)
    try:
        graph = load_workflow(workflow_path)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    pins = _parse_pins(args.pin)
    leaves = set(args.leaf or [])
    dot = to_dot(graph, pins=pins, name=args.name, leaves=leaves)

    if args.output:
        Path(args.output).write_text(dot)
        print(f"[workhorse] wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(dot)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workhorse",
        description="Fail-soft runner for YAML-defined agent workflows.",
    )
    sub = parser.add_subparsers(dest="command")

    # run (default)
    run_p = sub.add_parser("run", help="Execute a workflow (default)")
    _add_run_args(run_p)

    # test
    test_p = sub.add_parser(
        "test",
        help="Run pytest tests from a workflow's tests/ directory",
    )
    _add_test_args(test_p)

    # dot
    dot_p = sub.add_parser(
        "dot",
        help="Render a workflow graph to Graphviz DOT",
    )
    _add_dot_args(dot_p)

    # config — mirrors farrier's interface so agents.mk / scripts can call either tool
    config_p = sub.add_parser("config", help="Manage the workhorse/farrier home config")
    config_sub = config_p.add_subparsers(dest="config_command", required=True)
    # show [key] — print all keys as key=value lines, or a single bare value (farrier-compatible)
    show_p = config_sub.add_parser(
        "show", help="Print all config keys as key=value lines, or a single bare value"
    )
    show_p.add_argument(
        "key",
        nargs="?",
        default=None,
        help="If given, print only the value of this key",
    )
    # set-library / set-stablemate — write to the farrier config file (same file farrier reads)
    set_lib_p = config_sub.add_parser(
        "set-library", help="Record the prompt library directory in the home config"
    )
    set_lib_p.add_argument(
        "path", type=Path, help="Path to the library (the agents/ tree)"
    )
    set_sm_p = config_sub.add_parser(
        "set-stablemate", help="Record the stablemate checkout path in the home config"
    )
    set_sm_p.add_argument("path", type=Path, help="Path to the stablemate checkout")
    # list / get — workhorse-specific power/model config (workhorse's own config.toml)
    config_sub.add_parser(
        "list", help="Print the loaded workhorse config (power mappings etc.)"
    )
    get_p = config_sub.add_parser("get", help="Print one workhorse config value")
    get_p.add_argument("name", help="Config key, e.g. power or power.high.claude")

    # version
    sub.add_parser("version", help="Print the installed workhorse-agent version")

    return parser


def main() -> None:
    argv = sys.argv[1:]
    parser = _build_parser()

    # Keep `workhorse --workflow ...` working: if no recognised subcommand is
    # given, inject `run` so existing invocations are unchanged.
    # Exception: bare --help/-h should show the top-level subcommand listing.
    _SUBCOMMANDS = {"run", "test", "dot", "config", "version"}
    if argv and argv[0] in ("-h", "--help"):
        pass  # let the top-level parser handle it
    elif not argv or argv[0] not in _SUBCOMMANDS:
        argv = ["run"] + list(argv)

    args = parser.parse_args(argv)

    if args.command == "version":
        print(importlib.metadata.version("workhorse-agent"))
        return

    if args.command == "test":
        _run_test(args)
        return

    if args.command == "dot":
        _run_dot(args)
        return

    if args.command == "config":
        _run_config(args)
        return

    _run_run(args)


def _run_config(args: argparse.Namespace) -> None:
    if args.config_command == "set-library":
        path = Path(args.path).expanduser().resolve()
        write_config_key("library_dir", str(path))
        print(f"library_dir={path}")
        return

    if args.config_command == "set-stablemate":
        path = Path(args.path).expanduser().resolve()
        write_config_key("stablemate_dir", str(path))
        print(f"stablemate_dir={path}")
        return

    cfg = load_config()

    if args.config_command == "show":
        if args.key:
            value = cfg.get(args.key)
            if value is None:
                print(
                    f"error: '{args.key}' is not set in {config_path()}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(value)
        else:
            for key, value in cfg.items():
                print(f"{key}={value}")
        return

    if args.config_command == "list":
        print(f"# {config_path()}")
        print(json.dumps(cfg, indent=2, sort_keys=True))
        return

    if args.config_command == "get":
        value = get_config_value(args.name, cfg)
        if value is None:
            return
        if isinstance(value, (dict, list)):
            print(json.dumps(value, indent=2, sort_keys=True))
        else:
            print(value)
