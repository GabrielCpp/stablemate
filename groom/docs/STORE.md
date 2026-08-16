# Reading the store — cost, loops, transcripts, schema

`groom serve` is a collector as well as a dashboard: every span, metric and log record a
run emits lands in one local SQLite file, and the commands here are the questions worth
asking of it after the fact. `groom status` and `groom logs` answer *where a run is* and
*what it said* — those stay in [README.md](../README.md). This document is the analysis
half: what a run cost, what it would have cost elsewhere, which loops converge, what a
node actually said, where the wall clock went, and the schema underneath all of it.

Everything below reads the same file, so nothing here is privileged over `sqlite3` —
which is the point of the last section.

## What a run cost (`groom cost`)

Where the money and the rework went, per node:

```console
$ groom cost --run RUN
node                         turns  /work      usd     est$  share    min
-------------------------------------------------------------------------
plan-qa                         84   4.67   181.38   142.05  21.7%    730
document-story                  89   4.68   116.54    97.20  13.9%    602
implement-plan                  23   1.21   104.40    88.71  12.5%    317
```

Only `agent_turn` spans are counted — a node span wraps its turn, so totalling
both would double every figure, and an in-process `self.call` node spent no agent
money by definition.

`/work` is turns per work item, and it is the column to read first. A workflow
stamps `work_id` itself (the coder workflow uses the story slug), so a node at
`1.00` ran once per story while a node at `4.67` re-ran three and a half times on
average. Raw turn count tells you a node is *busy*; this tells you it is
*looping*, which is a different and usually more actionable problem.

**Cost coverage is not uniform, and the unit is harness × _provider_.** codex reports
no money at all under subscription auth. opencode reports real money through OpenRouter
and a literal `0` through a subscription provider — the same CLI, the same event shape,
because cost belongs to the provider behind it. copilot reports neither cost nor tokens
at all (it bills in premium requests).

The two ways of not pricing a turn differ in how visible they are. Nothing-reported is
recorded as absent rather than a fabricated `0.0`, so it is excluded from the sum and
shows up as a gap. A reported `0` is *summed* — so a run that spent forty minutes can
total `$0.00` and look complete. `groom cost` flags both, naming the backends:

```
note: 2 of 3 turns reported no cost, so usd and share cover only the 1 that did.
note: 2 turn(s) reported a cost of exactly 0 while spending output tokens. A turn that
      emitted tokens did not cost nothing — it was not priced. …
```

A turn that emitted no tokens and cost 0 is *not* flagged: it really was free.

Nodes that reported no cost are ranked among themselves by minutes rather than by
turn count, so an unpriced node that spent an hour in three turns still sorts above
one that spent two minutes in twenty.

Duration is comparable across harnesses but not identical: when the CLI reports a
turn duration that value is used, and when it does not (codex reports none) the
engine's own wall clock is stamped instead, which includes process spawn.

## What it would have cost (`groom prices`)

The caveats above leave a real question unanswerable: half the turns in a busy store
report no money, so *which of these two loops burned more* has no answer from the bill.
`est$` answers it from the tokens instead — every turn's four token counts at a published
rate card, in its own column:

```console
$ groom prices                    # the rates in force, and what they do not cover
$ groom prices --reprice          # estimate the turns already in the store
$ groom prices --reprice --all    # …including ones already estimated, after a rate change
$ groom prices --resolve          # price alias turns from the model their session names
```

**`est$` is never added to `usd`.** They are different claims — what a vendor billed
versus what a rate card says the tokens are worth — and a column mixing them answers
nothing. `groom cost` prints them side by side and says how many turns the estimate
covers.

**An unknown model is not priced.** No family guessing and no averaging of neighbours:
a model the table does not name yields no estimate and is listed as unpriced, so the
estimate's coverage is a number rather than an impression.

**An alias is recovered, not guessed** (`--resolve`). A CLI invoked as `--model sonnet`
stamps that alias on every turn, and no rate card can name it. But the session store the
turn ran in records what the provider actually *ran*, per assistant message, so the id is
recoverable rather than lost: `--resolve` reads it from there, prices the tokens with it,
and stamps `priced_model` so every estimate says which rate produced it. Two conditions
keep that a recovery — the concrete id has to contain the alias (a session that ran both
opus and sonnet resolves each to its own model), and exactly one candidate has to match.
An ambiguous session is left unpriced; a coin flip between two rates reads as evidence
and is not. Resolution recovers a name and never invents a rate: a session naming only
models the card does not cover stays unpriced and stays listed.

