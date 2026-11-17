story: none
date: 2026-11-16
elements: RunTaskThatFails
sources: paddock/paddock/cli.py::_report, paddock/paddock/runner.py::_run_steps

`paddock run` writes its step lines to stdout and exits 1 when a step failed, and writes its errors to stderr and
exits 1 when it never started. A command declares one shape per exit code, so one class cannot say both. RunTask
declares exit 1 as stderr and keeps to tasks whose steps all pass, and RunTaskThatFails declares exit 1 as the stdout
lines and keeps to tasks whose steps fail. The argv is the same, with the benchmark fixed to acme.

A refusal that comes before the first step leaves nothing on stdout, so RunTaskThatFails words it as the empty message.
Its refusals are only the ones its columns can reach.
