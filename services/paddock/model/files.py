"""The files the book watches and what the model keeps for each: its path and
which of the declared strings it holds. A row is that and nothing more."""

from __future__ import annotations

from typing import ClassVar, cast

from ostler.book import Collection, Mark, Watched

CONFIG = "config.toml"
BROKEN_HOME = "x = ("
EMPTY_ROOT = "/empty"
DATA_HEAD = "made/data-repo.txt"
DATA_COMMITTED = "committed"
BROKEN_BENCHMARK = "root/gold/broken/tasks.py"
BROKEN_TASKS = "RuntimeError"

SEEN: dict[str, tuple[str, ...]] = {
    "seen/plain-stage.txt": ("stage holds README.md", "stage has no remote"),
    "seen/plain-project.txt": ("pinned=False", "pinned=True", "default_cli=claude", "artifacts_dir inside the stage",
                               "pin fenced", "pin has no remote"),
    "seen/override.txt": ("default_cli=codex", "artifacts_dir kept"),
    "seen/inputs.txt": ("budget=1200.0", "only=A-1,B-2", "label=x,y", "strict=True", "absent=7.5", "none=0"),
    "seen/failing.txt": ("first ran",),
    "seen/failing-later.txt": ("later ran",),
    "seen/tools.txt": ("exit=1", "ok=False"),
    "seen/scored.txt": ("measured",),
    "seen/interrupt-start.txt": ("started",),
    "seen/interrupt-park.txt": ("parked", "passed"),
    "seen/interrupt-finish.txt": ("finished",),
    "seen/library.txt": ("entered=abababc", "cycle=ab x3", "render=Score a on 2", "members=0",
                         "gate=docs/context.md hand abc123", "repos=['']"),
}

LEDGER = (
    '"pinned": false', '"pinned": true', '"status": "ok"', '"status": "failed"', '"status": "skipped"',
    '"outcome": "interrupted"', '"outcome": "finished"', '"caveats": []', "step 'boom' failed",
    "step 'later' skipped", "step 'misread' failed", "step 'missing_tool' failed", "one trial was short",
)
SCORE = ("null", '"headline": "caught 7/9  missed 2"', '"a: caught"', '"b: missed"', '"one trial was short"')

MARKS = (
    Mark(CONFIG, BROKEN_HOME, EMPTY_ROOT),
    Mark(DATA_HEAD, DATA_COMMITTED),
    Mark(BROKEN_BENCHMARK, BROKEN_TASKS),
    *(Mark(path, *holds) for path, holds in SEEN.items()),
    Mark("kept/*.ledger.json", *LEDGER),
    Mark("kept/*.score.json", *SCORE),
)


class FileRecord(Watched):
    """A watched file the sandbox holds."""

    marks = MARKS
    source: ClassVar[tuple[str, ...]] = ("paddock/paddock/runner.py::_write_ledger", "paddock/paddock/runner.py::_drive")


class FileRows:
    files: Collection[FileRecord]

    def rows(self) -> tuple[FileRecord, ...]:
        return tuple(sorted(self.files, key=lambda f: f.path))

    def row(self, entity: object) -> FileRecord:
        return cast(FileRecord, entity)
