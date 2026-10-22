# Run facts: what a run says about itself

> **Disclosure.** I read the existing solution before this design started. That covers the
> workhorse telemetry host and its node, turn and wait spans, the engine's `agent`, `call`
> and `handoff` paths, the artifact writer, groom's store, its archive and its `cost`,
> `loops` and `profile` queries, coder's main, dev, docs and QA flows and their labels, the
> ostler QA artifact kinds, and the turns and spec folder of one live coder run on a client
> epic. The [story throughput](story-throughput.md) note already counts per-story hours by
> hand. Each decision that reached me from the brief is a claim in section 1b.

## 1. Problem

**Who feels it.** The operator who hands a 17-story epic to coder and holds each story to 4
hours of active time. To learn whether a story met that bar, they read `worklist.json`, count
turn folders by node, open each QA report and sum hours from the dashboard. That takes an
afternoon per epic and the counts drift from what the run did. An agent asked the same
question does the same reading and makes the same mistakes. Once groom archives a run, no
query command answers it at all: `cost`, `loops` and `profile` read SQLite only, and
archiving deletes the run's rows. The archive answers through `groom archive show`, a raw
stream of up to 160 MB.

**Done looks like this.**

- One command answers, per story of a coder run: active hours, laps per lane, failed QA
  runs, findings by disposition, operator gates with their outcome, and cost.
- The same command gives the same answer for a live run, a finished run and an archived run.
  The live answer includes the visit that is still running.
- groom's source holds none of the words story, QA, finding or lane.
- Another workflow gets the same breakdown by its own label with no groom change and no
  engine change.
- A fact that names a spec-folder file still resolves after the next QA run overwrites that
  file.

**Out of scope.**

- Alerting on facts, such as paging when a story passes 4 hours. The rules engine can read
  the same rows later.
- Retiring the `_verdict` suffix heuristic in `profile`. The output stamp makes it redundant,
  and its removal is a separate change.
- The dashboard's double-counted session totals described in the throughput note. This note
  prices turns the way `groom cost` already does.

## 1b. Claims

1. "groom stays general." It never learns coder's concepts.
2. A run records facts through telemetry. Logs, span attributes, span events and metrics are
   all allowed.
3. An agent and the groom view query that telemetry for live and archived runs alike.
4. A turn's `output.json` is a prime source, and the engine stamps it with no workflow code.
5. Spec-folder artifacts are a second source. A fact points at them for ostler to parse and
   does not copy their content.
6. Coder is the first consumer, and its question is the acceptance test.

## 2. Parts

| Part | Owner | What it does |
| ---- | ----- | ------------ |
| Output stamp | workhorse engine | Puts an output's scalars and list sizes on the visit span that produced it. |
| Fact | workhorse engine, called by a flow | A statement about a subject, emitted as one OTLP log record. |
| Ref | workhorse engine, called by a flow | A file a fact names: path, digest, size and ostler kind. |
| Run index | groom | The same SQLite schema over a live run's rows or over one archive. |
| Breakdown | groom | `groom profile RUN --by <label>`: one row per label value. |
| Coder's emits | coder | A `story` label on every lane, and one `story.done` fact per story. |

Two kinds of record carry everything. A **visit** happens many times, and the output stamp
records each one. A **fact** states where a subject stands, and a later fact with the same name
and subject replaces the earlier one. A failed QA run is a visit. A story's findings by
disposition are a fact. The split keeps each number in one place.

## 3. The output stamp (point 1)

**Where.** The engine stamps the node visit span, not the `agent_turn` span. A visit can run
several turns through retries, and only the last one produces the output. A `call` or a
`handoff` has no turn span, and `run_qa_plan`, the deterministic node that says whether a QA
run failed, is a `call`. The visit span is open when `write_step` writes `output.json` and
closes on the `done` event right after. `record_event` passes `end_attributes` to
`_end_execution` at that point, the way `wait_end` already does. groom joins turn spans to
their visit by `parent_id` already, so a turn-level query loses nothing.

**What.** The stamp reads the payload `write_step` writes, a plain JSON object, and knows no
schema:

| Output field | Span attribute | Example from a QA visit |
| ------------ | -------------- | ----------------------- |
| string up to 128 chars | `workhorse.out.<field>` | `workhorse.out.status = "findings"` |
| int, float, bool | `workhorse.out.<field>` | `workhorse.out.docs_recheck_required = true` |
| list | `workhorse.out.<field>.len` | `workhorse.out.findings.len = 3` |
| longer string, object, null | nothing | `notes` is prose and stays in `output.json` |

- The stamp writes at most 32 keys per visit, in field order. The OTel SDK's default limit is
  128 attributes per span, and a node span carries about 15 today.
- A `call` that returns a bare value is recorded as `{"value": ...}`, so it stamps
  `workhorse.out.value`.
- The stamp never fails a run. A payload it cannot read stamps nothing and logs at debug
  level.
