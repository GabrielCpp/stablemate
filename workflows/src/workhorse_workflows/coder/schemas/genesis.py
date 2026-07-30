"""Genesis's models: what the target already is, what each step made of it, and the verdict.

Ported from the `genesis` flow's six script nodes and its two agent turns. Genesis takes a
directory that may be empty, may hold a half-built project, or may already be a configured
repo, and leaves behind something the author and coder workflows can both stand on.

Two shapes to note:

* every `*_ok` / `*_written` / `*_valid` output was a `"yes"`/`"no"` **string** in the
  YAML, because a `branch` node compares rendered text. They are `bool` here. Nothing on
  disk carried the strings — they existed only to be compared by the engine;
* `notes` are kept verbatim from the scripts, including their remediation sentences. They
  are the only thing an operator reading a failed genesis run has, and several of them
  name the exact `--params` to re-run with.

The two agent replies default `status` to `"blocked"` rather than `""`, because the YAML
declared `default: {status: blocked}` on both nodes. Nothing branches on either, so the
default is fidelity, not control flow.
"""
from __future__ import annotations

from workhorse_workflows.coder.schemas._base import CoderResult


class TargetClassification(CoderResult):
    """`resolve-genesis-target.py` — what is already at the target, before anything runs.

    `target_state` is `existing` (an `agents.yml` is there: refresh config only),
    `partial` (content but no `agents.yml`: full genesis, removing nothing) or `absent`
    (missing or empty). `service_state` is `existing` when the declared marker file is
    already in place, `absent` otherwise; with no marker declared it reads `absent`,
    which sends the run through the skeleton step.
    """

    ok: bool = False
    target_dir: str = ""
    target_state: str = "absent"
    service_state: str = "absent"
    service: str = ""
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

    `errors` and `warnings` stay newline-joined strings rather than lists: both are handed
    straight to the fixer agent as prose, and splitting them only to rejoin them at the
    prompt would be a round trip with no reader in between.
    """

    valid: bool = False
    errors: str = ""
    warnings: str = ""


class ConventionsResult(CoderResult):
    """`prompts/apply-genesis-conventions.md` — `applied` or `blocked`."""

    status: str = "blocked"
    notes: str = ""


class FixResult(CoderResult):
    """`prompts/fix-genesis.md` — `fixed` or `blocked`.

    Not branched on: `validate_genesis` runs again after it and decides, which is the only
    honest reading of whether a repair worked.
    """

    status: str = "blocked"
    notes: str = ""


__all__ = [
    "AgentsYml",
    "ConventionsResult",
    "FarrierInstall",
    "FixResult",
    "GenesisReport",
    "GitInit",
    "Skeleton",
    "TargetClassification",
]
