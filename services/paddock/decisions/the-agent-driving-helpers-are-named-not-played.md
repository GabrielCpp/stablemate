story: none
date: 2026-11-16
elements: RunTask
sources: paddock/paddock/tasks/inputs.py, paddock/paddock/tasks/forensics.py::cycles, paddock/paddock/tasks/judge.py::render

paddock.tasks holds the helpers a benchmark's tasks module imports. The book plays the ones a step can run with no
agent: inputs (names, number, flag), judge.render, forensics.entered_nodes and cycles, operator_gates.record_hand_answer
and its reads, and tree.stage_members and repos_at. The library task calls them and writes what they returned.

greenfield, replay and the stablemate helpers drive workhorse and an agent CLI for minutes, run uv, farrier and git
over the stage and spend a budget, and judge.call_agent calls a model. A play must not start them, so RunTask names
their files in its source and says nothing of what they print. A benchmark that uses them states its own score.
