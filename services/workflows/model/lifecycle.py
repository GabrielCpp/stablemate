"""The lifecycle matrix of a working directory: how far it has come, and what
each command does to it there."""

from __future__ import annotations

from datetime import date
from typing import Callable

from ostler.book import Axes, Scene

from ..commands import (DryRunAuthor, DryRunCoder, DryRunLoopRunner, DryRunOkfBook, DryRunResearch, DryRunReviewDebt,
                        Look, New)
from ..events import InstallSkills
from ..fixtures import OTHER_CHECK, dry_run, new
from .state import Workspace, stage

TODAY = date(2026, 11, 12)

SCENES = (
    Scene("bare", "the directory holds nothing", lambda today: ()),
    Scene("skills installed", "the skills the prompts name are installed in the repository",
          lambda today: (InstallSkills(),)),
    Scene("scaffolded", "workhorse-new wrote fix-tests here", lambda today: (New(new()),)),
    Scene("scaffolded with skills", "fix-tests is written and the skills are installed",
          lambda today: (New(new()), InstallSkills())),
)

ACTIONS: dict[str, Callable[[Workspace], object]] = {
    "new": lambda m: New(new()),
    "new into out": lambda m: New(new(into="out")),
    "new with another check": lambda m: New(new(check=OTHER_CHECK, into="other")),
    "new with a bad name": lambda m: New(new("Fix-Tests")),
    "new with a blank check": lambda m: New(new(check="  ")),
    "new without a check": lambda m: New(new(check=None)),
    "new without a name": lambda m: New(new(None)),
    "new without either": lambda m: New(new(None, check=None)),
    "loop-runner": lambda m: DryRunLoopRunner(dry_run()),
    "research": lambda m: DryRunResearch(dry_run()),
    "author": lambda m: DryRunAuthor(dry_run()),
    "coder": lambda m: DryRunCoder(dry_run()),
    "okf-book": lambda m: DryRunOkfBook(dry_run()),
    "review-debt": lambda m: DryRunReviewDebt(dry_run()),
    "look": lambda m: Look(),
}

MATRICES = (Axes[Workspace]("workspace", TODAY, SCENES, ACTIONS, stage, state_of=lambda m, _: stage(m)),)
