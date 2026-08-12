---
name: groom-telemetry
description: "Investigating a workhorse run from groom's store — the SQLite telemetry (spans/metrics/logs/turns) and the turn-record archive that sits beside it. Which command answers which question (`status`, `logs`, `cost`, `loops`, `profile`, `transcript`), why an unfinished node has no span, the archive's visit-key layout and how to get records out of a container or backfill them from the agent CLI, and the raw `sqlite3` recipes — including the dotted-attribute-key footgun that silently returns NULL. Load when asked why a run is stuck, why a loop repeats, what a run cost, or what a node actually said."
tags: [cli, backend, standards]
---

# Digging into groom telemetry and transcripts

Load this skill when you are **reading** a workhorse run rather than building one: it is
stuck and nobody knows where, a node re-decided the same thing eleven times, a run cost
more than it should have, or someone needs the reasoning behind a decision the workflow
made two days ago. For groom's own architecture — the dashboard, the sidecar, the gate
answer flow — load [[groom]] instead. This skill is about the evidence groom keeps.

Everything here reads the same two artifacts, both of which live on the machine that ran
`groom serve`:

```
<platform data dir>/groom.db          # spans, metrics, logs, turns  ($GROOM_DB overrides)
<platform data dir>/transcripts/      # the bodies: what each node visit was told and said
```

```bash
groom db-path                 # prints the db; the archive is always its sibling
ls "$(dirname "$(groom db-path)")"
```

On Linux that is `~/.local/share/groom/`. **`$GROOM_DB` moves both** — the archive root is
derived from the db path, not from the platform dir, so pointing the db at a scratch file
takes the bodies with the index instead of writing them into the real archive.

> From a stablemate checkout, prefix every command below with `uv run` to use the working
> tree. Elsewhere `groom` is on the PATH from `pipx install ./groom`. The commands are
> read-only against a live `groom serve` — the store is SQLite in WAL mode and answering a
> question does not disturb the run producing it.

## The fact that shapes every investigation

**Spans export on completion.** The node a hung run is sitting in has no row in `spans`
and never will while it hangs — which is exactly the node you came to look at. Metrics
ship on a timer regardless, so:

| The run is… | Read | Do not read |
|---|---|---|
| live, or wedged | `groom status`, `groom logs`, the `metrics` table | `spans` — the open node is absent |
| finished | `groom profile`/`cost`/`loops`, the `spans` table | — |
| gone, but you want its reasoning | `groom transcript` | telemetry, which may have aged out |

Corollary: an empty `spans` result for a live run is not a broken exporter.

## Pick the tool by the question

| Question | Command |
|---|---|
| Where is every live run right now? | `groom status` |
| Is it wedged or just slow? | `groom status` — read the idle column, below |
| What was it *doing* on the way here? | `groom logs --run RUN` |
| What did this run cost, and where? | `groom cost --run RUN` |
| What would it have cost (unpriced harness)? | `groom prices --reprice`, then `cost`'s `est$` |
| Which review→rework loops don't converge? | `groom loops --workflow coder` |
| What occupied the wall clock? | `groom profile --run RUN` |
| What did the node actually say? | `groom transcript ls` → `show` |
| Anything the CLI doesn't answer | `sqlite3 "$(groom db-path)"` |

Read them in roughly that order. Each one narrows the next: `status` names a node,
`loops` names a node that repeats, and `transcript` is where you find out why.

## Live: `status` and `logs`

```bash
groom status                     # every live run: open node, node age, agent idleness
groom status --run RUN --json
```

The diagnosis is in the pair *(turn age, agent idle)*, not in either alone:

| Reading | Means |
|---|---|
| `alive`, node age small | working normally |
| `alive`, explicit wait | operator/cap/retry wait — parked deliberately, not stuck |
| active turn age large, agent `idle` **small** | a long but **streaming** turn — healthy, leave it |
| active turn, agent `idle` **large** | **wedged** agent/tool/API inside the node |
| no turn, no wait, node age large | **wedged deterministic work** inside the node |
| no heartbeat (`DEAD?`) | the process is gone — SIGKILL, OOM, crashed host |

