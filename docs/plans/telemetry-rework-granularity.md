---
type: feature
slug: telemetry-rework-granularity
title: Finer-grained telemetry for rework loops, verdicts, cost and wait time
status: proposed
---

> Related: [workhorse-otel.md](workhorse-otel.md) (the three-plane span/metric/log
> architecture this plan extends), [groom-json-first-reshape.md](groom-json-first-reshape.md)
> (groom's dashboard layer).

Status: 2026-08-05 proposed, not started. Revised 2026-08-05 against a real collector
database (see *Evidence* below), which changed three of the original design choices and
added four items the first draft missed.

## Context (read first — this plan assumes no prior conversation)

Repo: `/mnt/data/workspace/stablemate` — a `uv` workspace monorepo. `workhorse` drives an
agent CLI through a checkpointed Python state machine (a *workflow*); `groom` is the OTLP
collector + dashboard that persists what workhorse emits into a SQLite store
(`groom/groom/store.py`); a workflow like `coder`
(`workflows/src/workhorse_workflows/coder/`) is built from sub-flows (`dev`, `qa`,
`review`, `docs`), each a `Workflow` subclass whose states call `self.agent(...)` for an
agent-CLI turn or `self.call(...)` for an in-process node function.

Read `docs/plans/workhorse-otel.md` before starting. Note it has drifted: it references
`runner/script.py`, `InProcessScriptRunner` and `SubprocessScriptRunner`, none of which
exist, and cites line numbers in the retired YAML engine's `main.py`/`agent.py`. The live
instrumentation is `workhorse/otel.py`, `pyflow/run.py`, `runner/ladder.py` and
`runner/process.py`.

**The goal of this plan is not telemetry for its own sake.** It is to make two questions
cheap to answer on any run: *where does the money go*, and *which loop is spending it on
rework*. Everything below is justified by whether it moves one of those.

## Evidence: what a real run actually shows

Queried against a production collector DB (`~/.local/share/groom/groom.db`, 9 625 spans,
2 211 966 metric points). One `coder` run, 514 agent turns, **$830.23**, 3 032 agent-minutes,
105.6 wall-hours, 19 stories.

Cost by node, as a share of that run's agent spend:

| bucket | nodes | cost | share |
| --- | --- | --- | --- |
| QA **planning / reviewing / auditing** | `plan-qa`, `review-qa-plan`, `audit-qa` | $304 | **36.7%** |
| Documentation | `document-story`, `review-story-documentation` | $200 | 24.1% |
| **Editing product code** | `implement-plan`, `apply-review`, `apply-qa-fixes` | $126 | **15.2%** |
| QA **actually running** | `qa-story` | $40 | 4.8% |

Deciding *how* to test costs **7.6×** what running the tests costs. Rework is concentrated
in exactly those nodes — turns per story:

| node | turns/story | worst single story |
| --- | --- | --- |
| `document-story` | 4.68 | 10 |
| `plan-qa` | 4.61 | 10 |
| `review-story-documentation` | 3.47 | 6 |
| `review-qa-plan` | 3.17 | 6 |
| `implement-plan` | 1.21 | — |
| `plan-story` | 1.16 | — |

That shape is what the budget structure permits: `Qa` alone allows
`MAX_PLAN_REWORKS` (3) + `MAX_PLAN_VALIDATION_REWORKS` (3) + `MAX_PLAN_REVIEW_REWORKS` (3)
= up to nine plan-repair passes before give-up, and `Docs` allows `MAX_REWORKS` (3) +
`MAX_REVIEW_REWORKS` (3). **Whether those budgets are earning their keep is precisely what
today's telemetry cannot say**, because no span records which attempt it was or what the
gate decided.

Two more facts from the same DB:

- **52% of wall-clock is not agent compute.** 105.6 wall-hours against 50.5 agent-hours;
  41.7 of the missing hours sit in 11 gaps of >5 min between consecutive turns. Today a
  crash-and-resume gap, an `Await` on an operator, and an infra stall are indistinguishable.
- **The metrics table is 95% liveness noise.** `workhorse.run.heartbeat` alone is
  1 773 193 of 2 211 966 rows — 1 230 661 of them from that single run — because
  `_beat_once` (`otel.py:824-834`) ticks every 10s and the collector stores every point
  forever inside the retention window. This is what makes `groom.db` 440 MB.

### The verdicts exist, but only as prose

Deterministic gate outcomes are recoverable *only* by `LIKE`-matching log bodies —
`qa validate … returned status=invalid` (10 in that run), `story documentation invalid: N
changed production symbol(s) are not directly grounded` (17), `ostler qa run … status=failed`
(10). The **agent** gate verdicts — `QaPlanReview.disposition`, `QaAssessment.disposition`
and `.failure_class`, `QaAudit.verdict` and `.refutation_class`,
`DocumentationReview.status` — are not even in the logs. They are consumed by branching and
discarded. That is 140 turns in this one run whose outcome is unrecorded.

## Design

### 1. Rework counters as span labels — via state params, not a stashed attribute

**The original draft proposed stashing `self._loop = loop` at the top of each of `Qa`'s ~25
states purely for `labels()` to read. Do not do that.** It is 25 edit sites in one sub-flow,
each of which is silently wrong if forgotten, and it introduces mutable instance state that
exists only for instrumentation.

The counters are already where they need to be. **58 states across the five flows take their
rework counter as an ordinary state parameter** (32 of them as the `QaLoop`), and the driver
binds them two lines before it computes labels:

```python
# workhorse/pyflow/driver.py
279:        kwargs = coerce_params(bound, params, state=spec.name)
280:
281:        activity.rebase({**env.labels, **_labels(wf, env.log)})
...
306:        outcome = bound(**kwargs)
```

So the seam is: **pass the state's bound parameters to `labels()`**. In
`driver.py::_labels` (`:348-356`), inspect the override's signature and call it with the
params when it accepts them, keeping the zero-arg form working:

```python
def _labels(wf: Workflow, log: logging.Logger, params: dict[str, Any]) -> dict[str, str]:
    try:
        declared = wf.labels(params) if _takes_params(wf.labels) else wf.labels()
    except Exception as exc:  # noqa: BLE001 — instrumentation must not fail a run
        log.debug("[workhorse] labels() raised: %s", exc)
        return {}
    return {str(k): str(v) for k, v in (declared or {}).items() if v not in (None, "")}
```

Signature-driven binding is already this module's idiom (`coerce_params`, `:83-101`), so
this is not a new concept. `Workflow.labels` (`pyflow/workflow.py:199-204`) gains the
documented optional parameter; every existing override keeps working unchanged.

This stays **workflow-agnostic** per `workhorse/CLAUDE.md`: workhorse hands over the params
it already holds and never learns what is in them. The workflow decides what is a dimension.

`Qa` then needs exactly one new method body, not 25 stashes:

```python
def labels(self, params: dict[str, Any]) -> dict[str, str]:
    labels = {"work_id": self.ctx.story_slug} if self.ctx.story_slug else {}
    loop = params.get("loop")
    if isinstance(loop, QaLoop):
        labels |= {
            "qa.plan_rework": str(loop.plan_rework),
            "qa.plan_validation_rework": str(loop.plan_validation_rework),
            "qa.plan_review_rework": str(loop.plan_review_rework),
            "qa.qa_rework": str(loop.qa_rework),
            "qa.context_rework": str(loop.context_rework),
            "qa.setup_rework": str(loop.setup_rework),
            "qa.regression_fix": str(loop.regression_fix),
        }
    return labels
```

Because it is one mechanism rather than a per-state convention, phase 4 of the original
plan (copy the pattern to `dev` and `docs`) collapses into the same change: `Dev` reads
`plan_rework`/`lint_rework`/`reuse_rework`, `Docs` reads `rework`/`review_rework`, `Review`
reads `review_rework`, `Coder` reads `ci_rework`/`merge_rework`/`zero_diff` — all already
state params.

**Why a label and not a one-off attribute:** a label is stamped on every span opened while
it is current (`otel.py:857` for node spans, `:955` for turn spans), so a query groups by
attempt number without joining to a separate table.

Cardinality is bounded — each counter maxes at its `ClassVar` budget (2 or 3).

### 2. Verdicts — put them on the loop, which is already the carrier

The original draft proposed a second stashed attribute (`self._verdict`). Unnecessary for
the same reason: `QaLoop` is already the object every gate writes its outcome into
(`_finding()` at `qa/flow.py:111` stores gate notes; `assess` stores `failure_class`;
`with_qa()` carries the running `QaResult`). It is threaded through every transition and,
after §1, is already visible to `labels()`.

What is missing is that the *discrete* verdicts are computed and dropped. Add them as
fields on `QaLoop` (`shared/schemas/qa.py:369-375` region) beside the counters:

```python
#: The last discrete verdict from each agent gate — carried for telemetry and for the
#: give-up record, never branched on (each gate branches on its own fresh result).
plan_review_disposition: str = ""      # approved | revise
assessment_disposition: str = ""       # confirmed | repair_plan | extend_plan | repair_setup
audit_verdict: str = ""                # stands | refuted
audit_refutation_class: str = ""       # none | product-contradiction | plan-defect | evidence-defect
```

Each is set where the gate already branches (`review_plan` `:344`, `assess` `:412`, `audit`
`:489`) using the existing `loop.update(...)`. They then reach spans through §1's `labels()`
with no new mechanism, no new otel API, and no `self._verdict`.

This preserves the original's semantics — the verdict labels the spans *after* the turn that
produced it, which is what "time spent downstream of a `revise`" needs — while also making
the verdict durable in the checkpoint, so a resumed run and the `qa.md` give-up record can
both see it. The `record_event`-based alternative in the first draft is dropped; it needed
new API surface to be strictly worse.

`Docs` gets the same treatment for `DocumentationReview.status` (approved | revise | blocked),
which is the gate behind the 3.47 turns/story on `review-story-documentation`.

### 3. Fix the `attrs_json` flattened-key footgun, and promote the query columns

`groom/groom/store.py` stores OTel attributes verbatim (`store.py:153`,
`json.dumps(s.get("attrs") or {})`). OTel's attribute model is a flat `dict[str, ...]` with
dotted-looking keys, so `usage.output_tokens` is written as a **literal dotted key**.
`json_extract(attrs_json,'$.usage.output_tokens')` therefore returns `NULL` silently —
only `'$."usage.output_tokens"'` works. `groom/README.md:216-247` demonstrates the broken
unquoted form.

Promote the fields every cost query wants to real nullable columns on `spans`:
`duration_ms INTEGER`, `total_cost_usd REAL`, `input_tokens INTEGER`, `output_tokens INTEGER`,
`cache_read_tokens INTEGER`, `cache_creation_tokens INTEGER`, and `pid INTEGER`.

Two things the first draft got wrong or missed:

- **There are two places to edit, not one.** `_SCHEMA` (`store.py:45-60`) is only executed
  on a fresh DB. An existing DB is migrated by the hand-maintained tuple
  `_ADDED_SPAN_COLUMNS` (`store.py:104`), applied by `_migrate` (`:107-111`). A column
  added to `_SCHEMA` alone never appears on any existing collector database. Add to both.
- **`pid` is already being parsed and thrown away.** `otlp.parse_traces` produces `pid` and
  `workspace` (`otlp.py:106-107`) but `spans` has no column for either, so the insert
  (`store.py:143-157`) silently drops them. Promoting `pid` is therefore most of §5 for free.

Additive nullable columns; existing rows keep `NULL`; `RETENTION_DAYS` (14) ages them out.
No backfill. Document the convention — which fields are columns, which stay in `attrs_json`,
and the quoting rule for the latter — in a new schema section in `groom/README.md`.

### 4. Make groom actually aggregate cost (new — the first draft's gap)

Promoting columns is necessary but **not sufficient**, and this is the item that most
directly serves the plan's stated goal. There is no cost or token aggregation anywhere in
groom today: the only span aggregate that exists is `run_summaries` (`store.py:300-332`),
which computes `COUNT(*)` and `SUM(status='ERROR')`. Nothing in `groom/*.py`, `dashboard.js`
or `dashboard.html` reads `total_cost_usd` or any token field. The README's "Querying it
yourself" section is the entire cost story, and its example query is broken.

So without this item, §3 only makes hand-written SQL less error-prone — the tables in the
*Evidence* section above still have to be produced by hand every time.

Add `store.node_costs(run_id, ...)` returning per-node `turns / cost / minutes / share /
turns-per-work_id`, and expose it as `groom cost [--run ID]` (the CLI has no span-reading
command at all today — `cli.py` covers `status`, `logs`, `db-path`, `purge-tests`). Once §1
and §2 land, add `--by-attempt` and `--by-verdict` groupings, which is the payoff: *cost of
the third `plan-qa` attempt*, *minutes downstream of a `revise` disposition*.

### 5. Error classes and the dropped `error` phase (new)

"Rework rate" is half of what this plan is for, and today the *failure* half is unmeasurable:

- **The exception type is never stamped.** `ladder.py:428` and `run.py:204/227/239` carry
  only `str(exc)`. `BackendInvocationError`, `OutputParseError`, `RunBudgetExceeded` and
  `WorkflowFailed` are indistinguishable in the store, as are the `transient` / `overflow` /
  cap discriminators the ladder itself branches on at `ladder.py:264-303`. Stamp
  `error.class` (the exception type name) and `error.kind`
  (`transient|overflow|cap|parse|fatal`) on the turn span and the root span.
- **The node `error` phase is silently discarded.** `ArtifactWriter.record_interrupt`
  writes `phase="error"` (`artifacts.py:385`) and `_append_event` forwards it to
  `otel.record_event` (`artifacts.py:276`), but `record_event` (`otel.py:844-878`) has
  branches for `enter`, `done` and `terminal` only. A run interrupted mid-node leaves the
  node span swept as `"never completed"` with no cause. Add the `error` branch.
- **Node-call retries are invisible.** `pyflow/engine.py:287-294` retries a failing
  `self.call` node and only `log.warning`s it. Emit the existing `turn_event` shape.

### 6. Separate infra-wait from agent-compute time

Not every node span is agent work: `qa/flow.py`'s `stack` state (`:352`) calls
`ensure_stack` via `self.call`, opening a node span with no `agent_turn` child, and a real
run showed multi-minute stack boots (`booting app: … waiting up to 2400s`). Today that is
indistinguishable in an aggregate-by-node query from a node that waited on nothing.

Declare it in the workflow, not by a workhorse heuristic — per `workhorse/CLAUDE.md`,
workhorse must never infer what a node *means*. A `ClassVar` set on the `Workflow` subclass
(`Qa.INFRA_NODES = {ensure_stack, teardown_stack}`) surfaces as a `workhorse.span_kind`
label at the node-span open in `record_event` (`otel.py:850-860`).

### 7. Resume-generation and process tagging on the run

A run's root span is opened fresh on every `--resume-run` (`otel.py:772-774`, from
`pyflow/run.py:173-174`), and **`resume` is recorded nowhere**: `run.py:164` computes
`verb = "resuming" if resume else "starting"` and only `print()`s it. So the 41.7 hours of
gaps measured above cannot be attributed.

