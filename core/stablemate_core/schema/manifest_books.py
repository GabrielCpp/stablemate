"""Declaration: the book and QA tables of the per-repository manifest."""

from __future__ import annotations

from typing import Literal

from .base import Section, setting


class QaFixture(Section):
    """One QA fixture: a command that puts the application into a known state."""

    tool: str | None = setting(
        None,
        description="The command that runs the fixture, found on PATH.",
        examples=["seed-db"],
        default_text="unset",
    )
    args: list[str] = setting(
        factory=list,
        description="Arguments passed to the tool.",
        examples=[["--profile", "demo"]],
    )
    provides: str | None = setting(
        None,
        description="The state the fixture guarantees, in the terms a scenario's preconditions use.",
        examples=["a signed-in admin with two projects"],
        default_text="unset",
    )
    timeout: float = setting(
        120.0,
        description="Seconds the fixture may run before it is stopped.",
        examples=[300],
    )


class BookTable(Section):
    """The books above one service, read by ostler."""

    team: str | None = setting(
        None,
        description="The team whose book this repository reads: the pages under `teams/<team>/` in the artifacts dir. No team book is read while it is unset.",
        examples=["platform"],
        default_text="unset",
    )
    home: Literal["artifacts", "repo"] = setting(
        "artifacts",
        description="Where this repository's book lives: the `artifacts` folder, or `repo`, beside the code, for a tool that publishes its own book.",
        examples=["repo"],
        default_text="artifacts",
    )
    product: str | None = setting(
        None,
        description="The product whose pages under `products/<product>/` in the artifacts dir this repository reads and writes.",
        examples=["acme"],
        default_text="the repository name",
    )


class QaTable(Section):
    """What ostler's QA runs may use."""

    fixtures: dict[str, QaFixture] = setting(
        factory=dict,
        description="Fixtures keyed by name. A scenario's precondition names one.",
        examples=[
            {"seeded-db": {"tool": "seed-db", "provides": "a database with demo rows"}}
        ],
    )
    recordingExemptTargets: list[str] = setting(
        factory=list,
        description="QA targets that may run without a screen recording.",
        examples=[["web"]],
    )