A ten-minute turn with a fresh heartbeat is not an incident. Workhorse heartbeats for as
long as its process lives, which is what makes silence and slowness different
observations — and why the STALL rule (nothing emitted at all) and STUCK (alive and
parked) are separate alerts.

```bash
groom logs --run RUN                      # everything, oldest-first
groom logs --run RUN --node select_item
groom logs --level WARNING                # a FLOOR: WARNING + ERROR + FATAL
groom logs --contains "over budget"
```

Deterministic nodes appear here because workhorse runs them **in-process** with a
per-node logger — that is where a script node's account of what it decided lives.
Records carry the same `run_id`/`run_dir` as the spans, so a log line joins to its node
and its on-disk artifacts with no correlation step. Do not try to join on `trace_id`: it
is zeroes, because workhorse never makes its node spans current. Join on `run_id` +
`node`.

Logs prune on their own short window (`GROOM_LOG_RETENTION_DAYS`, 3) — one row per line,
so they are the first evidence to disappear. Pull them early in a postmortem.

## Finished: `cost`, `loops`, `profile`

```bash
groom cost --run RUN         # per-node spend; the /work column first
groom loops --workflow coder # lap distribution per node; the exit column first
groom profile --run RUN      # disjoint wall-clock buckets for one run
```

- **`cost`'s `/work`** is turns per work item. A node at `1.00` ran once per story; a node
  at `4.67` re-ran three and a half times on average. Raw turn count says a node is busy;
  this says it is *looping*.
- **`loops`'s `exit`** is `work_items / turns` — how often the gate says yes. It unpacks
  `/work` into a distribution, because "every story takes four passes" and "most take one
  and a handful take twenty" want opposite fixes. Act on `excess$` (money spent on every
  lap after the first). `at-max` carries no verdict: a pile there *suggests* a `MAX_*`
  budget was exhausted, so go read the workflow's constant rather than concluding.
- **`profile`** partitions observed wall time into disjoint buckets — agent turns,
  deterministic nodes, infrastructure, explicit waits, cross-generation gaps, unclassified
  — and separates **workflow visits** (one parent node span) from **backend retries**
  (extra CLI invocations inside one visit). `visits/work` is convergence; `backend_retries`
  is provider/parsing instability. Confusing the two reads instability as thrashing.

**Cost coverage is not uniform, and the unit is harness × provider.** codex reports no
money under subscription auth; opencode reports real money via OpenRouter and a literal
`0` via a subscription provider; copilot reports neither cost nor tokens. Two failure
modes, unequally visible: nothing-reported is stored as absent (excluded from sums, shows
as a gap), while a reported `0` is **summed**, so a run that spent forty minutes can total
`$0.00` and look complete. The CLI flags both in a note — read the note before quoting a
number. `groom loops` inherits this and it bites harder there, because that report *sorts*
by money.

When the bill can't answer "which loop burned more", price the tokens instead:

```bash
groom prices                  # the rate card in force, and what it doesn't cover
groom prices --reprice        # stamp est_cost_usd on turns already in the store
groom prices --resolve        # recover a concrete model id for turns that ran an alias
```

`est$` is **never added to `usd`** — different claims, shown side by side. An unknown model
is left unpriced rather than guessed from its family. Add rates in
`~/.config/stablemate/prices.toml`. Turns carry no estimate until `--reprice` has run.

## The archive: what the node actually said

Telemetry says a node re-decided something eleven times; it cannot say why. The reasoning,
the tool calls and the file the agent read and then ignored live in the agent CLI's own
session store — on whichever host ran it, for as long as that CLI feels like keeping them.
So groom harvests its own copy on a tick (`GROOM_HARVEST_EVERY_S`, 300) into:

```
<archive>/<run_id>/<gen>-<seq>-<node>__<session_id>/
    transcript.jsonl      # what the runner captured
    prompt.md             # the rendered prompt that provoked the turn
    output.json           # the parsed answer
    context_after.json    # optional
    sidechains/           # subagent transcripts, when the copy came from the CLI store
```

Run-major, so a run drops in one `rm -rf`; keyed by the **visit**, so a node visited five
times is five directories rather than one overwritten one.

```bash
groom transcript ls --run RUN --node plan-qa    # one row per lap, in visit order
groom transcript show --session SESSION         # its files on disk + the prompt
groom transcript harvest                        # copy now, don't wait for the tick
groom transcript backfill --dry-run             # what the CLI still holds, unarchived
```