`process.pid` is *already* a resource attribute (`otel.py:429`) — §3 makes it queryable by
adding the column. Add `workhorse.resume_generation`, an integer read-incremented-written
in `<run_dir>/resume_generation` (mirroring how `sessions.jsonl` persists per-run state next
to the checkpoint), as a resource attribute beside it. A gap that crosses a generation
boundary is a crash-resume; one that does not is an `Await` or genuine think time.

### 8. Stop the metrics table from being 95% heartbeat (new)

1.77 M of 2.21 M metric rows are `workhorse.run.heartbeat`, 1.23 M from one run. The point
of that metric is liveness — "is the process alive *now*" — and `store.live_status`
(`store.py:352-427`) only ever reads the **latest** point per `(run_id, name)` via
`ROW_NUMBER() … ORDER BY ts DESC`. Every older row is written, indexed, retained for 14
days, and never read.

Options, cheapest first: give the pure-liveness metrics a much shorter retention than
`RETENTION_DAYS` in `prune()` (`store.py:555-572`); or upsert-on-`(run_id, name, attrs)`
instead of appending, since only the last value is ever read. Either turns a 440 MB
database back into a small one. This is independent of everything else here and needs no
workhorse change.

While there: `workhorse.gas`, `workhorse.gas.capacity` and `workhorse.gas.refuels`
(`otel.py:719-727`) have **no production callers** — the gas tank belonged to the retired
YAML engine. Delete the instruments or wire them to the pyflow budgets.

