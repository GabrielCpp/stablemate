---
type: concept
title: Jobs and containment
---
# Jobs and containment

A detached job runs one long command outside any agent turn, so a measurement such as a benchmark
survives the node that started it. The workflow submits the job, parks on an `Await`, and a later
state reads what the job left behind. Submitting a job whose handle names a live process adopts
that process instead of starting a second one.

A job directory holds two results with different authors. The supervisor writes `runner.json`,
with the exit code, peak resident memory, wall seconds, kill reason, containment tier and
timestamps. The command writes its own result file, `result.json` by default. The command cannot
write the first file, so a run can tell a measurement that missed its bar from a job that produced
no measurement without asking a model.

The containment tier is the strongest this machine can deliver:

- `premium` on Linux with `systemd-run` and delegated memory and cpu cgroup controllers. The
  command runs inside a user scope with the manifest's memory and CPU limits.
- `best_effort` on any other Linux machine.
- `advisory` on every other platform.

A manifest whose `min_containment` this machine cannot meet is refused.

A run can also live in a container. The container's supervisor checks that the workspace, runs
and agent home mounts are writable, and exits 13 when one is not. It then starts the workflow run
and an optional observer as two children. A child that exits 3 asks for a reload, and the
supervisor starts it again on freshly installed source. The run's exit code becomes the
container's. The observer is installed from a read-only host mount, one numbered generation at a
time, and the two newest generations are kept. The repository's Dockerfile and compose file build
that container locally. The [run control](run-control.md) reload is how an operator asks for one.

- code: `workhorse/workhorse/job.py::supervise` @6189501d995a
- code: `workhorse/workhorse/job.py::submit` @6189501d995a
- code: `workhorse/workhorse/job.py::containment_tier` @6189501d995a
- code: `workhorse/supervisor.py::main` @6e803abf6409
- code: `workhorse/supervisor.py::require_writable` @6e803abf6409
- code: `workhorse/livesource.py::LiveSource` @b1e9c59daeb3
- code: `workhorse/livesource.py::refresh` @b1e9c59daeb3
- code: `workhorse/Dockerfile` @4b2d6e515bf7
- code: `workhorse/compose.yaml` @35e3d1511b23
- code: `workhorse/docs/DOCKER.md` @5eba57fe3d9c
- code: `workhorse/docs/JOBS.md` @1ac7e3348d78
