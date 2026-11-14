"""The breadth pass's record on disk: the files a skeleton turn was handed, and the notes of each turn."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from workhorse_workflows.okf_book.shared.blueprint import blueprint

BREADTH_DIR = "breadth"


class Skeletons(BaseModel):
    """What a skeleton turn wrote, what it left and what it found odd."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    written: list[str] = Field(default_factory=list, description="The name of each Screen class written.")
    left: list[str] = Field(default_factory=list, description="One line per entry file that got no screen: the file, a colon, and why.")
    odd: list[str] = Field(default_factory=list, description="One line per thing a user would find wrong in what you read, such as a text in the wrong language, a typo, a control that does nothing or two screens that name one thing differently: the file, a colon, and what is wrong.")


def _no_files_handed(_logger: logging.Logger, *_args: object) -> list[str]:
    return []


def _batch_handed(_logger: logging.Logger, _run_dir: Path, batch: list[str], *_args: object) -> list[str]:
    return sorted(batch)


@blueprint.node(stub=_no_files_handed)
def breadth_handed(logger: logging.Logger, run_dir: Path) -> list[str]:
    """The files a skeleton turn was already handed, read from the run's breadth folder."""
    del logger
    handed = run_dir / BREADTH_DIR / "handed.txt"
    if not handed.is_file():
        return []
    return [line for line in handed.read_text(encoding="utf-8").splitlines() if line]


@blueprint.node(stub=_batch_handed)
def record_breadth(logger: logging.Logger, run_dir: Path, batch: list[str], reply: Skeletons) -> list[str]:
    """Record a batch as handed and write the notes of its skeleton turn under the run's breadth folder."""
    folder = run_dir / BREADTH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    handed = sorted({*breadth_handed(logger, run_dir), *batch})
    (folder / "handed.txt").write_text("".join(f"{path}\n" for path in handed), encoding="utf-8")
    slug = re.sub(r"[^A-Za-z0-9]", "-", batch[0]) if batch else "empty"
    sections = (("Written", reply.written), ("Left", reply.left), ("Odd for a user", reply.odd))
    note = "\n".join(f"## {heading}\n" + "".join(f"- {item}\n" for item in items) for heading, items in sections)
    (folder / f"{slug}.md").write_text(note, encoding="utf-8")
    return handed