### 9. Per-tool-call sub-spans

Unchanged from the first draft, and still last. Backend-dependent (each adapter parses a
different wire format), the most invasive change here, and it should be scoped against what
§1-§8 fail to answer rather than spec'd blind. `TurnUsage` (`runner/usage.py:95-165`) has no
tool-call field today.

## Phasing

Each phase is independently useful and independently shippable.

0. **Un-dark groom's telemetry tests.** `groom/tests/test_telemetry.py` (1 043 lines — the
   primary ingest/store suite) is the only file in `groom/tests/` with no
   `if __name__ == "__main__"` block, and `groom/Makefile:47-49` runs each test file as a
   plain script. It therefore executes **zero tests** and exits 0. Fix before writing any
   store test, or the new tests are dark too.
1. **§3 schema columns + §4 `groom cost`.** Zero workflow changes; makes the *Evidence*
   tables above reproducible with one command instead of hand-written SQL.
2. **§8 metrics retention.** Independent, groom-only, largest immediate resource win.
3. **§1 params-to-`labels()`** in workhorse, plus the `labels()` override in all five
   sub-flows at once (one mechanism, so there is no reason to stage it per flow).
4. **§2 verdict fields** on `QaLoop` and the `Docs` equivalent.
5. **§5 error classes** and the `error`-phase branch.
6. **§7 resume generation**; **§6 infra-wait**. Both independent.
7. **§9 per-tool-call spans**, only if a gap remains.

