"""Genesis's models: what the target already is, what each step made of it, and the verdict.

Ported from the `genesis` flow's six script nodes. Genesis takes a directory that may be
empty, may hold a half-built project, or may already be a configured repo, and leaves
behind something the author and coder workflows can both stand on. It is pure bootstrapping
— every step here is deterministic tooling, with no agent turn anywhere in the flow.

One shape to note: every `*_ok` / `*_written` / `*_valid` output was a `"yes"`/`"no"`
**string** in the YAML, because a `branch` node compares rendered text. They are `bool`
here. Nothing on disk carried the strings — they existed only to be compared by the engine.
"""
from __future__ import annotations

from typing import Literal

from workhorse_workflows.coder.shared.schemas._base import CoderResult


class TargetClassification(CoderResult):
    """`resolve-genesis-target.py` — what is already at the target, before anything runs.

    `target_state` is `existing` (an `agents.yml` is there: refresh config only),
    `partial` (content but no `agents.yml`: full genesis, removing nothing) or `absent`
    (missing or empty). `service_state` is `existing` when the declared marker file is
    already in place, `absent` otherwise; with no marker declared it reads `absent`,
    which sends the run through the skeleton step.

    Both defaults are the arm that does the most work: a node the resilience ladder could
    not answer classifies as `absent`, which routes the run through full genesis rather
    than through the config-only refresh that would skip every step that makes a repo.

    `markers` is the marker list resolved once here — the `markers` param when it is set,
    otherwise the singular `marker` — so `config` and `verify` read one answer back
    instead of each re-deciding the fallback for itself.
    """

    ok: bool = False
    target_dir: str = ""
    target_state: Literal["absent", "partial", "existing"] = "absent"
    service_state: Literal["existing", "absent"] = "absent"
    service: str = ""
    markers: list[str] = []
    note: str = ""


class GitInit(CoderResult):
    """`genesis-git-init.py` — a repo with at least one commit, made or found.

    The commit matters as much as the `.git`: an unborn HEAD has nothing for a branch to
    point at, and `branch_author` cuts one almost immediately. An existing repo whose HEAD
    *is* unborn falls through to the commit step rather than being reported ready.
    """

    ready: bool = False
    note: str = ""
    initial_commit: str = ""


class AgentsYml(CoderResult):
    """`write-genesis-agents-yml.py` — the config merged in, or found already correct.

    `written` is False both when the merge failed and when it changed nothing, which is
    the common re-run; `note` is what tells the two apart.
    """

    written: bool = False
    path: str = ""
    note: str = ""


class Skeleton(CoderResult):
    """`init-genesis-skeleton.py` — the stack's own `init` command, and its proof.

    `ok` is asserted on the **marker file**, not on the command's exit code: a native init
    exiting 0 is not proof it made a service, and several write into a subdirectory of the
    one they were run in.
    """

    ok: bool = False
    note: str = ""
    marker_path: str = ""


class FarrierInstall(CoderResult):
    """`install-genesis-farrier.py` — adapters rendered, and the scaffolds that took.

    `scaffolds_rendered` is a real list here; the YAML carried it as a comma-joined string
    because a workflow var is a string.
    """

    ok: bool = False
    note: str = ""
    scaffolds_rendered: list[str] = []


class GenesisReport(CoderResult):
    """`validate-genesis.py` — every precondition the main loop assumes, checked.

    `errors` and `warnings` stay newline-joined strings rather than lists: both go straight
    into the `WorkflowFailed` message when the target is invalid, and splitting them only to
    rejoin them there would be a round trip with no reader in between.
    """

    valid: bool = False
    errors: str = ""
    warnings: str = ""


__all__ = [
    "AgentsYml",
    "FarrierInstall",
    "GenesisReport",
    "GitInit",
    "Skeleton",
    "TargetClassification",
]
