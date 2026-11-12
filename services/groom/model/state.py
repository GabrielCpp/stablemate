"""The states groom can be in. The fleet is the runs pushed to it, kept in creation
order. The one mode of the whole app is the attendant, which is off until an operator
turns it on; groom has no sign-in, so no state refuses a call."""

from __future__ import annotations

from typing import Hashable, cast

from ostler.book import Collection, State, Unique

from .records import Alert, AttendSummary, Filter, Fleet, Line, Panel, Row, Run


class GroomApp(State):
    runs = Collection(Run, Unique("container_id"))
    attend = "off"

    def row(self, entity: object) -> Row:
        run = cast(Run, entity)
        return Row(
            id=run.container_id,
            run_id=run.container_id,
            name=run.name,
            repo=run.repo,
            row_id=run.container_id[:4],
            state=run.state,
            live=run.live,
            live_label=run.live_label,
            node=run.current_node,
            doing=run.gate_path,
            gate_path=run.gate_path,
            gate_count=len(run.gates),
            exit_code=run.exit_code,
            exit_hint=run.exit_hint,
            rank=run.rank,
        )

    def alerts(self) -> tuple[Alert, ...]:
        found: list[Alert] = []
        for run in self.runs:
            for gate in run.gates:
                found.append(Alert(run.container_id, "blocked", run.current_node, gate.question, gate.file_path))
            if run.state == "finished":
                found.append(Alert(run.container_id, "ended", run.current_node, "", "", message=f"workflow exited with code {run.exit_code}"))
        return tuple(found)

    def fleet(self, query: str = "") -> Fleet:
        ordered = sorted(self.runs, key=lambda r: (r.rank, r.name, self.runs.position(r.container_id)))
        shown = tuple(self.row(r) for r in ordered if matches(r, query))
        return Fleet(shown, self.alerts(), AttendSummary(self.attend))

    def rows(self) -> tuple[object, ...]:
        return self.fleet().runs

    def key(self) -> Hashable:
        return (type(self).__name__, tuple(self.runs))


def matches(run: Run, query: str) -> bool:
    if not query:
        return True
    needle = query.lower()
    haystack = [run.name, run.repo_name, run.repo_branch, run.current_node, *(g.file_path for g in run.gates)]
    return any(needle in part.lower() for part in haystack)


class Off(GroomApp):
    attend = "off"


class Headless(GroomApp):
    attend = "headless"


FILTER_KEY = "runs"


def filter_matches(run: Run, text: str) -> bool:
    """The dashboard filters its list in the page: it trims and lowercases what is typed and looks
    in the run's name, repo, node, what it is doing and its id."""
    needle = text.strip().lower()
    if not needle:
        return True
    haystack = [run.name, run.repo, run.current_node, run.gate_path, run.container_id]
    return any(needle in part.lower() for part in haystack)


class Dashboard(GroomApp):
    """The dashboard page over the fleet: the run list narrowed by the filter box, and the
    attendant switch in the settings pane."""

    filters = Collection(Filter, Unique("key"))

    def row(self, entity: object) -> Row:
        if isinstance(entity, Filter):
            return cast(Row, entity)
        return super().row(entity)

    def typed(self) -> str:
        return next((f.text for f in self.filters if f.key == FILTER_KEY), "")

    def lines(self) -> tuple[Line, ...]:
        typed = self.typed()
        ordered = sorted(self.runs, key=lambda r: (r.rank, r.name, self.runs.position(r.container_id)))
        return tuple(
            Line(r.container_id, r.state, r.live, r.repo, r.container_id[:4], r.live_label, r.gate_path)
            for r in ordered
            if filter_matches(r, typed)
        )

    def rows(self) -> tuple[object, ...]:
        return (*self.lines(), Panel(self.attend))

    def key(self) -> Hashable:
        return (type(self).__name__, tuple(self.runs), self.typed())


class DashboardOff(Dashboard, Off):
    pass


class DashboardHeadless(Dashboard, Headless):
    pass
