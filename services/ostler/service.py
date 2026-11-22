"""ostler, as ostler loads it."""

from __future__ import annotations

from ostler.book import App, Because, Environment, Service, Stack, Unseen

from .books import ALL as BOOKS
from .commands import ALL as COMMANDS, Look
from .graph import (ALL as GRAPH, BacklogDropWithoutReason, CreateSpecOfUnknownStory, CutFrames, Doctor, EditRenameUnknown, EnvAddress, EnvRenderUnknown, EnvResetUnknown, EnvUpUnknown, LintBadPlan,
                    MilestoneEpicsUnknown, RunBadPlan, RunGrpcPlan, RunPhonePlan, RunWebPlan, ValidateBadPlan, VetArtifact,
                    VetOfUnknownStory, VetWithoutArguments, VetWithoutRegions)
from .books import ExplainNothing, SearchUnmovedBook
from .journeys import ALL as JOURNEYS
from .model import FileRecord, Plan
from .model.lifecycle import MATRICES
from .surface import OstlerCli

SURFACE_RUNTIME = (
    "browser", "pagesurface", "pagedata", "listjudge", "screen", "asked", "device", "mobilesurface", "rpc", "proxy", "signed",
    "delivery",
)
SHARED_RUNTIME = (
    "arrange", "backstage", "boundary", "cast", "contracts", "denied", "entries", "errors", "event", "planner", "stack",
    "surface", "workspace", "home",
)
IGNORED = (
    "ostler/ostler/_vendor/*", "ostler/ostler/__init__.py", "ostler/ostler/api.py", "ostler/ostler/*README.md",
    *(f"ostler/ostler/book/{name}.py" for name in (*SURFACE_RUNTIME, *SHARED_RUNTIME)),
)

NEEDS_A_RUNTIME = (
    Unseen(RunWebPlan, "0", Because.RUNTIME, "a pass needs a browser; a machine with Playwright, ffmpeg and the plan's secret shows it"),
    Unseen(RunPhonePlan, "0", Because.RUNTIME, "a pass needs a device and the Maestro CLI; a machine with an emulator and the plan's secret shows it"),
    Unseen(RunGrpcPlan, "0", Because.RUNTIME, "a pass needs a gRPC service answering at the address the plan calls"),
)

LOCAL = Environment("local", {})

REFUSED = "the call has no argument to vary, and the sandbox never makes it succeed"
UNSEEN = tuple(Unseen(command, "inputs", Because.NEVER_FILLED, REFUSED) for command in (
    Doctor, EditRenameUnknown, MilestoneEpicsUnknown, CreateSpecOfUnknownStory, BacklogDropWithoutReason, VetArtifact, LintBadPlan,
    ValidateBadPlan, RunBadPlan, CutFrames, ExplainNothing, SearchUnmovedBook, EnvRenderUnknown, EnvAddress, RunWebPlan, RunPhonePlan, RunGrpcPlan, VetWithoutArguments,
    VetWithoutRegions, VetOfUnknownStory, EnvUpUnknown, EnvResetUnknown))

service = Service[Plan](
    name="ostler",
    environments={"local": LOCAL},
    default_environment="local",
    new_model=Plan,
    surface=OstlerCli,
    journeys=JOURNEYS,
    stack=lambda log_dir: Stack((), log_dir),
    endpoints=(*COMMANDS, *GRAPH, *BOOKS),
    matrices=MATRICES,
    watch=(Look(),),
    records=(FileRecord,),
    unseen=(*UNSEEN, *NEEDS_A_RUNTIME),
    app=App(roots=("ostler/ostler",), verified="VERIFIED", ignore=IGNORED),
)
