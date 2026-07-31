"""Genesis's deterministic work: classify the target, make a repo, configure it, check it.

Ports `resolve-genesis-target.py`, `genesis-git-init.py`, `write-genesis-agents-yml.py`,
`init-genesis-skeleton.py`, `install-genesis-farrier.py` and `validate-genesis.py`.

**Genesis carries zero stack knowledge, and that is enforced, not aspired to.** Every
stack-specific value — which packs to install, which scaffold to render, the service root,
the init command, the marker files — arrives as a flow parameter and is written through
verbatim. `scripts/check_public.py` asserts no base workflow may depend on the private
overlay, and the stack packs live there; a base workflow that knew `go` meant `go.mod`
would be a base workflow that knows the overlay's contents.

Two shapes are worth naming before reading further:

* **Repo state and service state are tracked separately.** A monorepo grows one service at
  a time, so keying the skeleton step on the *repo* would mean the second run into an
  existing monorepo (adding `web` beside `api`) sees `existing`, skips the skeleton, and no
  second service could ever be created.
* **Two external commands run through `_run`, and git through `_git`**, both module-level
  so a test can replace them by attribute. The YAML's scripts called `subprocess.run`
  inline, which was fine for a subprocess node and is not for an in-process one.

The scripts' remediation sentences are kept verbatim in the notes. They are the only thing
an operator reading a failed genesis run has, and several name the exact `--params` to
re-run with.
"""
from __future__ import annotations

import copy
import io
import json
import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ostler import path as okf_path
from ostler.model import find_root
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import ScalarString
from workhorse_workflows.coder.shared.contract import service_problems
from workhorse_workflows.coder.shared import stubs
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.genesis import (
    AgentsYml,
    FarrierInstall,
    GenesisReport,
    GitInit,
    Skeleton,
    TargetClassification,
)

#: The three assistant backends `farrier install` knows about. Written as a full map with
#: booleans rather than as the enabled subset, because that is the shape farrier reads.
ASSISTANTS = ("claude", "codex", "copilot")


def _run(args: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    """An external CLI, captured. Module-level so a test can replace it by attribute."""
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                          check=False, timeout=timeout)


def _git(target: Path, *args: str) -> subprocess.CompletedProcess:
    """`git` in `target`, captured, never raising on a non-zero exit."""
    return subprocess.run(["git", *args], cwd=str(target), capture_output=True,
                          text=True, check=False, timeout=30)


