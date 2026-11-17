story: none
date: 2026-11-16
elements: RunTask, ResumeTask, Round
sources: paddock/paddock/runner.py::_interrupt, paddock/paddock/runner.py::resume, paddock/paddock/cli.py::main

A step that raises the runner's RoundInterrupted ends `paddock run` with exit 130 and no result. The workspace keeps
round.json and steps.json, and `paddock resume` finds the highest round that has no result and runs only the steps
without an ok outcome (paddock/paddock/runner.py::_unfinished_workspace, resume). The ledger it writes then holds
both segments, `interrupted` and `finished`.

The 130 answer declares no stdout. Its message goes to stderr, where it names the round by the data commit and the
stablemate sha, and the sha differs per checkout, so the book does not quote it. The rule for it says only that
the round is left open.

A scene cannot be arranged by a step the app refuses, and 130 is a refusal. The scene `interrupted` is reached by the
StopARound event, which starts the interrupt task by hand and lets the model take the same change a refused run
makes. A column and a journey step still call RunTask on the interrupt task, which is where the 130 is judged.

The interrupt task passes its second step only once it finds its own note from the first attempt. A run of the task
after that note exists therefore finishes in one go, which is why the model reads the note.