- The `workhorse.` prefix keeps the stamp out of `profile`'s attempt groups, which skip that
  prefix already.

On the sample run, the stamp gives these without any coder code: every `run_qa_plan` visit
with its `status`, every `qa-story` visit with `status` and `findings.len`, every `dev-story`
visit with `status`, `findings.len` and `follow_ups.len`, and every QA handoff with the QA
flow's `status` and `findings.len`.

## 4. The fact (point 2)

**Call site.** A flow states a fact from any state:

```python
self.fact(
    "story.done",
    subject=item.id,
    findings={"settled": 16, "declined": 5, "merged": 3},
    follow_ups=4,
    claims=item.laps,
    revision=sha,
    refs={"qa_report": spec / "qa-report.md", "qa_evidence": spec / "qa-evidence.json"},
)
```

**Transport: one OTLP log record.** The record's `event.name` attribute is the fact's name,
following OTel's convention for events carried as logs. Its attributes are:

- `fact.subject`, the subject string.
- `fact.<key>` for each scalar field, and `fact.<key>.<inner>` for one level of nesting.
- `ref.<name>.path`, `ref.<name>.sha256`, `ref.<name>.bytes` and `ref.<name>.kind` for each
  ref.
- every current run label, raw and unprefixed, the way spans carry them, plus `node`.

A log record wins over the two other carriers:

- **A span event** reaches groom only when its span ends. On the root span that is the end of
  the run. On a node span it is the end of a visit that can last hours. A run that dies loses
  its buffered spans with it. The live view needs the fact when it happens.
- **A metric** carries a number per series and no identity per occurrence. A story fact has
  several measures and refs. One series per story id would also grow the metric table, and the
  archive keeps only four budget series.

A log record goes out within seconds through the existing batch processor. groom stores it in
the `logs` table, which the archive keeps whole. Today log records carry `node` but no labels,
so the engine stamps the labels on fact records itself.

**Semantics.**

- The key is `(event.name, fact.subject)`. A reader takes the latest record per key. A
  resumed run that replays the state which emitted a fact therefore does no harm. A story that
  reopens and commits again replaces its first fact.
- Values are str, int, float and bool. A bad field is dropped with a debug log. A fact never
  fails a run.
- A flow states facts only for what telemetry cannot derive. Time, cost, visits per node and
  gates come from spans, and the fact does not repeat them.

That last rule departs from the brief's example, which put active minutes and laps per lane in
the "story committed" fact. groom derives both from spans: active time from the disjoint sweep
`profile` already runs, and laps per lane from visits per handoff node. A flow that timed itself
would miscount across reload cuts and resume gaps, which the spans already record. The fact
carries what only the flow knows: findings by disposition from the work list, follow-ups filed,
the commit revision, the work list's own claim count and the refs.

## 5. Refs to spec-folder files (point 3)

The QA run overwrites `qa-report.md` and `qa-evidence.json` each time. A path alone points at
the latest run's file, which can belong to a later QA run than the fact describes.

- **At emit**, the engine reads each ref's file once and stamps its path, sha256 and size. The
  flow names the ostler kind: `qa-evidence` is an ostler artifact kind today, and
  `qa-report` names the report ostler reads through `REPORT_FILE`. The engine does not parse
  the file.
- **At harvest**, groom copies each referenced file into `<data dir>/blobs/<sha256>`, once per
  digest, the way it harvests transcripts beside the turn archive. A QA file is a few kB, so a
  17-story epic adds well under a megabyte.
- **At archive**, the run's referenced blobs move with its turn archive.
- **At read**, `groom profile RUN --facts --json` returns each ref with its path, digest, kind
  and the local blob path. An agent hands the blob path to ostler. groom never opens the file.
- A ref whose file was missing at emit carries `bytes = 0` and no digest. A blob that harvest
  could not copy reads as `blob: null`, and the original path still stands.

The fact carries the few scalars the breakdown shows, such as assertions failed on the last
QA run. Coder has those in its `QaPlanRun` result already and passes them as fields. Anything
deeper stays in the file, for ostler.

## 6. groom's query surface (point 4)

**One command.** `groom profile RUN --by <label>` returns one row per value of that label.
Without `--by` it behaves as today. Each row holds:

| Column | Source |
| ------ | ------ |
| `active_s`, `wait_s` by wait kind, `resume_s` | profile's disjoint sweep, restricted to spans carrying that label value |
| `cost_usd`, `turns`, `output_tokens` | `agent_turn` spans, priced as `groom cost` prices them |
| `visits` per node | node visit spans |
| `out` per node | for each `workhorse.out.<field>`: counts per value for strings and bools, sums for numbers and `.len` |
| `waits` | each wait span: kind, gate path and outcome |
| `facts` | the latest fact per `(event.name, fact.subject)` whose label matches, with its refs |

