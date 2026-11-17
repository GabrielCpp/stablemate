story: none
date: 2026-11-16
elements: RunTask, RunTaskThatFails, ResumeTask, FileRecord, Round, Look
sources: paddock/paddock/runner.py::_write_ledger, paddock/paddock/runner.py::_report, paddock/paddock/cli.py::_report

A round's result lives under results/<benchmark>/<task>/<data commit>-<stablemate sha>/<n>/. The stablemate sha is
the HEAD of the checkout paddock is imported from, so the path differs on every machine and after every commit, and
a watch cannot name it. The book reads what a round did through two other doors.

The first is the tasks themselves. Each step writes a note under <sandbox>/seen/ with the facts a reader of the
README would want shown: the stage holds the data files and no remote, the config is the base with the task's
override laid over it, a relative artifacts_dir names a folder inside the stage, the pin is a clone behind a fence
with no remote, the inputs read through the helpers. Each note is a file the watch lists with the lines it holds.

The second is a person copying a result out of results/ by hand, which the README says to do to keep one. The
KeepTheResults event copies the latest ledger.json and score.json of each task into kept/, and the watch lists which
statuses, segments and caveats each holds. A round that ends in a step failure, a resume or an interruption still shows
as it did.

The lines paddock prints for a step carry its seconds with one decimal. A step that only reads files takes under
fifty milliseconds, so its line is `0.0s`. The only step that starts a process is the one that runs `false`, and it
is the slowest of them.
