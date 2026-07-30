"""The models the author workflow's seams need, grouped the way `nodes/` is.

`self.agent(prompt, returns=T)` validates a model out of whatever the turn produced and
reads `T`'s fields to build the output keys it asks for; a node returns a plain typed
value. Nothing here crosses a state boundary — a transition carries keyword arguments
bound against the next state's own signature, so a state's parameters are its schema.

The submodules are the subjects:

* `main` — the author's own graph (`nodes/config.py` through `nodes/artifacts.py`)
* `survey` — the surveyor sub-flow (`nodes/survey/`)
* `parity` — what the parity surveyor adds on top of it (`nodes/survey/parity.py`)
"""
from __future__ import annotations

from workhorse_workflows.author.schemas._base import AuthorResult
from workhorse_workflows.author.schemas.main import (
    AuditResult,
    Branches,
    Committed,
    Config,
    CoverageReview,
    DecomposeResult,
    Defects,
    EpicChoice,
    EpicReview,
    Feedback,
    Ledger,
    MockupResult,
    Pruned,
    PullRequest,
    RunContext,
    SeededStory,
    StoryChoice,
    StorySplit,
    VerifyReport,
    WriteEpicResult,
    WriteStoryResult,
)
from workhorse_workflows.author.schemas.parity import ParityConfig
from workhorse_workflows.author.schemas.survey import (
    EmitResult,
    Expansion,
    InventoryCheck,
    MarkResult,
    OperatorResolution,
    PartitionCheck,
    PartitionProposal,
    PlanResult,
    RecordCheck,
    RecordFix,
    SplitResult,
    SurveyConfig,
    UnitAssessment,
    UnitPick,
    VerifyResult,
)

__all__ = [
    "AuditResult",
    "AuthorResult",
    "Branches",
    "Committed",
    "Config",
    "CoverageReview",
    "DecomposeResult",
    "Defects",
    "EmitResult",
    "EpicChoice",
    "EpicReview",
    "Expansion",
    "Feedback",
    "InventoryCheck",
    "Ledger",
    "MarkResult",
    "MockupResult",
    "OperatorResolution",
    "ParityConfig",
    "PartitionCheck",
    "PartitionProposal",
    "PlanResult",
    "Pruned",
    "PullRequest",
    "RecordCheck",
    "RecordFix",
    "RunContext",
    "SeededStory",
    "SplitResult",
    "StoryChoice",
    "StorySplit",
    "SurveyConfig",
    "UnitAssessment",
    "UnitPick",
    "VerifyReport",
    "VerifyResult",
    "WriteEpicResult",
    "WriteStoryResult",
]
