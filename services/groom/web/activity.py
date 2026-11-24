"""The Activity tab of a run that reported no telemetry, and of a run groom archived."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.book import Action, Actor, Transaction

from ..fixtures import Archived, Push
from ..model.state import Dashboard


@dataclass(frozen=True)
class Note:
    """What the Activity tab of a run says in place of a timeline."""

    text: str

    def __str__(self) -> str:
        return self.text


NO_TELEMETRY = "No telemetry for this run. It was recorded before telemetry, or it exports to another collector."


class ReadActivityTab(Action[Push, Dashboard]):
    accept = Push

    @staticmethod
    def reduce(a: Push, s: Dashboard, by: Actor | None) -> Transaction:
        return Transaction(says=(Note(NO_TELEMETRY),))




@dataclass(frozen=True)
class ArchivedTab:
    """What the Activity tab of an archived run shows: its tabs, the filters and keys of the timeline,
    the turn the reading pane gives, and the one problem count of the Overview, the control and the tab."""

    tabs: tuple[str, ...]
    chips: tuple[str, ...]
    hints: tuple[str, ...]
    turn: str
    problems: int
    chip: int
    tab: int

    def __str__(self) -> str:
        return f"tabs {', '.join(self.tabs)} | chips {', '.join(self.chips)} | keys {', '.join(self.hints)} | turn {self.turn} | problems {self.problems} on the link, {self.chip} on the control, {self.tab} on the tab"


@dataclass(frozen=True)
class ArchiveGone:
    """What the Activity tab says of an archive whose files are gone, and whether the Overview keeps the summary."""

    text: str
    timeline: bool
    overview: bool

    def __str__(self) -> str:
        return f"{self.text} | timeline {self.timeline} | overview {self.overview}"


FILES_GONE = "Activity cannot be read This archive's files are gone. The Overview still shows the run's stored summary."


class ReadArchivedActivityTab(Action[Archived, Dashboard]):
    accept = Archived

    @staticmethod
    def reduce(a: Archived, s: Dashboard, by: Actor | None) -> Transaction:
        if a.gone:
            return Transaction(says=(ArchiveGone(FILES_GONE, False, True),))
        tab = ArchivedTab(
            ("Overview", "Activity"), ("logs", "problems", "raw", "steps"), ("j k move", "e next problem"),
            "Documented the flow.", 1, 1, 1,
        )
        return Transaction(says=(tab,))


@dataclass(frozen=True)
class ArchivedRecords:
    """What Raw and the search box of an archived run's Activity tab show: the first page of records,
    the order, the note above them, the metric samples before and after the control asks for them,
    the older records on request, and what a search finds in the rows and in the transcripts."""

    first_page: int
    newest_first: bool
    note: str
    metrics_hidden: bool
    with_metrics: int
    older_loaded: bool
    row_hit: str
    transcript_hit: str

    def __str__(self) -> str:
        return (
            f"raw {self.first_page} records, newest first {self.newest_first} | {self.note} | metric samples hidden {self.metrics_hidden}, "
            f"then {self.with_metrics} shown | older on request {self.older_loaded} | search rows {self.row_hit} | search transcripts {self.transcript_hit}"
        )


class ReadArchivedRecordsTab(Action[Archived, Dashboard]):
    accept = Archived

    @staticmethod
    def reduce(a: Archived, s: Dashboard, by: Actor | None) -> Transaction:
        shown = ArchivedRecords(
            200, True, "Every stored record, newest first. This run has 268 records, with 3 metric samples hidden. Showing the newest 200.", True, 3, True, "qa-story", "in transcript: Port 5432 is held, so I will use a free port.",
        )
        return Transaction(says=(shown,))
