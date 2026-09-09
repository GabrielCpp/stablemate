---
type: concept
slug: native-run-ending-verdict
title: Native-run ending verdict
---
# Native-run ending verdict

Native-run ending verdict is the per-tick, same-host detector that demotes a native workhorse run's dashboard status to *finished* when telemetry has not yet said so. The [groom app module](groom-app-module.md)'s `_sync_native_row` calls it on every telemetry beat and every [live-loop](groom-app-module.md#algorithm-live-update-convergence) tick, and stamps the verdict it returns onto the run's [run telemetry](run-telemetry.md) `terminal` field so the row's *recency* verdict (`projection.is_live`) and its *terminal* verdict agree without two readers racing the same source. Liveness is otherwise a telemetry question, and a containerized run has no choice but to wait for an export; a native run shares groom's host, which makes two facts directly observable that no exporter can be relied on to deliver:

* `run.json`'s terminal — written by the run itself as it stops, on disk whether or not the exporter got its last flush out;
* whether the run's pid still exists — the only witness left for a run that never got to write anything, the SIGKILL/OOM/segfault class the workhorse engine documents as taking the driver down with it.

Without this verdict the only remaining signal is silence, and silence is deliberately slow: `LIVE_AFTER_S` is three minutes because a healthy run must not flicker. So a native run that died stayed on the dashboard as *running / alive* for minutes — a false green on precisely the event an operator is watching for. Both facts here are same-host reads costing a stat and a signal, so the row can be corrected on the very next tick instead.

The verdict names the current session only and is self-clearing: a resume rewrites `run.json` with a null terminal and exports under a new pid, and the caller stamps `terminal_ts` so the alert engine's stale-terminal logic drops it the moment any newer signal lands. A truthy verdict is also the input the alert engine consumes through [note_native_ending](run-telemetry.md#note_native_ending) — the verdict layer and the alert-firing layer are siblings, not the same call: this function decides *what* the run ended as, that one decides *whether to page an operator*.

- code: groom/groom/app.py::_native_ending
- extends: [run telemetry](run-telemetry.md)
- tests: groom/tests/test_native_row.py::test_run_json_terminal_retires_the_row_without_waiting_for_silence
- tests: groom/tests/test_native_row.py::test_a_vanished_pid_retires_a_run_that_never_recorded_an_ending
- tests: groom/tests/test_native_row.py::test_a_live_pid_with_no_record_stays_running
- tests: groom/tests/test_native_row.py::test_a_locally_stamped_ending_is_cleared_by_the_resumed_session

## Contract

The helper exists so the dashboard can stop claiming a native run is alive when same-host evidence says it ended, without waiting for silence or for a fresh telemetry beat. Three return values cover the three states the host can read.

- return shape: one of three strings — `run.json`'s `terminal` field when truthy, the literal `"died"` when pid liveness contradicts an empty terminal, or `""` when no evidence of ending is present.
- verify: json_path(path="$", matches="^(|[a-z_]+|died)$")
- input: a [run telemetry](run-telemetry.md) record that has already been classified as native. The caller decides nativeness through [run telemetry `field-native`](run-telemetry.md#field-native); this function does not re-check.
- reads: `run.run_dir` through [run-terminal](groom-localfs-module.md#run-terminal) and `run.pid` through [pid-alive](groom-localfs-module.md#pid-alive). No Docker, no telemetry, no websocket, no socket round-trip.
- terminal-source precedence: a truthy `run.json` terminal takes precedence over the pid liveness check — the run's own verdict wins even when the pid is still alive.
- pid-source precedence: the pid liveness check is consulted only when `run.json`'s terminal is empty AND `run.pid` is truthy.
- empty-pid: a `None` pid produces `""`, because pid-liveness cannot speak for a run that has not yet reported a pid.
- failure handling: the underlying [run-terminal](groom-localfs-module.md#run-terminal) and [pid-alive](groom-localfs-module.md#pid-alive) helpers are best-effort and return zero values rather than raising.
- state boundary: this helper does not mutate the [run telemetry](run-telemetry.md) record, the [workflow registry](workflow-registry.md), the [alert](alert.md) set, or any dashboard or websocket state.
- session scope: the verdict names the current session only.
- alert-firing boundary: this helper is upstream of [note_native_ending](run-telemetry.md#note_native_ending); it fires no alerts.

## Methods

### method-_native_ending

- sig: `_native_ending(run: RunTelemetry) -> str`
- abstract: false
- does: reads [run-terminal](groom-localfs-module.md#run-terminal) once for `run.run_dir`.
- does: returns the [run-terminal](groom-localfs-module.md#run-terminal) string unchanged when that read yields a truthy value.
- verify: json_path(path="$.terminal", equals="the run.json terminal string after _sync_native_row stamps the verdict")
- does: when [run-terminal](groom-localfs-module.md#run-terminal) is empty, reads [pid-alive](groom-localfs-module.md#pid-alive) once for `run.pid` when `run.pid` is truthy.
- does: returns the literal `"died"` when [run-terminal](groom-localfs-module.md#run-terminal) is empty AND `run.pid` is truthy AND [pid-alive](groom-localfs-module.md#pid-alive) returns `False`.
- verify: json_path(path="$.terminal", equals="died")
- does: returns `""` when [run-terminal](groom-localfs-module.md#run-terminal) is empty AND either `run.pid` is falsy OR [pid-alive](groom-localfs-module.md#pid-alive) returns `True`.
- verify: json_path(path="$.terminal", equals="")
- does: suppresses the underlying exceptions by returning `""` rather than propagating.
- verify: json_path(path="$.terminal", equals="")
- does: does not raise under any input.
- verify: json_path(path="exception.type", absent=true)
- returns: a non-empty terminal verdict OR `""` — two cases for one return shape.
- verify: json_path(path="$", matches="^(|[a-z_]+|died)$")
- code: groom/groom/app.py::_native_ending

Produce the strongest same-host verdict that a native run has ended, by reading `run.json`'s terminal first and falling back to pid liveness when the run never wrote one. The return value is a single string, not a structured record: truthy is a verdict the caller should stamp, falsy is "no evidence" and the caller should leave the record alone.

#### Effects

- Reads: `<run.run_dir>/run.json` through [run-terminal](groom-localfs-module.md#run-terminal), exactly once per call.
- Reads: signal-0 and `/proc/{pid}/stat` through [pid-alive](groom-localfs-module.md#pid-alive) when the first read yields no terminal and `run.pid` is truthy, exactly once per call.
- Returns: the verdict string — `run.json`'s `terminal` field, the literal `"died"`, or `""` — without mutating the [run telemetry](run-telemetry.md) record, the [workflow registry](workflow-registry.md), the [alert](alert.md) set, the dashboard state, or any websocket frame.
- Preserves: every field on the [run telemetry](run-telemetry.md) record, every entry in the [workflow registry](workflow-registry.md), and every alert already in the [alert](alert.md) engine's dedup set; this helper is read-only.
- Excludes: telemetry reads, Docker inspection, websocket reads, sidecar queries, dashboard broadcasts, alert firing, [workflow registry](workflow-registry.md) mutations, and persistent state — those belong to `_sync_native_row`, [note_native_ending](run-telemetry.md#note_native_ending), and the [dashboard shell broadcaster](dashboard-shell-broadcaster.md).

## Algorithms

### algorithm-native-run-ending-verdict

Given a [run telemetry](run-telemetry.md) record the caller has classified as native, the helper asks the [run-terminal](groom-localfs-module.md#run-terminal) helper for `<run.run_dir>/run.json`'s `terminal` field. If that field is truthy, the helper returns it unchanged, because the run wrote its own ending and the run's own word wins over any host-side liveness signal — even a stopped run whose parent has not yet reaped the pid does not get a foreign verdict. If the field is empty, the helper asks [pid-alive](groom-localfs-module.md#pid-alive) for `run.pid` only when `run.pid` is truthy; a `None` pid skips the second read because pid-liveness cannot speak for a run that never reported one. When the second read returns `False`, the helper returns the literal `"died"` — the run did not write its own ending, but the process is gone, and that is the SIGKILL/OOM/segfault class the workhorse engine documents as taking the driver down with it. When the second read returns `True`, or when `run.pid` was falsy and the first read was empty, the helper returns the empty string `""`, because no evidence of ending is present and the verdict layer must not speak for a healthy run.

## Verdict Outcomes

A truthy verdict is one the caller stamps; an empty verdict is one the caller ignores.

- `run.json` terminal: any non-empty value — `"fail"`, `"done"`, `"cancelled"`, or a future workhorse-defined status — is the run's own ending and wins outright.
- `pid` dead with no terminal: the literal `"died"` — a process witness without a run-side account, distinct from any of the words the run might have written.
- `pid` alive with no terminal: `""` — a healthy run has no verdict, and the verdict layer does not invent one.
- `pid` absent with no terminal: `""` — a run that has not yet reported a pid cannot be retired by pid liveness alone.

## Self-Clearing Semantics

A verdict stamped today can clear itself tomorrow in three ways.

- resume: a `--resume-run` reuses the run dir and run id, rewrites `run.json` with `terminal: null` before doing anything else, and exports under a new pid. The next telemetry beat reaches [is-local-dir](groom-localfs-module.md#is-local-dir) and pid-alive with a fresh state.
- terminal-ts: the caller stamps `run.terminal_ts = time.time()` alongside `run.terminal`, and the alert engine's stale-terminal logic clears the verdict the moment a newer span or metric lands for the same run id.
- session boundary: the verdict names the current session only.

## Failure Semantics

The helper itself never raises; the underlying helpers absorb every error as a zero value, and the verdict layer observes those zero values rather than exceptions.

- consistency: run-terminal — a missing `<run.run_dir>/run.json` collapses to `""` from [run-terminal](groom-localfs-module.md#run-terminal).
- verify: json_path(path="$.terminal", equals="")
- consistency: pid-alive — a vanished pid collapses to `False` from [pid-alive](groom-localfs-module.md#pid-alive).
- verify: json_path(path="$.terminal", equals="died")
- exceptions: the underlying [run-terminal](groom-localfs-module.md#run-terminal) and [pid-alive](groom-localfs-module.md#pid-alive) helpers do not raise; this helper catches no exceptions because none are produced.
- verify: json_path(path="exception.type", absent=true)