Groom ships rates for the Anthropic models its own runs use. Everything else goes in
`~/.config/stablemate/prices.toml` (`$GROOM_PRICES` points elsewhere), where whoever
pays the bill can keep it current:

```toml
[models."acme/fast-1"]
input = 1.25          # $ per million input tokens
output = 10.0
cache_read = 0.125    # optional; defaults to 0.1 x input
cache_write = 2.5     # optional; defaults to 2.0 x input
```

Then `groom prices --reprice` to apply it. A malformed file is logged and ignored
rather than raised — a typo in a rate card must not take down the dashboard reading it.

**How accurate.** Cache defaults follow Anthropic's published multipliers, taking the
one-hour write rate rather than the five-minute one, because a run holding one context
across a long turn is what this is used to price. Checked against 528 turns in a live
store that reported a real price: median per-turn estimate 0.99× the billed amount,
aggregate 0.82× — the tail it misses is turns that mixed both TTLs and turns billed at
the long-context premium. That is the accuracy on offer, and it is why the column stays
separate rather than filling the gaps in `usd`.

Turns already in the store carry no estimate until `--reprice` has run over them: unlike
the promoted token columns, this one is derived here rather than reported by anyone, so
there is no attribute to fall back to.

## Which loops converge (`groom loops`)

`cost` says which nodes are expensive. `loops` says which are expensive *because
they repeat*, and what the repetition costs:

```console
$ groom loops --workflow coder
node                         items turns   exit  mean  max at-max   >=3  excess$    verdict
-------------------------------------------------------------------------------------------
plan-qa                         43   237    18%  5.51   13      1   84%   221.48  thrashing
document-story                  55   249    22%  4.53   10      3   75%   137.20  thrashing
implement-plan                  52    75    69%  1.44    4      1    8%    35.97      loose
```

The unit is the **lap count per work item** — one row of `cost`'s `/work` column
unpacked into its distribution, because the mean cannot separate *every* story
taking four passes from most taking one and a handful taking twenty, and those
want opposite fixes.

`exit` is the headline: `work_items / turns`, the share of laps that are the last
one for their work item. It is the maximum-likelihood per-lap acceptance
probability of a memoryless loop, which is what a review gate is — it re-reads a
rewritten artifact with no memory of how often it has already objected. Read it as
**how often this gate says yes**. Verdicts are labels on it (`converged` ≥ 80%,
`loose` ≥ 50%, `churning` ≥ 30%, `thrashing` below), and the number to act on is
`excess$`: the money spent on every lap after the first, priced per turn rather
than pro-rated so a loop with cheap rework turns is not overcharged.

`excess$` is what the harness billed, so a backend under subscription auth — every
opencode turn reports a literal `$0` — leaves it empty and sorts its worst loop to
the bottom as the cheap one. The note under the table says so, and quotes the same
excess at the rate card in `groom.prices` beside the count of turns whose model that
table names. Tokens are reported even when money is not, which is what makes such a
loop rankable at all; a model with no rates is listed by `groom prices --reprice` and
wants a line in `prices.toml`.

`at-max` carries no verdict on purpose. A loop bounded by a `MAX_*` budget is
censored — work items that would have run longer stop at exactly the cap — so a
pile there is *suggestive* of a budget being exhausted rather than a gate being
satisfied. Only suggestive: a naturally long tail lands in the same place, and
this module cannot see the workflow's constants. The number is there so whoever
sees a big one goes and reads the `MAX_*`.

Work items are keyed by `(run_id, work_id)`. Story slugs repeat across runs, so
keying on the slug alone would merge one story's single pass in three runs into a
three-lap item and report a converging loop as a thrashing one. With no `--run`
the report spans every retained run, which is the useful default: one run's loop
is an anecdote, the same node over twenty is a property of the prompt.

The cost caveats from `groom cost` apply here too, and bite harder because this
report *sorts* by money — a node that churned hundreds of laps under subscription
auth reports `$0.00` of excess. Both unpriced counts are tracked (`priced_turns`,
`zero_cost_turns`), excess turns break the tie, and the CLI says so in a note.

```bash
groom loops --run RUN --json     # one run, machine-readable
groom loops --min-items 10       # only nodes with enough items to have a shape
```

## What the node actually said (`groom transcript`)

