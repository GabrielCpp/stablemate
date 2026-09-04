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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class SourceRequest(BaseModel):
    """One source repository and surface participating in a story build."""

    model_config = ConfigDict(frozen=True)

    repo: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    surface: str = Field(min_length=1)
    root: str = "."
    base: str = Field(min_length=1)
    head: str = "WORKTREE"

    @field_validator("root")
    @classmethod
    def _relative_root(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip("/") or "."
        if normalized == ".." or normalized.startswith("../"):
            raise ValueError("source roots must be repository-relative")
        return normalized


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
    #: Whether the book already holds markdown. It is the run's one entry decision: a
    #: populated book is *reconciled* to HEAD (straight to the checkpoint, which is what
    #: `recheck_only` used to ask for by hand), an empty one is filled top-down from the
    #: code's entry surfaces.
    book_exists: bool = False
    #: The changed-paths file a `since`-narrowed build filters its inventory through.
    #: Empty on a whole-book reconcile. Zero paths in it is a real answer — sitting on the
    #: base itself, the merge base is HEAD and a clean tree has moved no file — and it is
    #: not the same thing as no narrowing at all.
    diff_scope_path: str = ""
    #: How many paths that scope holds. Zero is a real answer (an empty diff), not
    #: an unset one — `diff_scope_path` is what says whether a scope exists.
    diff_scope_count: int = 0
    #: Why the run cannot proceed, when it cannot.
    prepare_error: str = ""
    #: Stable identity of this build's scope, and the worklist's compatibility stamp.
    scope_id: str = "bulk"

    #: Retired and unread, kept declared for one release: story-mode's parallel prepare is
    #: gone and a run reconciles the book to HEAD instead. Deleting a field on `self.ctx`
    #: kills every in-flight run on reload with a bare pydantic `extra_forbidden`.
    mode: str = "bulk"
    story_id: str = ""
    story_path: str = ""
    story_content: str = ""
    acceptance_criteria: tuple[dict[str, str], ...] = ()
    spec_path: str = ""
    packet: dict[str, Any] = {}
    source_requests: tuple[SourceRequest, ...] = ()
    source_checkouts: dict[str, str] = {}
    source_roots: tuple[str, ...] = ()
    baseline_doctor_errors: tuple[str, ...] = ()
    initial_items: tuple[dict[str, Any], ...] = ()


# ── the drain loop ──────────────────────────────────────────────────────────


class Pick(OkfResult):
    """One item taken off a worklist, plus the snapshot the dashboard labels read."""

    has_item: bool = False
    over_budget: bool = False
    #: The item as stored, so `record` can close exactly what was opened.
    current_item: dict[str, Any] = {}
    item_kind: str = ""
    #: For a repair item (`kind == "fix:<code>"`), the bare doctor code — the one value the
    #: repair prompt dispatches its per-remedy fragment on. Empty for a discovery item.
    item_code: str = ""
    item_target: str = ""
    item_context: str = ""
    pending_count: int = 0
    done_count: int = 0
    done_this_run: int = 0
    #: `"3/12"`, for the label and the activity line.
    progress: str = ""
    #: `"5 surface · 3 layer"`, the kinds composition.
    kinds: str = ""


class Watermarked(OkfResult):
    """What a closed regrounding item retired: the files whose watermark moved to now."""

    advanced: list[str] = Field(default_factory=list)
    watermark_error: str = ""


class Recorded(OkfResult):
    """A worklist write: what it closed, what it opened, and what it gave up re-opening."""

    done_count: int = 0
    pending_count: int = 0
    added: int = 0
    #: Rows that reached `MAX_TARGET_ATTEMPTS` and were blocked instead of re-queued —
    #: `{target, kind, attempts, reason}` each, for the operator gate to name them.
    blocked: list[dict[str, Any]] = []
    #: Every blocked row on the worklist, not only the ones this write blocked. The gate
    #: reports the standing set, so a resumed run does not hand out a shorter list than the
    #: round that first blocked them.
    blocked_count: int = 0


# ── adjudication ────────────────────────────────────────────────────────────


class BlockedRows(OkfResult):
    """The blocked worklist rows no adjudication has yet given a side."""

    rows: list[dict[str, Any]] = []
    count: int = 0


class Evidence(OkfResult):
    """What an adjudication turn reads: the finding, the covering story, the source refs.

    Built mechanically before the turn so the agent judges the *correspondence* — book
    against source, both against the story — rather than the finding text alone. A finding
    of the collision class is born with fault undetermined; this is the other side.
    """

    target: str = ""
    kind: str = ""
    code: str = ""
    #: Every node the finding names — one on a per-node finding, all members on a group.
    nodes: list[str] = []
    #: Doctor's findings for this row, verbatim.
    findings: list[dict[str, Any]] = []
    #: The `code:` targets of those nodes, as written in the book.
    code_refs: list[str] = []
    #: The `story-for-node` row for the latest story with a trailer — `None` when no
    #: reachable commit over the node's code carries one, which reads as "the code is
    #: the intent".
    story: dict[str, Any] | None = None
    #: That story's story.md, verbatim, so the acceptance criteria are in the turn.
    story_text: str = ""
    #: Whether the trailer found names a story the book resolves.
    story_resolved: bool = False
    #: What the join could not do — a malformed ref, a checkout it was not given.
    warnings: list[str] = []
    #: What the last repair turn said when it gave the row back.
    blocked_reason: str = ""


class Adjudication(OkfResult):
    """The turn's verdict: which side of the correspondence is wrong, and the why-chain."""

    verdict: str = Field(
        default="", description="One of book, code, or story; empty matches no branch."
    )
    chain: str = Field(
        default="",
        description="The numbered why-chain ending at the property that names the side.",
    )
    seed_summary: str = Field(
        default="",
        description="For code only, one line naming the source defect; empty otherwise.",
    )


class Applied(OkfResult):
    """What routing a verdict wrote: a re-queued row, a seed and its bullets, or a conflict."""

    verdict: str = ""
    target: str = ""
    #: The seed id a `code` verdict filed, and the epic it landed in.
    seed: str = ""
    epic: str = ""
    #: Nodes that received a `known-defect:` bullet.
    marked: list[str] = []
    #: The story a `story` verdict wrote its conflict on.
    story: str = ""
    #: Whether the row went back to the drain with a fresh allowance.
    requeued: bool = False


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
    coverage_path: str = ""
    coverage_summary: str = ""
    coverage_error: str = ""
    #: `fix:stale-citation` items — one per node whose cited symbol drifted or moved under it.
    #: Seeded straight into the worklist rather than adjudicated: an uncovered unit is a
    #: judgement call (is this a unit at all?), a drifted one is not — the code moved and the
    #: bullet has to follow it.
    regrounding: list[dict[str, Any]] = Field(default_factory=list)
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
    #: Why, when it is not `documented`. Recorded on the worklist row and printed by the
    #: operator gate that a repeatedly-unrepairable target eventually blocks on, so the
    #: person reading it sees the turn's own sentence rather than only a code and a count.
    note: str = ""


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
    "Adjudication",
    "AppBoot",
    "Applied",
    "BlockedRows",
    "BrowserBoot",
    "Checkpoint",
    "Coverage",
    "Discovery",
    "Evidence",
    "Investigation",
    "OkfResult",
    "Pick",
    "Prepared",
    "Recheck",
    "Recorded",
    "SourceInventory",
    "SourceRequest",
    "TornDown",
    "WalkSeed",
    "WalkTurn",
    "WebApp",
]
