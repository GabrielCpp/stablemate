# groom

The package behind the `groom` dashboard, its OTLP collector and the in-container `groom-sidecar`. It shows every running workflow and lets an operator answer its gates.

## Map

- `alerts.py`: the alert rules over the telemetry stream, and the hot cache they read. It decides what pages the away operator.
- `app.py`: the Litestar app and every HTTP and websocket route: dashboard, JSON reads, sidecar pushes and the OTLP endpoints.
- `archive.py`: freezing a finished run's telemetry out of `groom.db` onto disk, and the sweep that decides which runs qualify.
- `assets/`: the dashboard's browser client and its static files.
- `attend.py`: dispatching an attendant agent to a run that parked on a gate or died, and its settings.
- `attend_ledger.py`: the attendant sessions table: one row per attendance, its session ids and its outcome.
- `attend_transcript.py`: where an attendant's session transcript is kept, and rendering it as a conversation.
- `attention.py`: the wire records for attention events shared by the producer and `groom wait`.
- `checkpoints.py`: reading a workhorse checkpoint's position without raising.
- `cli.py`: the `groom` and `groom-sidecar` console entry points and every `groom` subcommand.
- `discovery.py`: the startup scan that finds workhorse containers already running before groom started.
- `dispatch.py`: the config-declared dispatch queues that launch a workflow per item under a concurrency cap.
- `dispatch_ledger.py`: the dispatch items table: each queued item's status, pid and exit.
- `docker_io.py`: every call to the `docker` CLI: listing, exec, file reads and writes, and diffs inside a volume.
- `export.py`: writing the turn archive out in the by-node layout distillation reads.
- `gates.py`: the operator gate file format: its status, its question, and writing an answer into it.
- `live_history.py`: the history an open run pane holds, advanced by each committed OTLP batch.
- `localfs.py`: file, git and process reads for native runs on groom's own host. It is the local twin of `docker_io.py`.
- `models.py`: the plain records shared across groom: workflow, gate, container and per-run telemetry state.
- `notify.py`: sending an away notification to the configured phone channels.
- `otlp.py`: decoding OTLP/HTTP protobuf requests into plain span, log and metric dicts.
- `pools.py`: the bounded thread pools that keep one kind of blocking work from starving another.
- `prices.py`: the rate card that estimates a turn's cost when the harness does not report one.
- `projection.py`: turning groom's state into the JSON the dashboard renders, including fleet order and liveness.
- `run_inbox.py`: a run's `inbox.jsonl`, read and appended on a native host path or inside a docker runs volume.
- `settings.py`: the `[groom.attend]` and `[groom.dispatch]` tables of the home config, resolved with where each value came from.
- `sidecar.py`: the in-container watcher that reports gates and run state to the host over one websocket.
- `sidecar_hub.py`: the host-side registry of live sidecar sockets and the RPCs sent over them.
- `sidecar_turns.py`: pulling a container's turn records over the sidecar socket into the archive.
- `state.py`: the in-memory process state: tracked workflows, open tabs, watched runs and the broadcast to them.
- `store.py`: the SQLite telemetry store: its schema, its connection and the queries over spans, metrics, logs and turns.
- `turns.py`: the durable archive of turn records and the harvester that fills it from run directories.
- `wait.py`: `groom wait`, which blocks on the websocket until a chosen attention event arrives.
