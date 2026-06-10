from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from typing import Any

from .artifacts import ArtifactWriter
from .graph.context import WorkflowContext
from .graph.loader import load_workflow
from .graph.nodes import AgentNode, BranchNode, ScriptNode, TerminalNode
from .runner import agent as agent_runner
from .runner import branch as branch_runner
from .runner import script as script_runner
from .runner.agent import ClaudeInvocationError


def run(
    workflow_path: Path,
    runs_dir: Path,
    resume_run_dir: Path | None = None,
    auto: bool = True,
    run_id: str | None = None,
    params: dict[str, Any] | None = None,
) -> int:
    graph = load_workflow(workflow_path)
    workflow_dir = workflow_path.parent

    # Default (auto): one stable run dir per (workflow, program) that we resume in
    # place. The run *is* the research session — its full context (counters, gate
    # selection, ladder position) lives in the checkpoint, so we continue the same
    # graph with the same state rather than re-deriving it. Delete the dir to start
    # over. If it has no checkpoint yet, start fresh IN that same stable dir. An
    # explicit resume_run_dir (manual --resume-*) overrides this.
    fresh_run_id = run_id
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
        ctx = WorkflowContext(initial=checkpoint["context"])
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
                ctx = WorkflowContext(initial=after)
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
        ctx = WorkflowContext(initial={**graph.vars, **(params or {})})
        writer = ArtifactWriter(graph.name, runs_dir, run_id=fresh_run_id)
        current_id = graph.start
        print(f"[workhorse] starting '{graph.name}' (run: {writer.run_dir.name})")

    session_id_path = writer.run_dir / ".session_id"

    while True:
        node = graph.nodes[current_id]

        if isinstance(node, TerminalNode):
            writer.write_final_context(ctx.as_dict())
            writer.finish(terminal=node.type)
            success = node.type == "terminal"
            print(f"[workhorse] {node.type.upper()} — run artifacts: {writer.run_dir}")
            return 0 if success else 1

        # Checkpoint the node we're about to run and the context going into it.
        # If this node crashes (e.g. spending cap), `--resume-run` re-enters here.
        writer.write_checkpoint(current_id, ctx.as_dict())

        if isinstance(node, AgentNode):
            print(f"[workhorse] agent  → {node.id}")
            try:
                # run_agent is self-healing: it retries transient failures, reframes
                # the prompt, and finally defaults the node's outputs so the run
                # advances rather than crashing. A ClaudeInvocationError only
                # escapes when defaulting is disabled (AGENT_USE_DEFAULT_OUTPUTS=false).
                prompt, outputs = agent_runner.run_agent(
                    node, ctx, workflow_dir, session_id_path,
                    resume_session=resume_interrupted_node,
                )
                # The resume only applies to the first re-entered node; every node
                # the run advances to afterward is a fresh prompt / clean context.
                resume_interrupted_node = False

                ctx.merge(outputs)
                if node.next is None:
                    raise RuntimeError(f"AgentNode '{node.id}' has no 'next' and is not terminal")
                writer.write_step(node.id, prompt, outputs, ctx.as_dict(), next_node=node.next)
                current_id = node.next

            except ClaudeInvocationError as e:
                print(f"[workhorse] ERROR in node '{node.id}': {e}", file=sys.stderr)
                if e.transient:
                    print(f"[workhorse] This is a transient error - the workflow can be resumed", file=sys.stderr)
                    print(f"[workhorse] Resume command: --resume-run {writer.run_dir}", file=sys.stderr)
                else:
                    print(f"[workhorse] This appears to be a persistent error", file=sys.stderr)
                raise

        elif isinstance(node, ScriptNode):
            # A re-entered script/branch carries no Claude session; clear the flag
            # so a later agent node isn't mistaken for an interrupted continuation.
            resume_interrupted_node = False
            print(f"[workhorse] script → {node.id}")
            try:
                cmd_str, outputs = script_runner.run_script(node, ctx, workflow_dir)
                ctx.merge(outputs)
                if node.next is None:
                    raise RuntimeError(f"ScriptNode '{node.id}' has no 'next' and is not terminal")
                writer.write_step(node.id, cmd_str, outputs, ctx.as_dict(), next_node=node.next)
                current_id = node.next
            except Exception as e:
                # Log script errors with context
                print(f"[workhorse] ERROR in script node '{node.id}': {e}", file=sys.stderr)
                print(f"[workhorse] Script execution failed - workflow can be resumed after fixing", file=sys.stderr)
                print(f"[workhorse] Resume command: --resume-run {writer.run_dir}", file=sys.stderr)
                raise

        elif isinstance(node, BranchNode):
            resume_interrupted_node = False
            print(f"[workhorse] branch → {node.id}")
            next_id, value = branch_runner.evaluate(node, ctx)
            writer.write_branch(node.id, node.path, value, next_id)
            current_id = next_id

        else:
            raise RuntimeError(f"Unknown node type: {type(node)}")


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
    already holds a checkpoint to continue, else None (caller starts fresh)."""
    rid = run_id or "default"
    stable = runs_dir / f"{workflow_name}-{rid}"
    resume = stable if (stable / ArtifactWriter.CHECKPOINT_FILE).exists() else None
    return rid, resume


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
            print(f"error: {label} must be a JSON object (key→value map)", file=sys.stderr)
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


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workflow", required=True, help="Path to workflow.yaml")
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Directory to write run artifacts (default: <workflow-dir>/runs)",
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
        help="Agent CLI backend to drive this run (e.g. 'claude'). Overrides the "
        "AGENT_CLI env var; default 'claude'. Selection is per-run, not per-node.",
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


def _run_run(args: argparse.Namespace) -> None:
    # Per-run CLI backend selection. --cli wins over the AGENT_CLI env; validate
    # now so an unknown name fails fast with a clear message instead of mid-run.
    if args.cli:
        os.environ["AGENT_CLI"] = args.cli
    from .runner.backends import get_backend
    try:
        get_backend()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    workflow_path = Path(args.workflow).resolve()
    if not workflow_path.exists():
        print(f"error: workflow file not found: {workflow_path}", file=sys.stderr)
        sys.exit(1)

    if args.runs_dir:
        runs_dir = Path(args.runs_dir).resolve()
    else:
        runs_dir = (workflow_path.parent / "runs").resolve()

    params = _load_params(args.params, args.params_file)

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
        )
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="workhorse",
        description="Fail-soft runner for YAML-defined agent workflows.",
    )
    sub = parser.add_subparsers(dest="command")

    # run (default)
    run_p = sub.add_parser("run", help="Execute a workflow (default)")
    _add_run_args(run_p)

    # version
    sub.add_parser("version", help="Print the installed workhorse-agent version")

    return parser


def main() -> None:
    argv = sys.argv[1:]
    parser = _build_parser()

    # Keep `workhorse --workflow ...` working: if no recognised subcommand is
    # given, inject `run` so existing invocations are unchanged.
    # Exception: bare --help/-h should show the top-level subcommand listing.
    _SUBCOMMANDS = {"run", "version"}
    if argv and argv[0] in ("-h", "--help"):
        pass  # let the top-level parser handle it
    elif not argv or argv[0] not in _SUBCOMMANDS:
        argv = ["run"] + list(argv)

    args = parser.parse_args(argv)

    if args.command == "version":
        print(importlib.metadata.version("workhorse-agent"))
        return

    _run_run(args)
