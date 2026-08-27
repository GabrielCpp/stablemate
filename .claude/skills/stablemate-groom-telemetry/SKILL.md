---
name: stablemate-groom-telemetry
description: "Investigating a workhorse run from groom's store — the SQLite telemetry (spans/metrics/logs/turns) and the turn-record archive that sits beside it. Which command answers which question (`status`, `logs`, `cost`, `loops`, `profile`, `transcript`), why an unfinished node has no span, the archive's visit-key layout and how to get records out of a container or backfill them from the agent CLI, and the raw `sqlite3` recipes — including the dotted-attribute-key footgun that silently returns NULL. Load when asked why a run is stuck, why a loop repeats, what a run cost, or what a node actually said."
metadata:
  generated_by: farrier
  source: library/skills/groom/telemetry/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-groom-telemetry/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
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
| What did the node actually say? | `groom transcript ls` → `show` — [archive](references/archive.md) |
| Anything the CLI doesn't answer | `sqlite3 "$(groom db-path)"` — [raw SQL](references/raw-sql.md) |

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
session store, which groom harvests on a tick into an archive beside the db.

```bash
groom transcript ls --run RUN --node plan-qa    # one row per lap, in visit order
groom transcript show --session SESSION         # its files on disk + the prompt
```

**[references/archive.md](references/archive.md)** carries that branch whole: the
`<run_id>/<gen>-<seq>-<node>__<session_id>/` visit-key layout, why `ls` sorts by visit and
not the clock, what `src` and a `legacy-N` key mean, how a container's records are pulled
over the sidecar socket, the retention clock that outlives telemetry, and the `--by-node`
export that transposes the archive for evaluating one prompt across every session that ran
it. Read it when `ls` comes back empty, when a record is on a host you cannot reach, or
when you are grading a prompt rather than debugging a run.

## Raw SQL

There is no privileged view — the dashboard, the CLI and you read the same file. Four
tables: `spans`, `metrics`, `logs` — the first three carrying an `attrs_json` of whatever
OTel attributes the producer set — and `turns`, the bodiless index over the archive.

```bash
sqlite3 -header "$(groom db-path)" "
  SELECT node, ROUND(end_ts - start_ts, 1) AS secs, status
  FROM spans WHERE run_id = 'RUN' ORDER BY start_ts DESC LIMIT 20;"
```

**[references/raw-sql.md](references/raw-sql.md)** carries the rest, and you want it before
writing a second query: the dotted-key footgun that returns NULL **silently** for every
`usage.output_tokens`-shaped extract, which fields are real columns and so dodge it, the
three column semantics that make a wrong answer look right (NULL is not `0.0`;
`resume_generation`; `head_start`/`head_end` are observations), the recipe set, and the
`/traces` HTTP surface. Read it whenever the table above sends you to `sqlite3`.
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
