# Telemetry — observing an unattended run

A run meant to survive a week is a run nobody is watching. workhorse streams
OpenTelemetry spans, metrics and log records to a local OTLP collector so something else
can watch it: what state it is in, what each agent turn cost, when the recovery ladder
fired, and — crucially — whether a long silence is a legitimate spending-cap sleep or a
hang.

It is off unless a collector is actually there, and a complete no-op when it isn't. This
document covers turning it on (and off), what is emitted, how turn spans are normalized
across harnesses so costs are comparable, and how to tag spans with your own unit of
work.

For the resilience ladder those span events come from, see
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).
For `labels()`, see
[docs/AUTHORING.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#labels-and-saying-what-the-run-is-doing).

For away-from-keyboard monitoring of long runs, workhorse streams OpenTelemetry
spans and metrics to a local OTLP collector — by default `groom`, which stores them
in SQLite and pages you (ntfy/webhook + browser) on stall/budget/churn. Install the
extra once and it turns itself on whenever the collector is up:

```bash
pip install 'workhorse-agent[otel]'
groom serve                                                # now every run is observed
```

**Enablement is a tri-state.** With `WORKHORSE_OTEL` unset (the default),
`start_run` opens one short TCP connection to the endpoint and enables telemetry
only if something is listening — so a machine running `groom serve` gets spans with
no env var, and a machine without one stays a complete no-op. Set it explicitly to
override that decision in either direction:

| `WORKHORSE_OTEL` | Behavior |
|---|---|
| _unset_ (default) | **Auto** — probe the endpoint; enable only if it answers |
| `1` / `true` / `yes` | Force on — no probe (for a collector that comes up later, or one a TCP connect can't see) |
| `0` / `false` / `no` | Force off — no probe, never enabled |

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:8787   # groom serve (the default)
export WORKHORSE_OTEL=0                                    # opt out of auto-on
```

Auto-on is the default because the runs most worth observing are the unattended
week-long ones — exactly the runs nobody remembers to export a variable before
launching. Without the `otel` extra installed, auto mode stays silently inert (an
explicit `WORKHORSE_OTEL=1` still warns that the SDK is missing, since you asked).

Emitted: a root span per run, a span per node visit (nested through flows), a span
per agent-CLI turn with duration + token usage + cost (and a `session.id` attribute
linking it to the CLI session transcript), span events for the recovery ladder
(retry/reframe/compact/watchdog-kill), **log records** from the driver and the node
functions it calls (`groom logs`), and a **cap-wait heartbeat**
metric each pause tick — the signal that lets a collector distinguish a legitimate
multi-day spending-cap sleep (heartbeating = alive) from a hang (silence). With no
collector reachable, telemetry is a complete no-op and adds no dependencies;
exports are best-effort, so a collector that dies *mid-run* can never slow or wedge
a run either. Any standard OTLP/HTTP backend
(Jaeger, Grafana Tempo) works unchanged.

**Turn spans are comparable across backends.** Every harness reports what a turn
consumed and every one spells it differently, so workhorse normalizes them onto one
set of attribute names (Claude's, since those spans are already in the store): tokens
in/out, cache read/write, reasoning tokens, and `total_cost_usd` where the harness
reports money at all. Cost is left *absent* rather than zeroed when a harness doesn't
say — a real `0.0` (a subscription turn) and "this CLI doesn't report cost" are
different facts, and averaging them together understates spend. `duration_ms` is
stamped by the engine when the CLI omits it, so latency coverage is total regardless
of harness. Backends that report per *step* rather than per turn (opencode) are summed.

**Tag spans with your own unit of work** by overriding a workflow's `labels()` — re-read
before every transition and stamped as span attributes. Without it a store can group by
run and state but not by task; see [Labels, and saying what the run is
doing](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/AUTHORING.md#labels-and-saying-what-the-run-is-doing).

There is also a wall-clock ceiling,
`WORKHORSE_MAX_RUNTIME_S` — see
[docs/GUARDRAILS.md](https://github.com/GabrielCpp/stablemate/blob/main/workhorse/docs/GUARDRAILS.md).

