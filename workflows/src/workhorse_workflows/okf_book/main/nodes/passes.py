"""A pass's record on disk: what its turns were handed, and the notes of each turn."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from workhorse_workflows.okf_book.shared.blueprint import blueprint

BREADTH_DIR = "breadth"
REASONS_DIR = "reasons"


class Skeletons(BaseModel):
    """What a skeleton turn wrote, what it left and what it found odd."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    written: list[str] = Field(default_factory=list, description="The name of each Screen class written.")
    left: list[str] = Field(default_factory=list, description="One line per entry file that got no screen: the file, a colon, and why.")
    odd: list[str] = Field(default_factory=list, description="One line per thing a user would find wrong in what you read, such as a text in the wrong language, a typo, a control that does nothing or two screens that name one thing differently: the file, a colon, and what is wrong.")


class Reasons(BaseModel):
    """What a reasons turn wrote and what it could not settle."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    written: list[str] = Field(default_factory=list, description="The slug of each decision file written.")
    open: list[str] = Field(default_factory=list, description="One line per question added to QUESTIONS.md: the screen's class name, a colon, and the question.")


def _no_files_handed(_logger: logging.Logger, *_args: object) -> list[str]:
    return []


def _batch_handed(_logger: logging.Logger, _run_dir: Path, _folder: str, batch: list[str], *_args: object) -> list[str]:
    return sorted(batch)


@blueprint.node(stub=_no_files_handed, aliases=("breadth_handed",))
def pass_handed(logger: logging.Logger, run_dir: Path, folder: str) -> list[str]:
    """What a pass's turns were already handed, read from the pass's folder under the run."""
    del logger
    handed = run_dir / folder / "handed.txt"
    if not handed.is_file():
        return []
    return [line for line in handed.read_text(encoding="utf-8").splitlines() if line]


@blueprint.node(stub=_batch_handed, aliases=("record_breadth",))
def record_pass(logger: logging.Logger, run_dir: Path, folder: str, batch: list[str], sections: dict[str, list[str]]) -> list[str]:
    """Record a batch as handed and write the notes of its turn under the pass's folder."""
    path = run_dir / folder
    path.mkdir(parents=True, exist_ok=True)
    handed = sorted({*pass_handed(logger, run_dir, folder), *batch})
    (path / "handed.txt").write_text("".join(f"{item}\n" for item in handed), encoding="utf-8")
    slug = re.sub(r"[^A-Za-z0-9]", "-", batch[0]) if batch else "empty"
    note = "\n".join(f"## {heading}\n" + "".join(f"- {item}\n" for item in items) for heading, items in sections.items())
    (path / f"{slug}.md").write_text(note, encoding="utf-8")
    return handed
