"""Which prompt body a turn renders, and who owns it.

A node is a conversation, not a file. What the state machine names is a **role** — the
job the turn does, `implement-plan`, `dev-fix`, `code-review` — and this module answers
the question the flow deliberately does not: *whose text says how that job is done here?*

Three answers, highest precedence first:

1. the **repo**, in its `agents.yml`, under a `prompts:` block mapping a role to a
   repo-relative file — the same block shape as the `services:` one beside it;
2. a **library layer** the machine has installed, at `library/prompts/coder/<role>.md`
   in each entry of `Workflow.library_dirs` (the overlay first, then the base) — the
   layers farrier already renders across, in farrier's order;
3. nothing, in which case the turn renders **the workflow's own default**.

That third answer is the normal one, and it is why this resolver is an override mechanism
rather than a relocation. **The workflow ships standalone**: `workhorse-workflows` is
installed on its own and every prompt it needs is inside it, at
`coder/<flow>/prompts/<role>.md`.
A machine that never ran farrier, has no `~/.cache/stablemate` and no overlay still runs
every story end to end. The base library's `library/prompts/` are the *user's* prompts —
what farrier installs into a repo for a person to invoke — and a workflow that reached
into them for its own defaults would have made an optional install load-bearing.

What a layer may do is *replace* a body. The envelope — `coder/<flow>/prompts/<role>.md` —
is the *contract*: the inputs provided, the exit condition, the result schema the state machine
parses back. A repo does not get to edit it, because the state machine would then be
parsing a document it did not write. The body it wraps is the *procedure*, which is
exactly the part that knows this repo's stack, and so is exactly the part a repo must be
able to replace. `render` mounts the resolved body's directory under its own `body/`
namespace and the envelope pulls it in with `{% include body_template %}` — a namespace
rather than a search path because the body is named for the role, which is what the
envelope is named, and a bare filename would resolve back to the envelope.

**A role is named for the envelope's own stem**, not renamed to something tidier. Node
ids in a run directory, in the resume path and in telemetry derive from that stem, so a
rename here would break resumes and split every metric across two names for no gain the
plan asks for.

**A role is one key, not one file.** Each flow owns the envelopes it renders, in its own
`prompts/`, so `apply-qa-fixes` exists twice over — `qa/` and `fix/` each hold a copy,
free to diverge, and nothing checks that they agree. `turn` takes the calling flow for
exactly that reason. What stays single is everything on the *override* side: `ROLES`,
a repo's `agents.yml` `prompts:` block and `LIBRARY_SUBDIR` are keyed by role alone, so a
repo replaces a body once and every flow's copy of that envelope picks it up.

The mechanics prompts are not roles and are absent from the registry below:
`resolve-operator.md`, `settle-worktree.md`, `fix-merge.md` — named at their callsites by
path, since there is no body for a layer to swap. They are the state machine
talking to itself — an operator gate's resolution, git surgery on a worktree — and a repo
overriding them would be overriding the workflow, not describing itself.

Which is also why the per-flow copy a role needs buys them nothing. `resolve-operator.md`
is **one file**, `shared/prompts/resolve-operator.md`, rendered by every lane that gates:
dev, review, qa and docs each pass the stage in `block_kind` and are otherwise asking the
same question of the same record. Four copies free to diverge would only ever diverge by
being forgotten — an edit made where the block was noticed and nowhere else.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from workhorse.pyflow import WorkflowFailed
from workhorse.templates import BODY_PREFIX
from workhorse_workflows.kit import find_repo_root

#: The package every coder flow sits one level under. `flow_dir` measures against it.
PACKAGE = "workhorse_workflows.coder"

#: Where a library layer may keep a *replacement* coder body, relative to the layer root.
#: Nothing is expected to be here — the defaults ship with the workflow — so an empty or
#: absent directory is the ordinary case and means "this layer overrides nothing".
LIBRARY_SUBDIR = Path("library") / "prompts" / "coder"

#: Every overridable turn in the coder workflow, by role. The value is prose for a human
#: reading an error message or an `agents.yml` — nothing resolves through it.
ROLES: dict[str, str] = {
    # dev
    "plan-story": "plan a story into per-service implementation plans",
    "repair-plan-paths": "correct the service paths a plan validator rejected",
    "replan-with-answer": "re-plan a story around an answered operator block",
    "implement-plan": "implement one service layer of the plan",
    "dev-fix": "repair whatever gate went red, one lap",
    # review
    "code-review": "the mechanical review pass over the diff",
    "review-implementation": "the binding verdict on the implementation",
    "apply-review": "apply the review's findings",
    # qa
    "plan-qa": "write the story's QA plan",
    "qa-story": "execute the QA plan against the running system",
    "audit-qa": "audit the QA evidence for coverage and honesty",
    "triage-qa": "route QA findings to the lane that can fix them",
    "setup-fix": "repair the environment QA could not bring up",
    "fix-regression": "repair a regression QA surfaced outside the story",
    "apply-qa-fixes": "apply a batch of QA findings",
    "fix-qa-scenario": "fix one failing QA scenario, with its own dry-run proof",
    "qa-fix-item": "apply one QA finding",
    # fix
    "fix-item": "plan and implement one drained backlog item, in one turn",
    "repair-qa-plan": "repair a QA plan that did not validate",
    "repair-qa-context": "repair the obligation packet QA runs against",
    "report-qa-dev": "report a failing QA run back to the dev lane",
    "report-qa-dev-pass": "report a passing QA run back to the dev lane",
    # docs
    "document-story": "fold the story into the as-built book",
    "review-story-documentation": "an independent read of what was written",
    "repair-documentation": "repair documentation a review rejected",
    # the rest
    "fix-ci": "repair a red CI run",
    "replan-epic": "replan an epic whose stories no longer fit",
}

@dataclass(frozen=True)
class Turn:
    """What a role resolves to: the envelope to render, and the args that find its body.

    `args` is empty when no body was resolved, so a callsite reads the same either way —
    `args=turn.args | {…}` — and an un-overridden role renders exactly the document it
    rendered before this module existed.
    """

    prompt: str
    args: dict[str, Any]


def turn(flow: Any, role: str) -> Turn:
    """Resolve `role` to the envelope and the body arguments for one agent turn.

    Takes the calling flow, because a role no longer names one file: each flow owns its
    own copy of every envelope it renders, and which copy this is depends on who asked.
    `flow.repo_dir` and `flow.library_dirs` come along for free, which is what the two
    arguments this replaced were reading off the same object at every callsite.

    Raises `WorkflowFailed` for an unregistered role — that is a typo in the flow, caught
    on the transition rather than as a puzzling render. Resolving *no* body is not an
    error and never can be: it is the ordinary case, and it renders the default the
    workflow ships.
    """
    if role not in ROLES:
        raise WorkflowFailed(
            f"unknown prompt role {role!r}; the coder workflow's roles are: "
            + ", ".join(sorted(ROLES))
        )
    body = _body(role, flow.repo_dir, flow.library_dirs)
    prompt = f"{flow_dir(flow)}/prompts/{role}.md"
    if body is None:
        return Turn(prompt, {})
    return Turn(
        prompt,
        {"_body_dir": str(body.parent), "body_template": f"{BODY_PREFIX}/{body.name}"},
    )


def flow_dir(flow: Any) -> str:
    """The flow package's own directory name, as a prompt path is prefixed with it.

    Read off the defining module rather than declared on the class, so a flow that moves
    directory carries its prompts with it and nothing has to be kept in step by hand.
    Everything under `coder/` is one package deep — `…coder.dev.flow` is `dev`, and
    `…coder.main.flow` is `main` for the same reason the main graph is a flow package.
    """
    module = type(flow).__module__
    prefix = f"{PACKAGE}."
    if not module.startswith(prefix):
        raise WorkflowFailed(
            f"{type(flow).__name__} is defined in {module!r}, outside {PACKAGE!r}, so it "
            "has no flow directory to resolve its prompts against. A coder flow lives in "
            "its own package under `coder/`, beside the `prompts/` it renders."
        )
    return module[len(prefix) :].split(".", 1)[0]


def _body(role: str, repo_dir: str | Path, library_dirs: tuple[str, ...]) -> Path | None:
    """The first body file that exists, repo before overlay before base."""
    override = _repo_prompts(repo_dir).get(role)
    if override:
        candidate = Path(override)
        if not candidate.is_absolute():
            candidate = find_repo_root(repo_dir) / candidate
        if candidate.is_file():
            return candidate
    for layer in library_dirs:
        candidate = Path(layer) / LIBRARY_SUBDIR / f"{role}.md"
        if candidate.is_file():
            return candidate
    return None


def _repo_prompts(repo_dir: str | Path) -> dict[str, str]:
    """The repo's `prompts:` block, read the way `dev._services_config` reads `services:`.

    Same tolerance for the same reason: `agents.yml` is a file humans hand-edit, and a
    missing, empty or malformed one means "this repo overrides nothing", not "stop the
    run". A repo that meant to override and mistyped the file gets stablemate's default
    text, which is the failure mode that leaves a story implemented rather than parked.
    """
    config = find_repo_root(repo_dir) / "agents.yml"
    if not config.is_file():
        return {}
    try:
        loaded = yaml.safe_load(config.read_text()) or {}
    except yaml.YAMLError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    block = loaded.get("prompts")
    if not isinstance(block, dict):
        workflow = loaded.get("workflow")
        block = workflow.get("prompts") if isinstance(workflow, dict) else None
    if not isinstance(block, dict):
        return {}
    return {str(k): str(v) for k, v in block.items() if isinstance(v, str)}


__all__ = ["LIBRARY_SUBDIR", "PACKAGE", "ROLES", "Turn", "flow_dir", "turn"]