## Files

**groom** (`groom/`):
- `groom/store.py` — `_SCHEMA` (`:45-60`) **and** `_ADDED_SPAN_COLUMNS` (`:104`) get the new
  columns; the insert (`:143-157`) extracts them before writing `attrs_json`; new
  `node_costs()` aggregate; `prune()` (`:555-572`) gains per-metric retention.
- `groom/cli.py` — new `cost` command (no span-reading command exists today).
- `groom/README.md` — new schema section: which fields are columns, which stay in
  `attrs_json`, and the `'$."dotted.key"'` quoting rule. Fix the broken example at `:216-247`.
- `groom/tests/test_telemetry.py` — add the `__main__` block first; then the round-trip test
  asserting `usage.output_tokens` lands in the promoted column.

**workhorse** (`workhorse/`):
- `workhorse/pyflow/driver.py` — `_labels` (`:348-356`) gains the params argument and the
  arity check; call site at `:281`.
- `workhorse/pyflow/workflow.py` — `labels()` (`:199-204`) documents the optional parameter.
- `workhorse/otel.py` — `record_event` (`:844-878`) gains the `error` branch and the
  `span_kind` label; `resume_generation` resource attribute (`:419-443`).
- `workhorse/runner/ladder.py` — stamp `error.class` / `error.kind` (`:264-303`, `:428`).
- `workhorse/pyflow/run.py` — pass `resume` through to `start_run` (`:164`, `:173-174`).
- `workhorse/tests/test_otel.py`, `tests/test_activity.py` — extend; the fakes and
  `installed()` / `_gate()` helpers are already there.

