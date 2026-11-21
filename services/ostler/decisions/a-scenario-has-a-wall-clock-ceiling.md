story: none
date: 2026-11-21
elements: RunPlan
sources: ostler/ostler/qa/harness_host.py::SCENARIO_WALL_S, ostler/ostler/qa/drivers.py

A QA scenario is killed after one hour of wall-clock time, however often it reports. The silence timeout restarts on
every record the scenario writes, so a scenario that keeps reporting could otherwise run as long as it liked and hold the
whole run.

The scenario's process group is killed, its result fails with a message that names the ceiling, and its entry in the
run's scenarios carries `overran`. A reader of the result can tell a scenario that was too long from one that failed a
check. An interrupted run also kills the group of the scenario it was waiting on, so none outlives it.

The ceiling does not say whether the scenario is too long or the app hangs. The run leaves that call to the operator.
