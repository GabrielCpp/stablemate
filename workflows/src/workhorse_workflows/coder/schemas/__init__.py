"""Agent reply models and node return models for the coder workflow.

The same two-kinds-of-model split `research` and `author` established, and the same reason
for it: `self.agent(prompt, returns=T)` validates a model out of whatever the turn produced
and reads `T`'s fields to build the output keys it asks for; a node returns a plain typed
value. Nothing here crosses a state boundary — a transition carries keyword arguments bound
against the next state's own signature, so a state's parameters are its schema.

The modules are the coder's subjects, one per YAML sub-graph or per group of the main
graph's nodes. Everything derives from `CoderResult` in `_base`, which is what makes a
partially-answered node degrade into defaults rather than raise.
"""
from __future__ import annotations

from workhorse_workflows.coder.schemas._base import CoderResult
from workhorse_workflows.coder.schemas.ci import (
    CiChecks,
    CiRepoPick,
    FixCiResult,
    PushOutcome,
)
from workhorse_workflows.coder.schemas.dev import (
    BranchOutcome,
    DevResult,
    DispatchEntry,
    FixLintResult,
    ImplContext,
    ImplResult,
    LayerPick,
    LintOutcome,
    OperatorAnswer,
    OperatorResolution,
    PlanResult,
    PlanValidation,
    QaRunEntry,
    ReuseResult,
)
from workhorse_workflows.coder.schemas.dream import (
    ImprovementsRecorded,
    ReflectionResult,
    RunEvidence,
)
from workhorse_workflows.coder.schemas.genesis import (
    AgentsYml,
    ConventionsResult,
    FarrierInstall,
    FixResult,
    GenesisReport,
    GitInit,
    Skeleton,
    TargetClassification,
)
from workhorse_workflows.coder.schemas.story import SpecsStamped, StoryPaths, WorkspaceDirs

__all__ = [
    "AgentsYml",
    "BranchOutcome",
    "CiChecks",
    "CiRepoPick",
    "CoderResult",
    "ConventionsResult",
    "DevResult",
    "DispatchEntry",
    "FarrierInstall",
    "FixCiResult",
    "FixLintResult",
    "FixResult",
    "GenesisReport",
    "GitInit",
    "ImplContext",
    "ImplResult",
    "ImprovementsRecorded",
    "LayerPick",
    "LintOutcome",
    "OperatorAnswer",
    "OperatorResolution",
    "PlanResult",
    "PlanValidation",
    "PushOutcome",
    "QaRunEntry",
    "ReflectionResult",
    "ReuseResult",
    "RunEvidence",
    "Skeleton",
    "SpecsStamped",
    "StoryPaths",
    "TargetClassification",
    "WorkspaceDirs",
]