def _head_sha(target: Path) -> str:
    """The current HEAD, or `""` when HEAD is unborn."""
    result = _git(target, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else ""


# ── classify ──────────────────────────────────────────────────────────────────


@blueprint.node(stub=stubs.classified)
def resolve_genesis_target(
    logger: logging.Logger,
    target: str = "",
    service: str = "",
    service_root: str = "",
    marker: str = "",
) -> TargetClassification:
    """Classify the target before anything mutates it, so genesis is safe to re-run.

    Genesis is re-run constantly during setup iteration, and this node is what makes that
    safe: the flow routes an already-initialised repo to config-refresh-only instead of
    re-scaffolding over the top of real work.

    * `absent` — the directory does not exist, or exists and is empty. Full genesis. An
      existing-but-empty directory is indistinguishable from an absent one here, and
      calling it `partial` would route a fresh `mkdir` away from full genesis.
    * `partial` — content, but no `agents.yml`. Full genesis; nothing already there is
      removed.
    * `existing` — an `agents.yml` is there. Config refresh only, never re-scaffold.

    A blank `target` reports `ok=False`, which the flow turns into a failure. Without it
    the whole flow runs against an empty path: every step no-ops with a note, and the run
    still reaches the conventions agent, burning a model call to discover there is nothing
    there.
    """
    if not target:
        logger.error("no target directory was provided")
        return TargetClassification(
            note="no target directory was provided; "
                 "pass --params '{\"target\":\"<path>\", ...}'",
        )

    root = Path(target).expanduser().resolve()
    state = _classify(root)

    # Keyed on this service's marker, independent of repo state — see the docstring.
    service_dir = (root / service_root) if service_root else root
    service_state = "existing" if (marker and (service_dir / marker).is_file()) else "absent"

    note = {
        "absent": f"{root} does not exist yet — running full genesis",
        "partial": (f"{root} exists with content but has no agents.yml — running full "
                    f"genesis; nothing already there will be removed"),
        "existing": (f"{root} already has an agents.yml — refreshing config only, "
                     f"not re-scaffolding"),
    }[state]
    if service_root:
        note += (f"; service '{service or service_root}' at {service_root}/ is "
                 f"{service_state} (marker: {marker or '<none declared>'})")
    logger.info("%s", note)
    return TargetClassification(
        ok=True,
        target_dir=str(root),
        target_state=state,
        service_state=service_state,
        service=service,
        note=note,
    )


def _classify(target: Path) -> str:
    if (target / "agents.yml").is_file():
        return "existing"
    if not target.exists() or not any(target.iterdir()):
        return "absent"
    return "partial"


# ── make it a repo ────────────────────────────────────────────────────────────


@blueprint.node
def genesis_git_init(logger: logging.Logger, target_dir: str = "") -> GitInit:
    """`git init` the target and land one initial commit. The first mutating step.

    The ordering is load-bearing rather than stylistic. `ostler.model.find_root` walks *up*
    from its starting directory looking for `.git`, `docs/`, `ostler.yml` or `agents.yml`.
    A brand-new directory has none of them, so every ostler call made before this node
    binds to whichever **ancestor** repo happens to be above the target, silently: ids
    allocated out of the parent's registry, `docs/*` resolving into the parent's tree, and
    nothing erroring. The run looks fine and writes into the wrong repository. Creating
    `.git` first gives `find_root` a boundary to stop at, which closes that off
    structurally; `validate_genesis` then asserts the binding landed where intended.

    The initial commit matters as much: an unborn HEAD has no commit for a branch to point
    at, and the author workflow's `branch_author` cuts one as one of its first acts.

    Local-only by design — no remote is added. PR delivery is optional downstream.

    `target_state` is not read: the YAML passed it and the script ignored it, and the
    branch that would have used it (skip when `existing`) is upstream in the flow.
    """
    if not target_dir:
        return GitInit(note="no target_dir was provided")

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    if (target / ".git").exists():
        sha = _head_sha(target)
        if sha:
            logger.info("%s is already a git repo at %s", target, sha[:8])
            return GitInit(ready=True, initial_commit=sha,
                           note=f"already a git repo (HEAD {sha[:8]})")
        # A .git with an unborn HEAD still needs the initial commit below.
        logger.info("%s has .git but an unborn HEAD — landing the initial commit", target)
    else:
        result = _git(target, "init", "-q")
        if result.returncode != 0:
            return GitInit(note=f"git init failed: {result.stderr.strip()}")

    # A commit needs *something* tracked. A README is the least surprising choice and the
    # file a human opening the new repo looks for first.
    readme = target / "README.md"
    if not readme.exists():
        readme.write_text(f"# {target.name}\n", encoding="utf-8")

    _git(target, "add", "-A")
    result = _git(target, "commit", "-q", "-m", "Initial commit")
    if result.returncode != 0 and not _head_sha(target):
        return GitInit(note=f"initial commit failed: {(result.stderr or result.stdout).strip()}")

    sha = _head_sha(target)
    logger.info("initialised %s at %s", target, sha[:8])
    return GitInit(
        ready=True,
        initial_commit=sha,
        note=f"git initialised with an initial commit ({sha[:8]}), no remote configured",
    )


# ── configure it ──────────────────────────────────────────────────────────────


@blueprint.node
def write_agents_yml(
    logger: logging.Logger,
    target_dir: str = "",
    service: str = "",
    packs: Sequence[str] = (),
    service_root: str = "",
    markers: Sequence[str] = (),
    workflows: Sequence[str] = ("coder",),
    scaffolds: Sequence[str] = (),
    assistants: Sequence[str] = ("claude",),
) -> AgentsYml:
    """Merge this service into the repo's `agents.yml` — packs, scaffolds, `workspace:`.

    The `workspace:` block is what lets the planner target the service at all: it is where
    `service_roots` and `service_markers` come from, and `resolve_workspace` merges it into
    the repo record `validate_plan_context` reads.

    Existing files are **merged, not overwritten**. On a re-run the repo may carry
    hand-edits, and clobbering them would make genesis unsafe to re-run — which is the
    whole point of the classification step upstream.

    **Comments are hand-edits too.** A `safe_load`/`safe_dump` round trip preserves every
    value and destroys every comment, which on a mature repo is the larger loss: an
    `agents.yml` earns its rationale over time ("this port is taken by the other stack",
    "these keys are omitted on purpose"), and none of it is recoverable from the data. So
    the file goes through `ruamel.yaml`'s round-trip mode, which carries comments, key
    order and flow style through the merge, and is left untouched when the merge changes
    nothing.

    `scaffolds` arrives as `"<id>[:<dir>]"` pairs and only the ids are written here — the
    dir is `install_farrier`'s business. `farrier scaffold <id>` refuses to render an id
    that is not enabled in this list, so the scaffold step silently renders nothing unless
    this node declares them first.
    """
    if not target_dir:
        return AgentsYml(note="no target_dir was provided")
    target = Path(target_dir)
    if not target.is_dir():
        return AgentsYml(note=f"target {target} is not a directory")

    scaffold_ids = [s for s in (entry.partition(":")[0].strip() for entry in scaffolds) if s]

    # The repo's name is its directory name — NOT the service's. One monorepo holds many
    # services, and two things key off this: `resolve_workspace` keys the workspace on it
    # (so `validate_plan_context` resolves services under it), and farrier derives the
    # generated-skill prefix from it. Using the first surface's service name produced a
    # workspace keyed on "api" and 49 skills named `api-flutter-*`.
    repo_name = target.name
    path = target / "agents.yml"

    try:
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        return AgentsYml(note=f"existing agents.yml is unreadable ({exc}); refusing to clobber it")

    yml = _yaml(source)
    data: dict = {}
    if path.is_file():
        try:
            data = yml.load(source) or {}
        except (YAMLError, OSError) as exc:
            return AgentsYml(
                note=f"existing agents.yml is unreadable ({exc}); refusing to clobber it"
            )
        if not isinstance(data, dict):
            return AgentsYml(note="existing agents.yml is not a mapping; refusing to clobber it")

    # Mutate the loaded document in place rather than copying into a plain dict: the
    # comments ride on the loaded mapping, and a `dict(data)` would drop every one of them.
    had_existing = bool(data)
    before = copy.deepcopy(data)
    data.setdefault("repo", {})
    if isinstance(data["repo"], dict):
        data["repo"].setdefault("name", repo_name)

    # `farrier install` hard-exits with "No agents selected in config" when this key is
    # absent, so omitting it made install fail outright — which then surfaced downstream as
    # an empty instructions map and sent validate_genesis into a repair loop for something
    # entirely deterministic. setdefault, not assignment: a repo that has already chosen
    # its assistants keeps that choice across a config-refresh re-run.
    data.setdefault("agents", {name: name in assistants for name in ASSISTANTS})

    # Union rather than replace: a re-run must not drop packs or workflows a human added.
    for key, values in (("packs", list(packs)), ("workflows", list(workflows)),
                        ("scaffolds", scaffold_ids)):
        if values:
            _assign_seq(data, key, list(dict.fromkeys([*(data.get(key) or []), *values])))

    # In place, again — a `dict(...)` copy here is what would strip the comments a monorepo
    # writes into its own workspace block (which ports are taken, why a key is omitted).
    if not isinstance(data.get("workspace"), dict):
        data["workspace"] = {}
    workspace = data["workspace"]
    workspace.setdefault("type", "mono")
    for key, values in (("service_roots", [service_root] if service_root else []),
                        ("service_markers", list(markers))):
        if values:
            _assign_seq(workspace, key, list(dict.fromkeys([*(workspace.get(key) or []), *values])))

    if data == before and path.is_file():
        note = f"agents.yml for repo '{repo_name}' already carries this service; left untouched"
        logger.info("%s", note)
        return AgentsYml(path="agents.yml", note=note)

    buf = io.StringIO()
    yml.dump(data, buf)
    path.write_text(buf.getvalue(), encoding="utf-8")
    enabled = ", ".join(sorted(k for k, v in data["agents"].items() if v)) or "<none>"
    note = (f"{'updated' if had_existing else 'wrote'} agents.yml for repo '{repo_name}'"
            f"{f", service '{service}'" if service else ''} "
            f"(packs: {', '.join(packs) or '<none>'}; "
            f"scaffolds: {', '.join(scaffold_ids) or '<none>'}; "
            f"agents: {enabled}; "
            f"service_roots: {', '.join(workspace.get('service_roots') or []) or '<none>'}; "
            f"service_markers: {', '.join(workspace.get('service_markers') or []) or '<none>'})")
    logger.info("%s", note)
    return AgentsYml(written=True, path="agents.yml", note=note)


def _yaml(source: str = "") -> YAML:
    """Round-trip loader/dumper: comments, key order and flow style survive the merge.

    `width` is set far above any real line because ruamel wraps long scalars at 80 by
    default — which would reflow a hand-written value the merge never touched. The cost is
    the mirror case: a *plain* scalar the author wrapped by hand comes back on one long
    line, because plain multi-line scalars fold to a single string at parse time and their
    break positions are simply not in the loaded document. A block scalar (`>-`) is
    round-tripped byte for byte, so that is the shape to reach for when the wrapping of a
    long prose value matters.

    `source` is the existing file's text, read for the one thing round-trip mode does
    *not* remember: how far its block sequences are indented. Left at ruamel's default,
    every hand-written `  - go` comes back as `- go` — a diff touching every list in the
    file, which buries the two lines the merge actually changed.
    """
    y = YAML()  # round-trip mode
    y.preserve_quotes = True
    y.default_flow_style = False
    y.width = 4096
    seq = _sequence_indent(source)
    y.indent(mapping=2, sequence=seq + 2, offset=seq)
    return y


def _sequence_indent(source: str, default: int = 2) -> int:
    """How far `source` indents a top-level block-sequence item, or `default`.

    The shallowest `- ` in the file is the top-level one; anything deeper is nested and
    would over-indent the whole document if taken as the baseline.
    """
    indents = [len(line) - len(line.lstrip(" ")) for line in source.splitlines()
               if line.lstrip(" ").startswith("- ") or line.strip() == "-"]
    return min(indents) if indents else default


def _assign_seq(mapping: dict, key: str, merged: list) -> None:
    """Set `mapping[key]` to `merged`, keeping the existing sequence node when possible.

    `merged` always starts with the current entries, so the normal case is "append the new
    tail" — done in place so ruamel keeps the node's own style and comments. A flow
    sequence (`service_roots: ["api", "web"]`) rewritten as a fresh list would come back as
    a block list, reflowing a line the merge had no business touching.
    """
    current = mapping.get(key)
    if isinstance(current, list) and list(current) == merged[:len(current)]:
        current.extend(_like(current[0] if current else None, item)
                       for item in merged[len(current):])
        return
    mapping[key] = merged


def _like(sibling, value: str):
    """Return `value` quoted the way `sibling` is quoted.

    ruamel remembers the quoting of scalars it *loaded*, but a plain `str` appended next to
    them dumps bare — leaving `["api", "web", docs-api]`, which reads as a typo rather than
    as an edit. Mirroring the neighbour keeps the line looking hand-written.
    """
    return type(sibling)(value) if isinstance(sibling, ScalarString) else value


# ── make the service real ─────────────────────────────────────────────────────


@blueprint.node(stub=stubs.built)
def init_skeleton(
    logger: logging.Logger,
    target_dir: str = "",
    service_root: str = "",
    init_cmd: str = "",
    marker: str = "",
) -> Skeleton:
    """Run the stack's native init tooling, then assert it produced the marker.

    This is what makes a scaffolded folder into a *service*. Scaffolds seed a directory and
    a `.gitignore`; they do not produce `go.mod` / `package.json` / `pubspec.yaml`, and
    those marker files are precisely what `validate_plan_context` looks for when deciding
    whether the planner may target a service. So genesis shells out to the real tool rather
    than templating a fake skeleton — the layout then matches whatever that ecosystem
    currently generates, which is not something a library snapshot can stay correct about.

    The command and the marker are **flow parameters, not built-in knowledge**; farrier's
    pack schema merges exactly five set-valued keys with no slot for an init command, so
    parameters are the honest place for this until the shape has been proven across all
    four stacks. Inventing a pack `genesis:` block before then is how you get a schema you
    regret.

    Idempotent: if the marker is already present the command is skipped, because `go mod
    init` and friends fail or clobber on re-run.
    """
    if not target_dir:
        return Skeleton(note="no target_dir was provided")
    target = Path(target_dir)
    if not target.is_dir():
        return Skeleton(note=f"target {target} is not a directory")

    service_dir = (target / service_root) if service_root else target
    service_dir.mkdir(parents=True, exist_ok=True)
    marker_rel = f"{service_root}/{marker}".lstrip("/") if service_root else marker

    if marker and (service_dir / marker).exists():
        logger.info("%s already present — skipping init", marker_rel)
        return Skeleton(
            ok=True,
            marker_path=marker_rel,
            note=f"{marker_rel} already present; native init skipped (idempotent re-run)",
        )

    if not init_cmd:
        return Skeleton(note=(
            f"no init_cmd was provided and {marker_rel or '<no marker>'} does not exist — "
            f"pass the stack's native init command as a flow param, e.g. "
            f"--params '{{\"init_cmd\":\"go mod init example.com/api\",\"marker\":\"go.mod\"}}'"
        ))

    logger.info("running init in %s: %s", service_dir, init_cmd)
    result = subprocess.run(init_cmd, cwd=str(service_dir), shell=True, capture_output=True,
                            text=True, check=False, timeout=900)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return Skeleton(note=f"init_cmd failed ({init_cmd}): {detail}")

    # The command exiting 0 is not proof it made a service — some generators write into a
    # subdirectory, or no-op when they think one already exists. The marker is the proof.
    if marker and not (service_dir / marker).exists():
        return Skeleton(note=(
            f"init_cmd succeeded but {marker_rel} was not created. The service is not real "
            f"to validate-plan-context.py without it — check whether the tool wrote into a "
            f"subdirectory of {service_dir}, and adjust service_root or init_cmd."
        ))

    note = f"native init ran in {service_root or '.'}; {marker_rel} present"
    logger.info("%s", note)
    return Skeleton(ok=True, marker_path=marker_rel, note=note)


@blueprint.node(stub=stubs.installed)
def install_farrier(
    logger: logging.Logger,
    target_dir: str = "",
    scaffolds: Sequence[str] = (),
    skip_install: bool = False,
) -> FarrierInstall:
    """Run farrier against the genesis repo: install the packs, then render the scaffolds.

    Two calls, in order. `farrier install --repo <target>` reads the `agents.yml` the
    previous step wrote and renders the declared packs into the repo's adapters, producing
    `.agents/agents-context.json` — whose `instructions` map is what `resolve_impl_context`
    reads to decide which skills apply to a service. Without it every skill silently
    resolves to nothing and the implementation stage runs unskilled. Then `farrier scaffold
    <id> --param dir=<root>` per scaffold seeds the conventional folder and its
    `.gitignore`.

    Scaffolds are deliberately thin — a folder and a `.gitignore`, no marker file — so this
    node establishes *convention and hygiene* only. What makes the service real to
    `validate_plan_context` is the marker, and that comes from `init_skeleton`. The two are
    complementary, not redundant.

    A scaffold that fails ends the node with the ids rendered so far, rather than
    continuing: the later scaffolds in a list generally sit inside the earlier ones.
    """
    if not target_dir:
        return FarrierInstall(note="no target_dir was provided")
    target = Path(target_dir)
    if not target.is_dir():
        return FarrierInstall(note=f"target {target} is not a directory")

    notes: list[str] = []
    if not skip_install:
        result = _run(["farrier", "install", "--repo", str(target)], target)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            return FarrierInstall(note=f"farrier install failed: {detail}")
        notes.append("farrier install: adapters + .agents/agents-context.json rendered")

    rendered: list[str] = []
    for entry in (part.strip() for part in scaffolds if part.strip()):
        scaffold_id, _, dir_param = entry.partition(":")
        scaffold_id = scaffold_id.strip()
        args = ["farrier", "scaffold", scaffold_id, "--repo", str(target)]
        if dir_param.strip():
            args += ["--param", f"dir={dir_param.strip()}"]
        result = _run(args, target)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            return FarrierInstall(
                scaffolds_rendered=rendered,
                note="\n".join([*notes, f"scaffold '{scaffold_id}' failed: {detail}"]),
            )
        rendered.append(scaffold_id)
        notes.append(f"scaffold '{scaffold_id}' rendered at '{dir_param.strip() or '<default>'}'")

    logger.info("farrier ok: %d scaffold(s) rendered", len(rendered))
    return FarrierInstall(ok=True, scaffolds_rendered=rendered, note="\n".join(notes))


# ── check it ──────────────────────────────────────────────────────────────────


@blueprint.node(stub=stubs.valid)
def validate_genesis(
    logger: logging.Logger,
    target_dir: str = "",
    service_root: str = "",
    markers: Sequence[str] = (),
) -> GenesisReport:
    """Assert the genesis repo satisfies every precondition the main loop assumes.

    Genesis's postcondition **is** the main loop's precondition, so the service half is
    checked with the shared `contract.service_problems` — the same call
    `validate_plan_context` makes. Without that sharing the two drift apart and the only
    symptom is a confusing planner rejection several stages later.

    What each check earns its place with:

    * **ostler binds to this repo.** The one genuinely silent failure in the whole flow;
      before `git init` a fresh directory matches none of `find_root`'s markers and ostler
      binds to an ancestor without erroring.
    * **`.git` with at least one commit.** An unborn HEAD has nothing for a branch to point
      at, and `branch_author` cuts one almost immediately.
    * **The service marker exists.** What makes the service real to the planner rather than
      just a folder.
    * **`.agents/agents-context.json` has a non-empty `instructions` map.** Empty means
      every skill silently resolves to nothing and implementation runs unskilled — a
      vacuous success, not a crash.
    * **The epics root exists** (`docs/epics/` unless `docRoots:` moved it — ostler resolves
      which). ostler infers its graph profile from this directory, and only the `full`
      profile runs the structural doctor checks the author workflow's coverage gate
      depends on.
    * **The backlog exists**, wherever ostler keeps it. `load_config` hard-fails without it.
    * **A `make lint` target** — a *warning*, not an error: the lint gate degrades to a skip
      without one, so this is a legibility problem rather than a broken repo.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not target_dir:
        return GenesisReport(errors="no target_dir was provided")
    target = Path(target_dir).resolve()
    if not target.is_dir():
        return GenesisReport(errors=f"target {target} is not a directory")

    # ── git ──
    if not (target / ".git").exists():
        errors.append(f"no .git at {target} — ostler will bind to an ancestor repo, and "
                      f"branch-author.py cannot cut a branch")
    elif not _has_commit(target):
        errors.append(f"{target} has an unborn HEAD (no commit) — there is nothing for a "
                      f"branch to point at")

    # ── ostler binds HERE, not to an ancestor ──
    bound = _ostler_root(target)
    if bound is None:
        warnings.append("could not import ostler to verify graph binding — skipped that check")
    elif bound != target:
        errors.append(
            f"ostler binds to {bound}, not {target}. Ids would be allocated from that repo's "
            f"registry and docs written into its tree, silently. This is the failure mode "
            f"git_init exists to prevent — check that node ran before any ostler call."
        )

    # ── the service is real to the planner ──
    if service_root:
        errors.extend(service_problems(target / service_root, markers,
                                       f"{target.name}::{service_root}"))

    # ── skills actually resolve ──
    ctx_path = target / ".agents" / "agents-context.json"
    if not ctx_path.is_file():
        errors.append(f"no {ctx_path.relative_to(target)} — farrier install did not run, so "
                      f"resolve-impl-context.py will resolve every skill to nothing")
    elif not _instructions(ctx_path):
        errors.append(
            f"{ctx_path.relative_to(target)} has an empty 'instructions' map — the "
            f"implementation stage would run with no skills and still report success"
        )

    # ── the docs ground author and coder both stand on ──
    epics_root = okf_path.epics_root_in(target)
    backlog = okf_path.backlog_path_in(target)
    if not epics_root.is_dir():
        errors.append(f"no {epics_root.name}/ at {epics_root} — ostler infers the 'exploration' "
                      "profile without it, and epic-coverage validation then short-circuits "
                      "and asserts nothing")
    if not backlog.is_file():
        errors.append(f"no backlog at {backlog} — the author workflow's load_config hard-fails")

    # ── advisory ──
    if not _has_lint_target(target):
        warnings.append("no `lint` target in a Makefile — the coder workflow's lint gate will "
                        "skip rather than fail, so lint findings would go unreported")

    if errors:
        logger.warning("genesis validation failed with %d error(s)", len(errors))
    else:
        logger.info("genesis validation passed%s",
                    f" with {len(warnings)} warning(s)" if warnings else "")
    return GenesisReport(
        valid=not errors, errors="\n".join(errors), warnings="\n".join(warnings)
    )


def _ostler_root(target: Path) -> Path | None:
    """Where ostler *actually* binds when run from `target` — not where we hope it does."""
    try:
        return Path(find_root(target)).resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def _has_commit(target: Path) -> bool:
    return bool(_head_sha(target))


def _instructions(ctx_path: Path) -> object:
    """The `instructions` map from an agents-context file, or a falsy value."""
    try:
        return (json.loads(ctx_path.read_text(encoding="utf-8")) or {}).get("instructions")
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _has_lint_target(target: Path) -> bool:
    makefile = next((target / name for name in ("Makefile", "makefile")
                     if (target / name).is_file()), None)
    if makefile is None:
        return False
    return any(line.startswith("lint:") or line.startswith("lint ")
               for line in makefile.read_text(encoding="utf-8").splitlines())


__all__ = [
    "genesis_git_init",
    "init_skeleton",
    "install_farrier",
    "resolve_genesis_target",
    "validate_genesis",
    "write_agents_yml",
]
