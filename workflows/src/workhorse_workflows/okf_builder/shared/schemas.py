"""The models the okf-builder seams need: agent replies and node returns."""
from __future__ import annotations

from typing import Any, Literal

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
    """Where the book, the source and the worklist are, and whether ostler can read them."""

    worklist_path: str = ""
    features_root: str = ""
    repo_root: str = ""
    source_root: str = ""
    service: str = ""
    source_excludes: str = ""
    ostler_ok: bool = False
    done_baseline: int = 0
    worklist_reset: bool = False
    book_exists: bool = False
    prepare_error: str = ""
    scope_id: str = "bulk"

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
    diff_scope_path: str = ""
    diff_scope_count: int = 0


class Baseline(OkfResult):
    """Where the book was copied as a repair turn found it."""

    path: str = ""


class Committed(OkfResult):
    """Whether the completed book produced a git commit."""

    committed: bool = False


class Stamped(OkfResult):
    """The `@digest` targets a turn's stamp step actually wrote, and what it withheld."""

    stamped: int = 0
    skipped_nodes: list[str] = Field(default_factory=list)




class Pick(OkfResult):
    """One item taken off a worklist, plus the snapshot the dashboard labels read."""

    has_item: bool = False
    over_budget: bool = False
    current_item: dict[str, Any] = {}
    batch: list[dict[str, Any]] = []
    item_kind: str = ""
    item_code: str = ""
    item_codes: list[str] = []
    item_target: str = ""
    item_context: str = ""
    pending_count: int = 0
    done_count: int = 0
    done_this_run: int = 0
    progress: str = ""
    kinds: str = ""


class Settled(OkfResult):
    """A mid-drain settle: whether doctor was consulted, and what that closed."""

    ran: bool = False
    settled: int = 0
    reopened: int = 0
    standing: int = 0
    pending_count: int = 0
    at_done: int = 0
    error: str = ""


class Recorded(OkfResult):
    """A worklist write: what it closed, what it opened, and what it gave up re-opening."""

    done_count: int = 0
    pending_count: int = 0
    added: int = 0
    settled: int = 0
    blocked: list[dict[str, Any]] = []
    blocked_count: int = 0




class BlockedRows(OkfResult):
    """The blocked worklist rows no adjudication has yet given a side."""

    rows: list[dict[str, Any]] = []
    count: int = 0


class Evidence(OkfResult):
    """What an adjudication turn reads: the finding, the covering story, the source refs."""

    target: str = ""
    kind: str = ""
    code: str = ""
    nodes: list[str] = []
    findings: list[dict[str, Any]] = []
    code_refs: list[str] = []
    story: dict[str, Any] | None = None
    story_text: str = ""
    story_resolved: bool = False
    warnings: list[str] = []
    blocked_reason: str = ""


class Adjudication(OkfResult):
    """The turn's verdict: which side of the correspondence is wrong, and the why-chain."""

    verdict: Literal["book", "code", "story"]
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
    seed: str = ""
    epic: str = ""
    marked: list[str] = []
    story: str = ""
    requeued: bool = False




class Checkpoint(OkfResult):
    """The mechanical gate's verdict, and the repair work it queues."""

    checkpoint_clean: bool = False
    doctor_output: str = ""
    round: int = 0
    fixup_items: list[dict[str, Any]] = []
    backfill_count: int = 0
    fixup_signature: str = ""
    stall_rounds: int = 0




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
    regrounding: list[dict[str, Any]] = Field(default_factory=list)
    rescan_round: int = 0




class Discovery(OkfResult):
    """What a turn found that is not yet on the worklist."""

    discovered: list[dict[str, Any]] = []


class Investigation(Discovery):
    """One item documented — and whether it actually was."""

    doc_status: str = ""
    note: str = ""
    commit_message: str = ""


class Recheck(Discovery):
    """The coverage adjudication: which missing rows are real work."""

    needs_journeys: bool = False


__all__ = [
    "Adjudication",
    "Applied",
    "BlockedRows",
    "Checkpoint",
    "Committed",
    "Coverage",
    "Discovery",
    "Evidence",
    "Investigation",
    "OkfResult",
    "Pick",
    "Prepared",
    "Recheck",
    "Recorded",
    "Settled",
    "SourceInventory",
    "SourceRequest",
    "Stamped",
]
