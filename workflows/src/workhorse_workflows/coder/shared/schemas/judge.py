"""The judge's models: its ruling on a closed question, and the story texts an escape question reads."""
from __future__ import annotations

from pydantic import Field
from workhorse.pyflow import dry_run

from workhorse_workflows.coder.shared.schemas._base import CoderResult


@dry_run(answers={})
class Ruling(CoderResult):
    """The judge's answers to one closed question, by subject."""

    answers: dict[str, str] = Field(
        default_factory=dict,
        description="Subject id to the one allowed answer that fits it. Leave a subject out "
        "when you are not sure, and the run treats it as the default answer.",
    )
