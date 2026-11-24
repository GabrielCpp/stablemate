from .a_runs_life_on_the_page import ARunsLifeOnThePage
from .judging_a_run_against_its_median import JudgingARunAgainstItsMedian
from .looking_through_the_panes import LookingThroughThePanes
from .narrowing_the_list import NarrowingTheList
from .reading_a_run_with_no_telemetry import ReadingARunWithNoTelemetry
from .reading_a_blocked_run import ReadingABlockedRun
from .the_attendant_is_switched_on_the_page import TheAttendantIsSwitchedOnThePage
from .the_list_is_ordered import TheListIsOrdered

ALL = (
    ARunsLifeOnThePage, TheListIsOrdered, NarrowingTheList, TheAttendantIsSwitchedOnThePage,
    ReadingABlockedRun, ReadingARunWithNoTelemetry, LookingThroughThePanes, JudgingARunAgainstItsMedian,
)
