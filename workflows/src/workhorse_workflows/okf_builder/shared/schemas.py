"""The models the okf-builder seams need: agent replies and node returns.

`self.agent(prompt, returns=T)` validates a model out of whatever the turn produced and
reads `T`'s fields to build the output keys it asks for; a node returns a plain typed
value. Nothing here crosses a state boundary — a transition carries keyword arguments
bound against the next state's own signature, so a state's parameters are its schema.

Every model derives from `OkfResult`, whose two rules come from how workhorse *fails*
rather than how it succeeds:

* **Every field has a default.** After the resilience ladder's last rung a node that
  could not be answered emits its declared output keys as `null` and the run advances
  (`workhorse/docs/GUARDRAILS.md`, "Default to the next node"). A required field would
  turn that soft failure into a hard one.
* **Unknown keys are ignored, nulls are dropped**, so a missing answer falls back to the
  field's own default instead of raising.

Two divergences from the YAML's output keys, both mechanical and both applied throughout:

* the `"yes"`/`"no"` strings a branch matched on are **booleans**, and the counters the
  YAML carried as `"0"` are **ints**. The YAML had no types, so every gate spelled its
  own coercion and `guard_rounds` compared `rescan_round` to the *string* `"6"`;
* `current_item`, `discovered` and `fixup_items` were JSON **strings** because a template
  argument is text — hence `| tojson` at one callsite, a bare pass-through at another,
  and `record.py`'s `ast.literal_eval` fallback for when the round trip mangled one.
  They are typed containers here and the round trip is gone.

`torn_down` stays a string: it is tri-state (`yes`/`no`/`skipped`), and `skipped` — a
pgid that was never a number — is the value an operator most needs to see.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class OkfResult(BaseModel):
    """Base for every agent reply and node return in the okf-builder workflow."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


# ── the run's setting: what `prepare` resolved ──────────────────────────────


class Prepared(OkfResult):
    """Where the book, the source and the worklist are, and whether ostler can read them.

    `setup()` returns this, so it is `self.ctx` for the whole run: the one thing every
    state reads and no state writes.
    """

    #: The drain loop's memory, absolute.
    worklist_path: str = ""
    #: The book being built, absolute.
    features_root: str = ""
    #: The docs repo root, absolute.
    repo_root: str = ""
    #: The subtree the coverage inventory walks, absolute.
    source_root: str = ""
    #: Echoed back so a state reads one object rather than two.
    service: str = ""
    #: Comma-separated, relative to `source_root`.
    source_excludes: str = ""
    #: Whether ostler can load a *graph* at `repo_root` — not whether it imports.
    ostler_ok: bool = False
    #: Items already `done` when this run started: `max_items` bounds the run, not the file.
    done_baseline: int = 0
    #: Whether a stale worklist was discarded rather than resumed.
    worklist_reset: bool = False
    #: Why the run cannot proceed, when it cannot.
    prepare_error: str = ""


# ── the drain loop ──────────────────────────────────────────────────────────


class Pick(OkfResult):
    """One item taken off a worklist, plus the snapshot the dashboard labels read."""

    has_item: bool = False
    over_budget: bool = False
    #: The item as stored, so `record` can close exactly what was opened.
    current_item: dict[str, Any] = {}
    item_kind: str = ""
    item_target: str = ""
    item_context: str = ""
    pending_count: int = 0
    done_count: int = 0
    done_this_run: int = 0
    #: `"3/12"`, for the label and the activity line.
    progress: str = ""
    #: `"5 surface · 3 layer"`, the kinds composition.
    kinds: str = ""


class Recorded(OkfResult):
    """A worklist write: what it closed and what it opened."""

    done_count: int = 0
    pending_count: int = 0
    added: int = 0


# ── convergence ─────────────────────────────────────────────────────────────


class Checkpoint(OkfResult):
    """The mechanical gate's verdict, and the repair work it queues."""

    checkpoint_clean: bool = False
    #: The tail of `ostler doctor`'s findings, for the log.
    doctor_output: str = ""
    #: The checkpoint round this pass was, already incremented.
    round: int = 0
    #: One repair item per offending node, ready to seed onto the worklist.
    fixup_items: list[dict[str, Any]] = []
    #: Of those, how many need a value derived from source rather than a doc edit.
    backfill_count: int = 0
    #: Fingerprint of the finding set, to detect an unchanging re-flag.
    fixup_signature: str = ""
    #: Consecutive rounds the finding set recurred unchanged.
    stall_rounds: int = 0


