from ostler.book import Interaction

from ..fixtures import Push, Query, Reply, Settings
from ..model.actions import AnswerFromPage, FilterRuns, Navigate, OpenRun as SelectRun, PushBlocked, PushExited, PushProgress, SwitchAttendant
from .screens import Attendant, Dispatch, History, RunDetail, Runs
from .screens import Settings as SettingsScreen


class ReportProgress(Interaction[Push]):
    source = ("groom/groom/app.py",)
    does = "a workflow reports progress to groom from its container while the dashboard is open, and the page shows the run"
    carries = PushProgress


class ReportGate(Interaction[Push]):
    source = ("groom/groom/app.py",)
    does = "a workflow reports a gate waiting on an operator while the dashboard is open, and the page shows the run as blocked"
    carries = PushBlocked


class ReportExit(Interaction[Push]):
    source = ("groom/groom/app.py",)
    does = "a workflow reports that it exited while the dashboard is open, and the page shows the run as ended"
    carries = PushExited


class FilterTheList(Interaction[Query]):
    source = ("groom/groom/assets/dashboard.js",)
    screen = Runs
    does = "types in the filter box above the run list; an empty box shows every run"
    carries = FilterRuns


class OpenSettings(Interaction[object]):
    source = ("groom/groom/assets/dashboard.js",)
    screen = Runs
    leads_to = SettingsScreen
    does = "presses Settings in the left bar"
    carries = Navigate


class OpenRuns(Interaction[object]):
    source = ("groom/groom/assets/dashboard.js",)
    screen = SettingsScreen
    leads_to = Runs
    does = "presses Runs in the left bar"
    carries = Navigate


class SwitchTheAttendant(Interaction[Settings]):
    source = ("groom/groom/assets/dashboard.js", "groom/groom/settings.py")
    screen = SettingsScreen
    does = "ticks or clears the attendant checkbox in the settings pane"
    carries = SwitchAttendant


class OpenRun(Interaction[Push]):
    source = ("groom/groom/assets/dashboard.js",)
    screen = Runs
    leads_to = RunDetail
    does = "presses a run in the list; its detail pane opens beside the list with the gate it waits on"
    carries = SelectRun


class AnswerTheGate(Interaction[Reply]):
    source = ("groom/groom/assets/dashboard.js", "groom/groom/app.py")
    screen = RunDetail
    does = "types an answer under the question of a blocked run and presses Send answer"
    carries = AnswerFromPage


class OpenHistory(Interaction[object]):
    source = ("groom/groom/assets/dashboard.js",)
    screen = Runs
    leads_to = History
    does = "presses History in the left bar"
    carries = Navigate


class OpenAttendant(Interaction[object]):
    source = ("groom/groom/assets/dashboard.js",)
    screen = Runs
    leads_to = Attendant
    does = "presses Attendant in the left bar"
    carries = Navigate


class OpenDispatch(Interaction[object]):
    source = ("groom/groom/assets/dashboard.js",)
    screen = Runs
    leads_to = Dispatch
    does = "presses Dispatch in the left bar"
    carries = Navigate


ALL = (
    ReportProgress, ReportGate, ReportExit, FilterTheList, OpenSettings, OpenRuns, SwitchTheAttendant,
    OpenRun, AnswerTheGate, OpenHistory, OpenAttendant, OpenDispatch,
)
