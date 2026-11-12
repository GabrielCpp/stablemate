from ostler.book import Interaction

from ..fixtures import Push, Query, Settings
from ..model.actions import FilterRuns, Navigate, PushBlocked, PushExited, PushProgress, SwitchAttendant
from .screens import Runs
from .screens import Settings as SettingsScreen


class ReportProgress(Interaction[Push]):
    does = "a workflow reports progress to groom from its container while the dashboard is open, and the page shows the run"
    carries = PushProgress


class ReportGate(Interaction[Push]):
    does = "a workflow reports a gate waiting on an operator while the dashboard is open, and the page shows the run as blocked"
    carries = PushBlocked


class ReportExit(Interaction[Push]):
    does = "a workflow reports that it exited while the dashboard is open, and the page shows the run as ended"
    carries = PushExited


class FilterTheList(Interaction[Query]):
    screen = Runs
    does = "types in the filter box above the run list; an empty box shows every run"
    carries = FilterRuns


class OpenSettings(Interaction[object]):
    screen = SettingsScreen
    does = "presses Settings in the left bar"
    carries = Navigate


class OpenRuns(Interaction[object]):
    screen = Runs
    does = "presses Runs in the left bar"
    carries = Navigate


class SwitchTheAttendant(Interaction[Settings]):
    screen = SettingsScreen
    does = "ticks or clears the attendant checkbox in the settings pane"
    carries = SwitchAttendant


ALL = (ReportProgress, ReportGate, ReportExit, FilterTheList, OpenSettings, OpenRuns, SwitchTheAttendant)