**workflows** (`workflows/src/workhorse_workflows/coder/`):
- `qa/flow.py` — `labels()` (`:186-188`) reads `params["loop"]`; the three gates
  (`:344`, `:412`, `:489`) record their verdict via `loop.update(...)`; `INFRA_NODES`.
- `dev/flow.py` (`:154`), `docs/flow.py` (`:102`), `review/flow.py` (`:123`),
  `workflow.py` (`:188-204`) — the same `labels(params)` override.
- `shared/schemas/qa.py` — the four verdict fields on `QaLoop`; `shared/schemas/docs.py`
  equivalent.
- `workflows/tests/coder/qa/test_flow.py` — the `_Agent` harness (`:341-470`) already scripts
  every branch axis, so a rework-label assertion slots into the existing give-up tests
  (`:825`, `:1137`).

## Verification

- **Phase 0:** `cd groom && make test` names `test_telemetry.py` and reports real test counts.
- **Phase 1:** round-trip test through the promoted columns; `groom cost --run <id>`
  reproduces the *Evidence* cost-by-node table.
- **Phase 2:** metric row count for a fresh run stays flat over hours instead of growing at
  ~6/min/node.
- **Phases 3-4:** a `Qa` unit test driving two `plan` reworks via the existing fake-agent
  harness, asserting `labels()` reports `qa.plan_rework` at each transition and the verdict
  key after `review_plan`. Cross-check that no existing zero-arg `labels()` override broke.
