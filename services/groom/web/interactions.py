from ostler.book import Interaction

from ..fixtures import Judged, Push, Query, Reply, Settings
from ..model.actions import AnswerFromPage, FilterRuns, Navigate, OpenRun as SelectRun, PushBlocked, PushExited, PushProgress, SwitchAttendant
from .activity import ReadActivityTab
from .median import JudgeRun
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
    does = "presses a run in the list; its detail pane opens beside the list with the gates it waits on in a strip above the tabs"
    carries = SelectRun


class ReadActivity(Interaction[Push]):
    source = ("groom/groom/assets/dashboard.js",)
    screen = RunDetail
    does = "presses Activity in the tabs of the open run. A run that reported no telemetry, which is every run a push creates, reads 'No telemetry for this run. It was recorded before telemetry, or it exports to another collector.' where the timeline would be"
    carries = ReadActivityTab


class ReadTheMedian(Interaction[Judged]):
    source = ("groom/groom/assets/dashboard.js", "groom/groom/medians.py")
    screen = History
    does = "chooses the workflow of ended runs in History. The run's cell under $/item vs median and the median cell of the totals say how the run compares with the other successful runs of its workflow"
    carries = JudgeRun


class AnswerTheGate(Interaction[Reply]):
    source = ("groom/groom/assets/dashboard.js", "groom/groom/app.py")
    screen = RunDetail
    does = "types an answer in the strip above the tabs, under the question of a blocked run, and presses Send answer"
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
    OpenRun, ReadActivity, ReadTheMedian, AnswerTheGate, OpenHistory, OpenAttendant, OpenDispatch,
)
