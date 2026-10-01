# workhorse

The import package of the engine that drives an agent CLI through a checkpointed state machine. Run-wide records, operator channels and telemetry live here. The state machine, the command line and the agent turn each have their own subdirectory.

## Map

- `artifacts.py`: the run directory's files as one writer: checkpoints, per-node outputs, the event log, usage and `run.json`.
- `cli/`: the subcommands a workflow's console script carries, and the arguments each one takes.
- `config_run.py`: the immutable per-run settings and the recovery ladder's tuning knobs, read once from the environment.
- `context.py`: the flat key to value bag a node's prompt and arguments render against.
- `control.py`: the socket an operator talks to a live run over, and the request and reply framing on it.
- `gates.py`: the `STATUS:` and `SCOPE:` header of an operator gate file, and how an answer is written into it.
- `gitstate.py`: what a working tree looked like at one moment, and putting a tree back to a recorded start.
- `inbox.py`: the run-scoped inbox of operator messages and their replies.
- `job.py`: one long command run outside an agent turn, under a detached supervisor with a containment tier and a cost record.
- `logsetup.py`: console logging for workhorse and its script nodes, and shipping those records to the OTel collector.
- `manifest.py`: the farrier context manifest of a repo, projected onto the render context a prompt sees.
- `otel.py`: every span, metric and log a run exports, and the rule that telemetry never fails a run.
- `packaged.py`: where a workflow package's own files sit on disk.
- `profile.py`: which agent CLI and model profile a run is on, and the models a power resolves to under it.
- `pyflow/`: the Python state machine: its base class, transitions, registry, driver and static graph.
- `records.py`: the typed shapes of the records a run writes and reads back: checkpoint, `run.json`, `launch.json` and events.
- `references.py`: the preflight that finds skill and prompt references a workflow's prompts make that will not resolve.
- `reload.py`: what a reload or stop request means to a run that is already going.
- `rewind.py`: moving a stopped run's checkpoint to another state, validated and backed up.
- `rundir.py`: the run id, which run directory an operator means, and the resume argv for it.
- `runner/`: one agent turn: spawning the CLI, classifying its end, and the retry ladder around it.
- `scratch.py`: the per-machine scratch directory for a subject, kept outside any repo.
- `sessions.py`: where a run files each chain's agent-CLI session id.
- `templates.py`: the one Jinja2 environment every prompt renders in, with its loaders and farrier helpers.
- `testing.py`: test helpers a workflow author imports: a real git repo and file assertions.
- `turnkey.py`: the identity of one agent-node visit that every writer names it by.
- `worklist.py`: the generic worklist a run works through: select next, claim, count and snapshot.
