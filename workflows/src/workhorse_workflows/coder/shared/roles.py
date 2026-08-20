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
3. nothing, in which case the turn renders the **envelope alone**.

The envelope is the file the workflow ships and keeps: `coder/prompts/<role>.md`. It is
the *contract* — the inputs provided, the exit condition, the result schema the state
machine parses back — and a repo does not get to edit it, because the state machine
would then be parsing a document it did not write. The body it wraps is the *procedure*,
which is exactly the part that knows this repo's stack, and so is exactly the part a repo
must be able to replace. `render` mounts the resolved body's directory under its own
`body/` namespace and the envelope pulls it in with `{% include body_template %}` — a
namespace rather than a search path because the body is named for the role, which is what
the envelope is named, and a bare filename would resolve back to the envelope.

**A role is named for the envelope's own stem**, not renamed to something tidier. Node
ids in a run directory, in the resume path and in telemetry derive from that stem, so a
rename here would break resumes and split every metric across two names for no gain the
plan asks for. It also means `fix`'s and the top-level workflow's reuse of dev's
`plan-story`/`implement-plan` bodies stays a single file, as it already is.

The mechanics prompts are not roles and are absent from the registry below:
`resolve-operator.md`, `settle-worktree.md`, `fix-merge.md`. They are the state machine
talking to itself — an operator gate's resolution, git surgery on a worktree — and a repo
overriding them would be overriding the workflow, not describing itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from workhorse.pyflow import WorkflowFailed
from workhorse.templates import BODY_PREFIX
from workhorse_workflows.kit import find_repo_root

#: Where a library layer keeps the coder bodies, relative to the layer root. Beside
#: `library/prompts/stablemate/` — the bodies of the interactive commands — because they
#: are the same kind of thing: prose a repo owns, versioned with the skills it ships.
LIBRARY_SUBDIR = Path("library") / "prompts" / "coder"

#: Every overridable turn in the coder workflow, by role. The value is prose for a human
#: reading an error message or an `agents.yml` — nothing resolves through it.
ROLES: dict[str, str] = {
    # dev
    "plan-story": "plan a story into per-service implementation plans",
    "refine-plan": "repair a plan a gate or a reviewer rejected",
    "implement-plan": "implement one service layer of the plan",
    "dev-fix": "repair whatever gate went red, one lap",
    # review
    "code-review": "the mechanical review pass over the diff",
    "code-reuse": "did the implementation rebuild something that exists?",
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
    "qa-fix-item": "apply one QA finding",
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
    "dream-reflect": "reflect on the run and propose an improvement",
}

#: Roles whose default body has **left this package** for the base library. For these an
#: unresolved body is a hard, named error rather than a silent envelope-only render: the
#: envelope on its own is a contract with no procedure attached, and a turn that shipped
#: it would look like a working prompt and behave like an empty one. Roles absent from
#: this set still carry their body in-tree, so resolving nothing is the normal state and
#: means "no override" — that is what makes the move a file at a time instead of a flag
#: day.
LIBRARY_BODIES: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Turn:
    """What a role resolves to: the envelope to render, and the args that find its body.

    `args` is empty when no body was resolved, so a callsite reads the same either way —
    `args=turn.args | {…}` — and a role whose body has not moved yet renders exactly the
    document it rendered before this module existed.
    """

    prompt: str
    args: dict[str, Any]


def turn(role: str, repo_dir: str | Path = "", library_dirs: tuple[str, ...] = ()) -> Turn:
    """Resolve `role` to the envelope and the body arguments for one agent turn.

    Raises `WorkflowFailed` for an unregistered role — that is a typo in the flow, caught
    on the transition rather than as a puzzling render — and for a `LIBRARY_BODIES` role
    whose body no layer supplies.
    """
    if role not in ROLES:
        raise WorkflowFailed(
            f"unknown prompt role {role!r}; the coder workflow's roles are: "
            + ", ".join(sorted(ROLES))
        )
    body = _body(role, repo_dir, library_dirs)
    if body is None and role in LIBRARY_BODIES:
        looked = [str(Path(d) / LIBRARY_SUBDIR / f"{role}.md") for d in library_dirs]
        raise WorkflowFailed(
            f"no prompt body for role {role!r} ({ROLES[role]}). Its text lives in the "
            "stablemate base library, and this run resolved no library layer that has "
            "it. Looked in: " + (", ".join(looked) or "nowhere — `library_dirs` is empty")
            + ". Install the library (`farrier install`) or point the run at a checkout "
            "with `--param library_dirs=[…]`."
        )
    prompt = f"prompts/{role}.md"
    if body is None:
        return Turn(prompt, {})
    return Turn(
        prompt,
        {"_body_dir": str(body.parent), "body_template": f"{BODY_PREFIX}/{body.name}"},
    )


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


__all__ = ["LIBRARY_BODIES", "LIBRARY_SUBDIR", "ROLES", "Turn", "turn"]