`ls` orders by the **visit key, not the clock** — so laps read top to bottom even across a
checkpoint rewind, which a wall-clock sort does not survive. `show` prints *paths*, not the
transcript: a record runs to tens of megabytes and what you want is somewhere to point a
pager, a `jq`, or a replay.

Three things routinely surprise people here:

- **`src` is recorded, never inferred.** `store` is the CLI's own session directory and is
  the richest — it carries attachments and the subagent sidechains that never cross stdout.
  `tee` is the redacted stream capture, used when that store is not on this host.
  `store-backfill` came from the CLI after the fact.
- **`legacy-N` is a reconstructed ordinal, not a real visit.** A `sessions.jsonl` written
  before the engine stamped `generation`/`seq` gets a key rebuilt from the map's own order.
  It orders the run's turns and claims nothing more — don't read `legacy-17` as generation 1,
  seq 17. Most history worth revisiting is legacy-keyed.
- **A container's run dir is on a volume the host cannot read**, and it is destroyed by the
  very event that makes anyone want it. The sidecar announces turn movement and groom
  **pulls** the records over the same socket the Files panel uses, mirroring them under
  `<archive>/.incoming/<container>/<run>` and then harvesting them as if local. The last
  pull is unconditional at the run's terminal. If the sidecar never connected, that
  container's records are simply absent — nothing else degrades, and no amount of
  `harvest` will conjure them.

Empty result from `ls` means the tick hasn't run, this host cannot see the run dir, or the
record only ever existed in the CLI's store. Try `harvest`, then `backfill --dry-run`, in
that order.

**The archive rides its own clock.** `GROOM_TRANSCRIPT_RETENTION_DAYS` defaults to `0` —
keep everything — because a transcript is wanted precisely when someone comes back long
after the spans aged out (`GROOM_RETENTION_DAYS`, 14). Do not assume telemetry and
transcripts cover the same window; the archive usually reaches further back.

### Evaluating a prompt against every session that ran it

That needs the archive transposed — not one run's laps, but every session that ever ran
that node:

```bash
groom transcript export --by-node DIR --node plan-qa --workflow coder
```

```
DIR/<workflow>/<node>/<source>__<session_id>.json
DIR/INDEX.json
```

One file per session (`task`, `source`, `session_id`, `cwd`, `model`, `time_created`,
`n_messages`, `messages[]`), streamed a line at a time because the corpus does not fit in
memory. `task` is the node, from the `sessions.jsonl` index join — classification is
**exact**, with no heading regex and no unclassified bucket. The export is a *view*: it
duplicates nothing, has no default output directory, and should be thrown away and retaken
after the next harvest rather than maintained.

## Raw SQL

There is no privileged view — the dashboard, the CLI and you read the same file.

```bash
sqlite3 -header "$(groom db-path)" "
  SELECT node, ROUND(end_ts - start_ts, 1) AS secs, status
  FROM spans WHERE run_id = 'RUN' ORDER BY start_ts DESC LIMIT 20;"
```

Four tables: **`spans`**, **`metrics`**, **`logs`** — the first three carrying an
`attrs_json` of whatever OTel attributes the producer set — and **`turns`**, which holds
no bodies at all: it is the index over the archive, keyed by
`(run_id, generation, seq, session_id)`.

### The footgun: quote every dotted key

OTel attribute keys are flat strings that merely *look* nested. `set_attribute` is called
with `usage.output_tokens`, and that reaches `attrs_json` as a literal key containing a
dot:

```sql
json_extract(attrs_json, '$.usage.output_tokens')     -- NULL, always, no error
json_extract(attrs_json, '$."usage.output_tokens"')   -- 17550
```

SQLite reads the unquoted dot as navigation into an object that is not there and returns
NULL **silently**. A query that returns all-NULL for a column you know is populated is
this, essentially every time.

Most queries dodge it entirely, because the fields worth having are real columns on
`spans`: `duration_ms`, `total_cost_usd`, `input_tokens`, `output_tokens`,
`cache_read_tokens`, `cache_creation_tokens`, `pid`, `resume_generation`, `head_start`,
`head_end`. Everything else — `workhorse.node`, `backend`, `model`, `session.id`, and
whatever the workflow declared in `labels()` — stays in `attrs_json`.