`loops` says a node re-decided the same thing eleven times. It cannot say *why*,
because the reasoning, the tool calls and the file the agent read and then ignored
are none of them telemetry — they live in the agent CLI's own session store, on
whichever host ran it, for as long as that CLI feels like keeping them.

So groom keeps its own copy. Every turn record — the transcript, the `prompt.md`
that provoked it, the `output.json` it answered with — is harvested off visible run
dirs on a tick and archived beside `groom.db`, addressed by the visit key the run
recorded in `sessions.jsonl`:

```console
$ groom transcript ls --run RUN --node plan-qa
when      visit        node                         src              size  session
14:02:11  1-37         plan-qa                      store           612K  9f2c…
14:19:40  1-44         plan-qa                      store           701K  a13b…
14:41:02  1-52         plan-qa                      tee             498K  c07e…
```

One row per lap, in the order the run took them — by the visit key rather than the
clock, so the order survives a checkpoint rewind, which a wall clock read across two
generations does not. `src` is where the copy came from and is never inferred: `store`
is the CLI's own session directory (richer — it carries attachments and the subagent
sidechains that never cross stdout), `tee` is the redacted stream capture used when
that store is not on this host, `store-backfill` came from the CLI after the fact.

```bash
groom transcript show --session SESSION   # its files on disk, and the prompt that caused it
groom transcript harvest                  # copy now, without waiting for the tick
groom transcript backfill --dry-run       # what the CLI still holds that the archive doesn't
```

`show` prints paths rather than the transcript: a record runs to tens of megabytes,
and what a reader wants from here is somewhere to point a pager or a replay.

**Runs older than the visit key are archivable too.** A `sessions.jsonl` written before
the engine stamped `generation`/`seq` names only the node and the session — and those
runs are most of the history anyone comes back to. Their turns get a key reconstructed
from the map's own order, printed as `legacy-17` so it is never mistaken for a real
`3-17`: it orders the run's turns and claims nothing more. Those rows predate the
`backend` field as well, so `backfill` asks each CLI store which of them answers to the
session id rather than dropping the turn for want of a field nobody wrote.

**Testing an improved prompt** needs the archive transposed: not one run's laps, but
every session that ever ran that node, together. `export` materializes that view into a
directory you name:

```bash
groom transcript export --by-node DIR            # everything
groom transcript export --by-node DIR --node plan-qa --workflow coder
```

```
DIR/<workflow>/<node>/<source>__<session_id>.json
DIR/INDEX.json
```

Each file is one session — `task`, `source`, `session_id`, `cwd`, `model`,
`time_created`, `n_messages`, `messages[]` — streamed a line at a time, because the
corpus does not fit in memory and neither does some of its individual sessions. `task`
is the node, taken from the index join that `sessions.jsonl` made possible, so
classification is **exact**: there is no heading regex and no unclassified bucket. The
export is a view and duplicates nothing in the archive — throw it away and take it again
after the next harvest. There is no default output directory: where a dataset lands is
the caller's decision, not groom's.

The archive rides its **own clock**. `GROOM_TRANSCRIPT_RETENTION_DAYS` defaults to
`0`, meaning keep everything, because a transcript is wanted precisely when someone
comes back to a run long after its spans aged out. `GROOM_HARVEST_EVERY_S` (default
300) is how often the tick copies; it is well under the prune interval because it is
racing a run dir's lifetime, not groom's disk budget. Harvest is idempotent on a
content digest, so a live run's growing transcript is re-copied and a finished one is
not, and scratch run dirs (`pytest-of-`, `tmpXXXXXX` under a temp root) are never
archived.

**Containers.** A container's run dir is on a volume the host cannot read, and it is
destroyed by the same event that makes anyone want it — the run ending. So the sidecar
announces (`{"type":"turn","run":…}`) whenever a turn record moves, and groom **pulls**
it over the same socket the Files panel uses. Pull, not push: a thrashing node writes
records as fast as it turns and the host is the side that has to store them. What
arrives is mirrored under `<archive>/.incoming/<container>/<run>` and then harvested
exactly as a local run dir would be, so a container's records get the archive's rules —
the visit key, the digest, what counts as a record — by construction rather than by a
second implementation. The last pull is unconditional, at the run's terminal, and drops
the mirror after it. The sidecar remains non-authoritative: if it never connects, that
container's records are absent and nothing else degrades.

## What occupied the wall clock (`groom profile`)

For one retained run, partition observed wall time and group agent work by the
workflow's attempt and verdict labels:

