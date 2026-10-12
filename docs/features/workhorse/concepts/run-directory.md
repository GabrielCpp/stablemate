---
type: concept
title: Run directory
---
# Run directory

Every run writes to one directory under `--runs-dir`, default `./.agents/runs`. The directory is
named `<workflow>-<run id>`. The run id is `--run-id` when given. Without it, the run id is `p`
followed by eight hex digits of a digest of the params. With no params either, the run id is
`default`. So the same params land in the same directory. A rerun into a directory whose run never
finished picks up where that run stopped. A rerun into a finished run's directory starts over, and
`--no-cache` starts over in either case.

The files an operator reads:

- `run.json` records the process and the outcome. While the run is going it holds the pid. When
  the run ends, its `terminal` field holds `terminal` for a finished walk or `fail` for a failed
  one.
- `checkpoint.json` records where the run is: the flow, the state, the params and the gate it
  waits on. A rewind moves it, and a resume starts from it. A checkpoint whose shape belongs to
  the retired YAML engine is refused by every reader.
- `events.jsonl` logs one line per node phase: enter, done, terminal, error or rewind.
- `launch.json` records the command line that resumes the run, and whether the run was launched
  in a container.
- `inbox.jsonl` is the [operator inbox](operator-inbox.md).
- `control.sock` is the socket a live run listens on, described in [run control](run-control.md).
- `turns/` holds one directory per agent-node visit, with its `prompt.md`, its `output.json` and
  its `usage.json`, described in [agent turns](agent-turns.md).

Agent CLI session ids are kept per chain of turns, so a later turn of the same chain resumes the
same session. Before each turn the run snapshots the git trees the turn may touch.

- code: `workhorse/workhorse/records.py::RunRecord` @ce33d3ae4195
- code: `workhorse/workhorse/records.py::LaunchRecord` @ce33d3ae4195
- code: `workhorse/workhorse/records.py::PyflowCheckpoint` @ce33d3ae4195
- code: `workhorse/workhorse/rundir.py::derive_run_id` @aa85ef04e897
- code: `workhorse/workhorse/rundir.py::find_latest_resumable` @aa85ef04e897
- code: `workhorse/workhorse/artifacts.py::ArtifactWriter` @ea09ba99b938
- code: `workhorse/workhorse/sessions.py::read_chain` @f6e3de822358
- code: `workhorse/workhorse/turnkey.py::VisitKey` @0dffcaf7cfde
- code: `workhorse/workhorse/scratch.py::scratch_dir` @32d503d3e5ca
- code: `workhorse/workhorse/gitstate.py::RepoState` @88deaba0786e
- code: `workhorse/workhorse/gitstate.py::snapshot_tree` @88deaba0786e