groom does not know that `run_qa_plan` is a QA run or that `findings.len` counts findings. It
reports `out.run_qa_plan.status = {passed: 3, failed: 2}`, and the reader brings the meaning.
`--by` takes any label the run carries, so a book run can break down by its page label the
same way.

**Live, finished and archived runs share one path.** The breakdown is a function of a SQLite
connection and a run id.

- A live or recent run reads `groom.db`.
- An archived run reads `<archive>/telemetry.db`, a SQLite file with groom's schema that groom
  builds from `telemetry.jsonl` on the first query and reads after that. The jsonl file stays
  the source. Deleting the index costs one rebuild.
- `cost`, `loops` and `profile` all move onto that connection, so every existing query answers
  for an archived run too.

**The visit still running.** Spans export when they close, so a live story's open visit is
missing from SQL. The breakdown adds the open visit's elapsed time from groom's live state,
which the liveness gauges feed. Today those gauges carry `node`, `activity` and `work_id`
only. They carry every run label instead, so the open visit lands in the right row for any
`--by`. The CLI asks the serving groom for the live part, the way `groom status` does, and
says when it answers from SQL alone.

**The view.** The run page gets a "group by" control listing the run's label keys and renders
the same rows. An agent reads `--json`.

## 7. What coder emits (point 5)

1. **A `story` label on every lane.** A child flow's labels replace its parent's, and the
   fix and CI-fix flows declare none. Their spans carry no work id today, so their time
   falls outside every story. Dev's `work_id` is a finding id such as `<story>/qa-1.1` while
   it fixes, so a breakdown by `work_id` splits a story's fix time across its findings. Main,
   dev, docs, QA and both fix flows add `story`. A label is the only dimension groom groups
   by, so the join stays in coder.
2. **No stamp code.** The output stamp covers every visit: `run_qa_plan` status, QA findings
   counts, dev and docs status, and the handoffs' results.
3. **One fact per story**, `story.done`, emitted in `standing` after the work list marks the
   story done. Its fields are findings by disposition, follow-ups filed, the work list's claim
   count, the commit revision, the last QA run's assertions passed and failed, and refs to
   `qa-report.md` and `qa-evidence.json`.

**The acceptance test.** On a coder run started after these slices, `groom profile RUN --by
story --json` answers the operator's question per story:

| The operator asks | The row answers with |
| ----------------- | -------------------- |
| active hours | `active_s` |
| laps per lane | `visits` on the `dev`, `docs`, `qa` and `fix` handoff nodes |
| failed QA runs | `out.run_qa_plan.status.failed` |
| findings | `out.qa-story.findings.len`, and `facts.story.done.findings.*` by disposition |
| gates | `waits`, with outcome |
| cost | `cost_usd` |

The same command answers again after `groom archive now` freezes the run. Each number matches
a count taken from that run's `worklist.json`, its `turns/` folders and its spec folder by
hand, for every done story.

## 8. Invariants

- groom's source holds no workflow vocabulary. A breakdown names only labels, nodes and
  output fields the run sent.
- The engine's stamp and fact path hold no workflow schema. A different workflow would want
  both unchanged.
- Neither the stamp nor a fact can fail a run.
- A fact never repeats what spans derive.
- `telemetry.jsonl` stays an archive's source of truth. The index beside it is derived.

## 9. Slices

1. **Output stamp.** The engine stamps visit spans. groom stores the keys in `attrs_json`
   with no schema change. Tests: an engine test with a recording telemetry for `agent`, `call`
   and `handoff`, and a groom ingest test.
2. **Archive index.** Store queries take a connection, and an archived run opens its built
   index. `cost`, `loops` and `profile` answer for an archived run.
3. **Breakdown.** `profile --by <label>`, the liveness gauges carrying every label, and the
   view's group-by control.
4. **Facts and refs.** `Workflow.fact()`, an `event_name` column on `logs` with an index on
   `(run_id, event_name)`, blob harvest by digest, and facts in the breakdown.
5. **Coder.** The `story` label on every lane, the `story.done` fact, and the acceptance test
   on the next live epic.

Slices 1 and 2 are independent. Slice 5 needs 1, 3 and 4.

## 10. Assumptions to check

1. Building the index for the largest archive today, 160 MB of jsonl, takes under a minute
   once. Measure it in slice 2. If it takes longer, the sweep builds the index when it
   archives.
2. A replayed state on resume re-emits its fact with the same subject. Latest-wins covers that
   case. Confirm by resuming a test run mid-story.
3. The log batch processor exports a fact within a few seconds. Check its schedule delay in
   the SDK version the workspace pins.
4. ostler reads one `qa-report.md` or `qa-evidence.json` given only its path, outside a spec
   folder. If it cannot, slice 4 adds that read to ostler, since the blob copy has no spec
   folder around it.
5. A visit span's labels name the story that visit served. Coder works one story at a time.
   A workflow that runs two subjects at once still gets a correct row per subject, but the
   rows' active times then sum past the wall clock.
