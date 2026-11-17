story: none
date: 2026-11-16
elements: SandboxRun
sources: paddock/paddock/cli.py::cmd_sandbox_build, paddock/paddock/sandbox.py::build, paddock/paddock/sandbox.py::Sandbox.refusals

`paddock sandbox run` checks, in order, that a command follows `--`, that the config reads and names only agent CLIs
the sandbox has a login for, that no mount is missing or duplicated or holds the stablemate checkout, and that
--workdir names one of the apps (paddock/paddock/cli.py::cmd_sandbox_run, paddock/paddock/sandbox.py). A call that
passes all of them hands the container to docker and returns docker's exit code. The book plays every refusal and
never the pass, so the success answer and the input classes are declared unseen: docker, its image and its daemon are
the machine's, not the app's.

`paddock sandbox build` is not a command of the book. It runs `uv build --all-packages` over the checkout and then
docker build, takes the agent CLI releases from the machine, and cannot be played without starting both. Its code is
named in this decision's sources.

The check for a mount that holds the checkout is not played either, since it needs a path that holds the checkout of
whoever runs the book.