### Three column semantics to respect

- **NULL is not `0.0`.** A harness that reports no cost yields NULL, deliberately, so that
  averaging an unknown together with a real zero cannot understate spend. Spans ingested
  before these columns shipped are NULL and are never backfilled — `groom cost` falls back
  to `attrs_json`, and so should anything you write.
- **`resume_generation`** counts how many times a run dir has been started. A resume reuses
  the `run_id` and opens a fresh root span, so it is what distinguishes a gap that crosses
  a generation (crash-and-resume) from one that does not (the process waiting or thinking).
- **`head_start`/`head_end` on a span, `head` on a log and a turn, are observations, not
  assertions.** An unequal pair records that something moved `HEAD` inside that span; the
  engine says nothing about why, and reading the reason is your job. NULL means nothing
  observed a tree, which is not an unknown hash.

### Recipes

```sql
-- Which node is open right now, and for how long (no span exists for it yet).
SELECT json_extract(attrs_json, '$.node') AS node, value AS secs_in_node
FROM metrics WHERE name = 'workhorse.node.elapsed_s'
ORDER BY ts DESC LIMIT 1;

-- Recovery-ladder events: retries, reframes, compactions, watchdog kills.
SELECT s.node, e.value ->> 'name' AS event, datetime(e.value ->> 'ts', 'unixepoch')
FROM spans s, json_each(s.attrs_json, '$.events') e
WHERE s.run_id = 'RUN' ORDER BY s.start_ts;

-- Slowest nodes across every run.
SELECT node, COUNT(*) n, ROUND(AVG(end_ts - start_ts), 1) avg_s
FROM spans WHERE name NOT LIKE 'run:%' GROUP BY node ORDER BY avg_s DESC LIMIT 10;

-- From a span to the artifacts that produced it (prompt.md, output.json).
SELECT DISTINCT run_dir FROM spans WHERE run_id = 'RUN';
```

That last one is why this stays local: `run_dir` is a resource attribute on every span, so
a query hands you the path to the prompt and the outputs on disk — a join a hosted trace
backend cannot make.

The HTTP surface answers the same shapes when groom is up:
`GET /traces?run=…&node=…&status=…&slower_than=…`. It returns **only runs live right now**
unless you pass `show_ended=1` — naming an explicit `run=` always finds it, finished or
not. A "missing" run in the telemetry pane is nearly always this and not data loss.

## Hygiene, and two ways to read a lie

- **Test telemetry is not evidence.** One `make test` of the workflows suite once wrote a
  six-figure number of spans and buried every real run. Producers no longer export from a
  test process and the receivers drop records whose `run_dir` is certainly a test dir, but
  neither undoes what an older producer already wrote:

  ```bash
  groom purge-tests --dry-run    # what would go
  groom purge-tests              # delete, then VACUUM to shrink the file
  ```

  It also evicts `tempfile.mkdtemp` scratch runs — a *guess*, which is why it lives in a
  deliberate command with a preview rather than in the ingest path, where the same guess
  would discard real evidence unasked.

- **Liveness counters expire in a day** (`GROOM_LIVENESS_RETENTION_DAYS`, 1), not fourteen.
  `workhorse.run.heartbeat` / `turn.heartbeat` / `cap_wait.heartbeat` tick every ~10s per
  open node and on a long run outgrow everything else combined — in one real store the run
  heartbeat alone was 1.77M of 2.21M metric rows. Nothing reads their history, so their
  absence beyond a day is by design, not a gap. The gauges (`turn.active`, `turn.idle_s`,
  `wait.active`, `wait.elapsed_s`, `node.elapsed_s`, `node.active`) keep the normal window,
  and those are the ones a postmortem wants.

- **Don't count a run's age as a problem.** Resumptions reuse a run identity and multi-day
  runs are normal — which is why groom deliberately has no rule on total run age. A hard
  wall-clock limit is workhorse's `WORKHORSE_MAX_RUNTIME_S`, not something to infer here.

Full as-built reference: `groom/README.md` in the stablemate workspace, and the design book
under `docs/features/groom/` (`ostler graph --surface groom`).