- **Phase 5:** a test asserting an `OutputParseError` turn carries `error.kind="parse"`.
- **Phases 6-7:** as the first draft (`INFRA_NODES` labelling; resume increments the
  generation), using `FakeClock` / `RecordingTelemetry` from `workhorse/tests/_fakes.py`.
- **End-to-end:** after phases 1-4, on a real `coder` run with at least one QA-plan rework,
  `SELECT node, json_extract(attrs_json,'$."qa.plan_rework"'), duration_ms, total_cost_usd
  FROM spans WHERE run_id=? AND node LIKE 'qa%' ORDER BY start_ts` returns attempt number
  and cost in one row.
- `make lint`, `make check-public`, `make check-no-env`, `make test` from the repo root —
  this plan touches `groom`, `workhorse` and `workflows`.

## What this is expected to reveal

Stated as falsifiable predictions, so landing the plan either confirms or kills them:

1. **The QA planning apparatus costs more than it saves.** It is 36.7% of spend against
   4.8% for running the plan it produces. §1+§2+§4 give cost-per-verdict: if most
   `review-qa-plan` turns end `approved`, the gate is a toll rather than a filter and its
   budget should shrink.
2. **The nine-pass plan-repair budget is the direct cause of `plan-qa`'s 4.61 turns/story.**
   §1 shows the attempt distribution; if the mass is at attempts 4+ and those stories still
   pass, the three separate budgets should be one smaller one.
3. **`review-story-documentation` at `power="high"` re-runs `document-story` at
   `power="medium"` 3.47 times per story** — an expensive judge repeatedly rejecting a
   cheaper author. §2's disposition labels show whether raising the author's power once is
   cheaper than three rejections.
4. **Most of the 52% non-compute wall-clock is crash-resume, not operator waits.** §7
   settles it, and it is a different fix (checkpoint durability) from the one a plan-budget
   change would make.