class Waived(OkfResult):
    """What `auto_waive` accepted, and whether anything was left that it could not."""

    has_unwaivable: bool = False
    waived_count: int = 0
    note: str = ""


# ── coverage ────────────────────────────────────────────────────────────────


class SourceInventory(OkfResult):
    """The source side of the coverage diff, materialized mechanically."""

    source_inventory_path: str = ""
    source_unit_count: int = 0
    operational_unit_count: int = 0
    inventory_errors: str = ""


class Coverage(OkfResult):
    """The computed verdict: is the book's citation set a cover of the inventory."""

    coverage_complete: bool = False
    missing_count: int = 0
    missing_path: str = ""
    #: The other computed gap: nodes minting obligations that declare no `verify:` check.
    #: Separate from `coverage_complete`, which stays what its name says — the join of the
    #: book's `code:` citations against the source inventory. The workflow requires both.
    undeclared_count: int = 0
    undeclared_path: str = ""
    coverage_path: str = ""
    coverage_summary: str = ""
    coverage_error: str = ""
    #: The re-scan counter, incremented on *every* exit path — see `nodes/coverage.py`.
    rescan_round: int = 0


# ── agent replies ───────────────────────────────────────────────────────────


class Discovery(OkfResult):
    """What a turn found that is not yet on the worklist.

    Each entry is `{kind, target, context}`, and may carry `requeue: true` to reopen an
    item already marked done.
    """

    discovered: list[dict[str, Any]] = []


class Investigation(Discovery):
    """One item documented — and whether it actually was."""

    #: `documented` | `skipped` | `partial`; the default matches no branch.
    doc_status: str = ""


class Recheck(Discovery):
    """The coverage adjudication: which missing rows are real work."""

    needs_journeys: bool = False


class WalkTurn(Discovery):
    """One journey or screen walked against the running app."""

    #: `confirmed` | `healed` | `skipped`.
    walk_status: str = ""


# ── the walk's runtime ──────────────────────────────────────────────────────


class WebApp(OkfResult):
    """Whether this service has a web surface, and the recipe for bringing it up.

    Every field is read out of the book — the launch contract is documentation, not
    configuration — which is what lets the walk run standalone.
    """

    is_webapp: bool = False
    repo_root: str = ""
    source_root: str = ""
    features_root: str = ""
    entry_url: str = ""
    launch_cmd: str = ""
    health_path: str = "/"
    app_cwd: str = ""
    app_identity: str = ""
    stop_cmd: str = ""
    boot_timeout: str = ""
    wt_worklist_path: str = ""
    screenshots_dir: str = ""
    #: The shared browser's CDP endpoint — the agent's playwright MCP and `ostler vet`
    #: both attach to this one Chromium.
    cdp_url: str = ""


class AppBoot(OkfResult):
    """The app under walk, once it answers its health path."""

    boot_ok: bool = False
    #: Resolved/echoed, because a fallback port can change it.
    entry_url: str = ""
    app_pid: str = ""
    #: The process *group*, which is what teardown reaps.
    app_pgid: str = ""


class BrowserBoot(OkfResult):
    """The shared CDP browser, booted here so it outlives an agent turn."""

    browser_ok: bool = False
    cdp_url: str = ""
    browser_pid: str = ""
    #: Empty when an already-answering endpoint was adopted: we did not spawn it, so we
    #: do not reap it.
    browser_pgid: str = ""


class TornDown(OkfResult):
    """`yes`, `no`, or `skipped` — tri-state, so it stays a string."""

    torn_down: str = "no"


class WalkSeed(OkfResult):
    """The walk worklist, seeded from the book's screens and flows."""

    done_count: int = 0
    pending_count: int = 0
    added: int = 0
    #: Screens carrying no `vet:` evidence — the walk's delta.
    unconfirmed_count: int = 0
    screen_count: int = 0


__all__ = [
    "AppBoot",
    "BrowserBoot",
    "Checkpoint",
    "Coverage",
    "Discovery",
    "Investigation",
    "OkfResult",
    "Pick",
    "Prepared",
    "Recheck",
    "Recorded",
    "SourceInventory",
    "TornDown",
    "WalkSeed",
    "WalkTurn",
    "Waived",
    "WebApp",
]
