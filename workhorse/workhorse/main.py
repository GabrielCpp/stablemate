from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
import sys
import tomllib
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
from .runner.script import ScriptExitError

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
) -> int:
    graph = load_workflow(workflow_path)
    workflow_dir = workflow_path.parent

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

    session_id_path = writer.run_dir / ".session_id"

    try:
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
                        print("[workhorse] This is a transient error - the workflow can be resumed", file=sys.stderr)
                        print(f"[workhorse] Resume command: --resume-run {writer.run_dir}", file=sys.stderr)
                    else:
                        print("[workhorse] This appears to be a persistent error", file=sys.stderr)
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
                except ScriptExitError as e:
                    # Propagate the script's own exit code so callers can distinguish
                    # expected halts (e.g. await_operator exits 2 for "blocked") from
                    # genuine crashes (exit 1).
                    print(f"[workhorse] ERROR in script node '{node.id}': {e}", file=sys.stderr)
                    sys.exit(e.exit_code)
                except Exception as e:
                    # Log script errors with context
                    print(f"[workhorse] ERROR in script node '{node.id}': {e}", file=sys.stderr)
                    print("[workhorse] Script execution failed - workflow can be resumed after fixing", file=sys.stderr)
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

    except KeyboardInterrupt:
        agent_runner.terminate_active()
        print("\n[workhorse] interrupted — run paused.", file=sys.stderr)
        print(f"[workhorse] resume with: workhorse --resume-run {writer.run_dir}", file=sys.stderr)
        sys.exit(130)


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
    if manifest_skill_dir and target_skill_dir and target_skill_dir != manifest_skill_dir:
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
        required=True,
        help="Path to a workflow.yaml, OR a bare workflow NAME (e.g. 'author') "
        "resolved from the configured prompt library as "
        "<library_dir>/workflows/<name>/workflow.yaml. The library dir comes from "
        "$WORKHORSE_LIBRARY_DIR or library_dir in ~/.config/farrier/config.toml.",
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


def _resolve_library_dir() -> Path | None:
    """Locate the installed prompt library (the dir holding ``workflows/<name>/``).

    Resolution order: ``$WORKHORSE_LIBRARY_DIR`` (explicit override), then the
    ``library_dir`` key in ``~/.config/farrier/config.toml`` — the same home config
    farrier and the generated Makefile read (``farrier config show library_dir``),
    so a bare ``--workflow <name>`` finds the same library the rest of the toolchain
    uses. Returns ``None`` when neither is set."""
    env = os.environ.get("WORKHORSE_LIBRARY_DIR")
    if env:
        return Path(env).expanduser()
    cfg = Path.home() / ".config" / "farrier" / "config.toml"
    if cfg.is_file():
        try:
            data = tomllib.loads(cfg.read_text())
        except (OSError, tomllib.TOMLDecodeError):
            return None
        lib = data.get("library_dir")
        if isinstance(lib, str) and lib:
            return Path(lib).expanduser()
    return None


def _resolve_workflow_path(spec: str) -> Path:
    """Resolve ``--workflow`` as either an explicit path or a bare library name.

    A value that looks like a path — contains a separator, ends in ``.yaml``/
    ``.yml``, or names an existing filesystem entry — is used verbatim. Otherwise
    it is treated as a bare workflow NAME and resolved against the configured
    prompt library as ``<library_dir>/workflows/<name>/workflow.yaml`` (so
    ``--workflow author`` runs the library's author workflow without a full path)."""
    looks_like_path = (
        os.sep in spec
        or (os.altsep is not None and os.altsep in spec)
        or spec.endswith((".yaml", ".yml"))
        or Path(spec).exists()
    )
    if looks_like_path:
        return Path(spec).resolve()
    library = _resolve_library_dir()
    if library is None:
        print(
            f"error: '{spec}' is not a path and no prompt library is configured.\n"
            "Set library_dir in ~/.config/farrier/config.toml (or export "
            "WORKHORSE_LIBRARY_DIR), or pass --workflow as a path to a workflow.yaml.",
            file=sys.stderr,
        )
        sys.exit(1)
    return (library / "workflows" / spec / "workflow.yaml").resolve()


def _run_run(args: argparse.Namespace) -> None:
    workflow_path = _resolve_workflow_path(args.workflow)
    if not workflow_path.exists():
        print(f"error: workflow file not found: {workflow_path}", file=sys.stderr)
        sys.exit(1)

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
        )
    )


def _add_test_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "workflow_dir",
        help="Directory containing workflow.yaml and a tests/ subdirectory",
    )
    parser.add_argument(
        "--filter", "-k",
        default=None,
        metavar="PATTERN",
        help="Only run tests matching this pytest -k expression",
    )
    parser.add_argument(
        "--verbose", "-v",
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
        "--output", "-o",
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
            print(
                f"error: --pin must be KEY=VALUE (got '{item}')", file=sys.stderr
            )
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

    # version
    sub.add_parser("version", help="Print the installed workhorse-agent version")

    return parser


def main() -> None:
    argv = sys.argv[1:]
    parser = _build_parser()

    # Keep `workhorse --workflow ...` working: if no recognised subcommand is
    # given, inject `run` so existing invocations are unchanged.
    # Exception: bare --help/-h should show the top-level subcommand listing.
    _SUBCOMMANDS = {"run", "test", "dot", "version"}
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

    _run_run(args)