```bash
groom profile --run RUN
groom profile --run RUN --json
```

The time buckets are disjoint: agent turns, deterministic nodes, infrastructure,
explicit waits, gaps between resume generations, and unclassified time sum to the
reported wall clock without counting nested spans twice. Wait time is also split by
kind (`operator`, `cap`, `retry`, `reframe`, or `exec-retry`).

Attempt and verdict groups report workflow visits separately from agent turns. A visit
is one trace-scoped parent node span; every agent CLI invocation is a turn, so turns that
share a visit are backend retries rather than another pass through the workflow.
`visits/work` is therefore the convergence signal, while `backend_retries` exposes
provider or parsing instability without inflating it. Groups also report agent time,
work items, cost coverage, and tokens for each telemetry label value. `profile` reads
every retained span for the named run rather than the paginated trace search, so a long
run is not silently truncated. As with `cost`, absent and suspicious zero pricing remain
visible. Older spans without a parent id count as one visit per turn rather than being
collapsed together.

## The schema, and one footgun

Four tables — `spans`, `metrics`, `logs` and `turns` — the first three with an
`attrs_json` holding whatever OpenTelemetry attributes the producer set. `turns`
carries no bodies: it is the index over the archive above, keyed by
`(run_id, generation, seq, session_id)`.

Repo state is recorded as **observation, not assertion**. A span carries
`head_start` and `head_end`, a log record carries the `head` current when it was
emitted, and a `turns` row carries the head the turn recorded. The engine says
nothing about why the pair on a span is unequal — that is the record that
something moved `HEAD` inside it, and reading the reason is the consumer's job.
NULL means nothing observed a tree, which is not the same as an unknown hash.

**OTel attribute keys are flat strings that merely look nested.** `set_attribute`
is called with `usage.output_tokens`, and that reaches `attrs_json` as a literal
key with a dot in it — not as a nested object. So:

```sql
json_extract(attrs_json, '$.usage.output_tokens')     -- NULL, always, no error
json_extract(attrs_json, '$."usage.output_tokens"')   -- 17550
```

SQLite reads the unquoted dot as navigation into an object that is not there and
returns NULL silently. **Quote every dotted key.**

The fields most queries want dodge this entirely by being real columns on
`spans`: `duration_ms`, `total_cost_usd`, `input_tokens`, `output_tokens`,
`cache_read_tokens`, `cache_creation_tokens`, `pid`, `resume_generation`,
`head_start`, `head_end`.

`est_cost_usd` is the odd one out: derived by groom from the token columns and the
rate card rather than promoted from anything a producer reported (see `groom prices`
above), so it has no `attrs_json` to fall back to and a span only carries it once
`--reprice` has run. `priced_model` is derived the same way and names the rate that
produced the estimate — usually the model the turn reported, and for a resolved alias the
concrete id its session store named.

`resume_generation` counts how many times a run directory has been started. A
resume reuses the `run_id` and opens a fresh root span, so it is what tells a gap
between two spans apart: one that crosses a generation boundary is a
crash-and-resume, one that does not is the process waiting or thinking. They are populated at ingest
and are **nullable on purpose** — a harness that does not report cost yields NULL,
never `0.0`, because averaging a real zero together with an unknown understates
spend. Spans ingested before these columns shipped have NULL in them and are not
backfilled; `groom cost` falls back to `attrs_json`, and anything else you write
should too.

Everything else — `workhorse.node`, `backend`, `model`, `session.id`, and whatever
the workflow declared in `labels()` — stays in `attrs_json`. Adding a column means
editing both `_SCHEMA` and `_ADDED_SPAN_COLUMNS` in `groom/store.py`: the first
only runs on a fresh database, so a column added there alone never appears on a
`groom.db` that already exists.

## Querying it yourself

There is no privileged view: the dashboard, `groom status`, and any agent all
read the same SQLite file, so `sqlite3` answers anything the CLI doesn't.

```bash
sqlite3 -header "$(uv run groom db-path)" "
  SELECT node, ROUND(end_ts - start_ts, 1) AS secs, status
  FROM spans WHERE run_id = 'RUN' ORDER BY start_ts DESC LIMIT 20;"
```

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

The last one is why this stays local: `run_dir` is a resource attribute on every
span, so a query hands you the path to the prompt and outputs on disk — a join a
hosted trace backend cannot make.

For the full design, see `docs/features/groom/` at the repo root — groom's own OKF book,
queryable with `ostler graph --surface groom`.
