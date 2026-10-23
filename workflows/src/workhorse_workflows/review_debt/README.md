# review_debt

The `review-debt` workflow. It reads the whole debt register, has one agent turn group the
records by shared cause, proves the report covers every record, writes `trends.md`, and
proposes a decision for each cluster big enough to need one.

```bash
workhorse-review-debt run
workhorse-review-debt run --dry-run   # ends at "register is empty", no agent CLI needed
```

## Map

- `workflow.py`: the `review-debt` command and its registry.
- `flow.py`: the `ReviewDebt` state machine.
- `nodes/`: `read_register`, `account`, `write_trends`, `select_candidates`,
  `narrow_candidate` and `file_decision`.
- `schemas.py`: `CompleteRead`, `TrendReport` (`Cluster`, `Singleton`), `Accounting`,
  `Candidate`, `DecisionDraft`, `Filed`, `Proposed`.
- `prompts/review-register.md`: the grouping turn.
- `prompts/draft-decision.md`: the turn that drafts one decision from one cluster.

## States

1. `start` calls `read_register`. A read with no ids ends the run as `Done` with the reason
   "register is empty": no agent turn and no `trends.md`.
2. `group` renders `review-register.md` with the listing lines and the shelf path, and
   gets a `TrendReport` back. `account` compares the ids of the report with the ids of the
   read. A passing report goes to `write_trends`, then to `plan_decisions`.
3. `plan_decisions` calls `select_candidates` with `decision_threshold` (default 3). With no
   cluster at the threshold the run ends as `Done` with an empty `Proposed`.
4. `draft` takes one candidate at a time. `narrow_candidate` re-reads the shelf and drops
   records a decision has bound since the plan. A candidate still at the threshold gets one
   `draft-decision.md` turn, and `file_decision` calls ostler's `propose_decision` with the
   draft. The run ends as `Done` with a `Proposed` that names every decision id it filed.

## Inputs

The ambient `repo_dir` and `workspace`, injected the way every workflow here gets them. The
register is the artifacts dir's shelf, resolved by ostler, never a path this package spells.

The read holds every parseable record of every status in every repository. Closed records
are in it on purpose: a dropped record whose cause recurs is a trend. A `record.md` that
does not parse is logged and carried in the read's `unreadable` list. It is never accounted
for, so the report is not asked to name it.

## The send-back cap

`account` returns the ids the report leaves out (`missing`), repeats (`duplicated`) and
invents (`unknown`). A report is ok when all three are empty. A failing report goes back to
the same turn with every such id named in the prompt's feedback block. `max_sendbacks`
(default 2) caps that: after the second send-back fails, the run raises `WorkflowFailed`
with the gap ids in its reason and writes nothing. At most three agent turns run.

## Where `trends.md` lands

`<artifacts>/backlog/trends.md`, beside the repository folders of the shelf. The file is
rendered from the passing report and the read alone: a heading, the record count, the
summary, one `##` section per cluster and a singletons section. Every id appears once as a
line starting `- <id> `. Rendering is deterministic, so a resume that renders the same text
commits nothing. The one file is committed in the artifacts repo as
`chore: review the debt register`. The shelf glob is `*/*/*/record.md`, so the file at the
shelf root is never read back as a record.

## Decisions

The evidence of a cluster is its ids whose record has an empty `decision`. A cluster whose
evidence reaches `decision_threshold` yields one `adr/<id>.md` in the artifacts dir with
`status: proposed`, the sorted `repos` of the evidence and the evidence ids. Each evidence
record gets `decision: <id>` and stays open. The adr file and the records are one artifacts
commit, `chore: propose <id> from <n> records`. A cluster below the threshold yields nothing.

A rerun or a resume over the same report proposes nothing twice. Bound records drop out of
the evidence count, so a cluster that a decision already holds falls under the threshold, and
`draft` narrows its candidate again before it spends a turn. A refusal from ostler (an
unknown id, a record bound to another decision) ends the run with `WorkflowFailed` naming it.
