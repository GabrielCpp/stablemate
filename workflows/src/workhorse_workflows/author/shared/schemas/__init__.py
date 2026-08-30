"""The models the author workflow's seams need, grouped the way `nodes/` is.

`self.agent(prompt, returns=T)` validates a model out of whatever the turn produced and
reads `T`'s fields to build the output keys it asks for; a node returns a plain typed
value. Nothing here crosses a state boundary — a transition carries keyword arguments
bound against the next state's own signature, so a state's parameters are its schema.

The submodules are the subjects:

* `main` — the author's own graph (`nodes/config.py` through `nodes/artifacts.py`)
* `survey` — the surveyor sub-flow (`shared/survey/`)
* `parity` — what the parity surveyor adds on top of it (`parity_surveyor/nodes/parity.py`)
"""
from __future__ import annotations

from workhorse_workflows.author.shared.schemas._base import AuthorResult
from workhorse_workflows.author.shared.schemas.edit import (
    AppliedEpicEdit,
    EditIntent,
    EpicEditPlan,
    EpicEditReview,
    EpicRewriteResult,
    EpicSnapshot,
    MilestoneSnapshot,
    ResolvedBullet,
    SeedChange,
    SeedSnapshot,
    StoryChange,
    StorySnapshot,
)
from workhorse_workflows.author.shared.schemas.main import (
    AuditFinding,
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
    MockupGate,
    MockupResult,
    Pruned,
    PullRequest,
    RoadmapStatus,
    RunContext,
    SeededStory,
    StoryChoice,
    StoryMutation,
    StorySplit,
    VerifyReport,
    WriteEpicResult,
    WriteStoryResult,
)
from workhorse_workflows.author.shared.schemas.parity import ParityConfig
from workhorse_workflows.author.shared.schemas.survey import (
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
    "AuditFinding",
    "AuditResult",
    "AppliedEpicEdit",
    "AuthorResult",
    "Branches",
    "Committed",
    "Config",
    "CoverageReview",
    "DecomposeResult",
    "Defects",
    "EmitResult",
    "EditIntent",
    "EpicEditPlan",
    "EpicEditReview",
    "EpicRewriteResult",
    "EpicSnapshot",
    "EpicChoice",
    "EpicReview",
    "Expansion",
    "Feedback",
    "InventoryCheck",
    "Ledger",
    "MarkResult",
    "MockupGate",
    "MockupResult",
    "MilestoneSnapshot",
    "OperatorResolution",
    "ParityConfig",
    "PartitionCheck",
    "PartitionProposal",
    "PlanResult",
    "Pruned",
    "ResolvedBullet",
    "PullRequest",
    "RoadmapStatus",
    "RecordCheck",
    "RecordFix",
    "RunContext",
    "SeededStory",
    "SeedChange",
    "SeedSnapshot",
    "SplitResult",
    "StoryChoice",
    "StoryChange",
    "StoryMutation",
    "StorySnapshot",
    "StorySplit",
    "SurveyConfig",
    "UnitAssessment",
    "UnitPick",
    "VerifyReport",
    "VerifyResult",
    "WriteEpicResult",
    "WriteStoryResult",
]
