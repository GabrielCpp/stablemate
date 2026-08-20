# Let every node say "not possible", and let a repair lap remember the last one

A node reaches a verdict it cannot act on, and there is no receiver for it. The flow drops
the verdict and advances; the next node starts cold with no memory that the last one already
refused. Those are not two defects. They are one defect seen from both ends — the run keeps
going because nothing caught the refusal, and it keeps going *expensively* because nothing
carries forward what the previous lap already ruled out.

Observed 2026-08-18 in an overlay coder run (`coder-qafix9`, one story, `operator_mode: auto`):

| | |
| --- | --- |
| wall clock | 14h44m, terminal `fail`, **nothing committed** |
| phase split | dev 9m (1%) · review 83m (9%) · docs 14m (2%) · **qa 12h29m (85%)** · give-up docs 29m (3%) |
| turns | 65, of which **3 were production work** (4.6%) and 37 were the QA lane (57%) |
| sessions | **60 distinct ids across 65 turns — 92% cold starts** |

The run's fourth turn, `implement-plan`, returned this at minute 9:

```json
{"status": "blocked",
 "notes": "…all 12 admitted pages failed source-fidelity assertions before publication…
           AC3 requires cross-surface schema/parser/serializer/importer/editor remediation
           and replanning; no story status line was changed."}
```

That verdict was correct and it was discarded. `_implement_classic` (`coder/dev/flow.py:636`)
calls `self.agent(...)` without assigning the result, and both of its callers unconditionally
`return Continue(None, self.lint, index=index)`. The run then spent 14h35m — 85% of it in a
QA lane testing a feature that was never implemented — before giving up.

The amnesia is what made those 14h35m cost what they did. `plan-qa` re-planned **seven** times
at ~35KB of prompt each, every one a cold context. The four chained `repair-qa-plan` turns
differed only in a lap counter (16820 / 16821 / 16822 / 16822 bytes). Five consecutive
`apply-qa-fixes` turns reported `passed` while QA never passed, one of them admitting the
"fix already present in the working tree".

Reached by [`/stablemate-grill`](../../CLAUDE.md) on 2026-08-18; nothing below is implemented.

## What already works and is not being rebuilt

The escalation machinery is present, correct, and wired at only four stage boundaries
(`dev/flow.py:243,282` — plan only; `review/flow.py:376,438`; `docs/flow.py:797`;
`qa/flow.py:1516,1857`). It is absent from implement, lint, red gate, fix and fix_ci.

- `compose_escalation` (`coder/shared/escalation.py`) rewrites `context.md` with the prior
  body truncated into it (`HISTORY_HEAD=4000` / `HISTORY_TAIL=8000`), so a re-block carries
  its own history. Escalations are **deliberately uncapped**.
- `read_operator_context` (`coder/shared/dev.py:542`) flips `ANSWERED` → `CONSUMED`, so a
  re-block re-arms instead of looping on a stale answer. `SCOPE: epic` escapes to replan.
- `Await` propagates out of a `handoff` — the child runs through the same driver
  (`pyflow/engine.py:514`), and QA's escalations already suspend the whole run from inside one.
- The **outbox** is the answer channel: `outbox_get` returns the gate the checkpoint's
  `waiting_on` names, and `outbox_post` → `_answer` → `answer_gate` writes into that file and
  flips the state (`groom/groom/app.py:574-605,879`). The **inbox** is a message log —
  `inbox reply` marks a jsonl entry answered and touches no gate (`workhorse/cli/inbox.py`).

## Settled design

- **The signal is uniform and lives on `CoderResult`.** Every agent node can raise it, not a
  curated subset. Curation is a guess about where impossibility occurs, and nobody would have
  curated `implement-plan` into the set — which is exactly where it happened.

- **`blocked` / `unfixable` / `not_passed` / `invalid` are one thing.** They are consolidated,
  not left to coexist. Today every result schema declares its own free-form `status: str` with
  its own default (`""`, `"blocked"`, `"skipped"`, `"failed"`, `"invalid"`, `"unfixable"`,
  `"not_passed"`, `"ready"`) and no shared vocabulary exists. All of them mean *hand this to
  the operator*.

- **The pessimistic self-report is believed; the optimistic one still is not.** `ImplResult`'s
  docstring — "an agent claiming `done` is not evidence that it is" — stands unchanged. The
  asymmetry is the point: a false `done` ships broken work, a false `blocked` costs one
  operator answer, and the run above cost fourteen hours for want of that answer.

- **Actionable evidence is what separates a repair lap from an escalation**, and it is tested
  mechanically: at least one **structured finding carrying a location** (file/line or spec id)
  **and a demand**. Has it → route back as a fix demand. Lacks it → operator. A non-empty
  prose list is not evidence; that is what `apply-qa-fixes` acted on seven times without
  converging.

- **The fix target is derived from the gate**, never self-nominated: review fix → dev,
  QA fail → dev, audit fail → the QA planner. A node that nominates its own target can bounce
  work indefinitely with nothing noticing the loop has no exit.

- **Repair nodes survive, but run on the operator's say-so.** `repair-qa-plan`,
  `apply-qa-fixes` and `rework_plan` are not deleted — the operator's answer can still be
  "try again, here's what you missed."

- **Escalation honours `operator_mode` exactly as today.** Auto-resolver first by default; it
  produces the `tried` list `escalation.py` calls the load-bearing one. An answer resumes **at
  the node that escalated**, with `scope: epic` still escaping to replan.

- **Session ids are captured, not generated.** Every backend mints its own and workhorse reads
  it back — `state.session_id = sid` (`runner/backends/opencode.py:44`),
  `stream.session_id` (`runner/backends/claude.py:156`) — then resumes with `--resume <sid>`
  off `session_id_path`. Only Claude Code accepts a caller-chosen `--session-id`; opencode,
  codex and copilot do not, so a workflow-generated id is not portable. The minted id is
  captured into **checkpointed workflow state** and threaded as a literal node parameter.
  This is the real fix: a `.sessions/<key>` file is *not in the checkpoint*, so a resumed run
  silently opens a fresh conversation while the flow believes it is continuing one.

- **Chains go to repair loops only.** `workhorse/sessions.py` states the reason: "A reviewer
  reading the author's reasoning is not a reviewer." A chained auditor inherits the fixer's
  rationalisations — which is how five `apply-qa-fixes` turns in a row reported `passed`.
  Structured carry-forward stays alongside as the durable record.

- **Agents commit at will; the commit gate becomes a cleanliness check.** The run asserts the
  tree is clean, subtracting what `snapshot_worktree_state` (`coder/shared/worktree.py:65`)
  recorded as dirty at story start. Dirty → re-enter the same agent, chained, once; a second
  dirty reading escalates. Only the agent that made the mess knows whether a file is finished
  work or a scratch edit.

- **There is no mechanical no-progress detector.** `zero-diff-streak` is deleted outright, not
  converted.

- **All four lanes change at once.** They share `CoderResult`, `compose_escalation` and
  `read_operator_context`; a half-converted tree means two escalation contracts coexisting,
  and the run above failed by falling through a seam *between* lanes.

### A consequence, not a decision

Groom holds at most one live gate per run ("A run has at most one live gate (the one its
checkpoint's `waiting_on` names)"). That stays correct — an `Await` suspends the run — but it
means a story with problems in three lanes surfaces them serially, across three operator
answers.

## Scope

### 1. `coder/shared/schemas/_base.py` — the consolidated signal

`CoderResult` gains the blocked signal and the evidence it may carry:

- a single blocked marker, replacing `unfixable` / `not_passed` / `invalid` / `blocked` as
  four separate spellings across seven schemas;
- `findings: list[Finding]`, where `Finding` carries a **location** (a repo-relative
  `file`/`line`, or a spec id) and a **demand** (what must change). A finding missing either
  is not evidence.

`extra="ignore"` and the `_drop_nulls` before-validator stay: the resilience ladder's soft
failure must remain soft. But the blocked marker needs a default that is distinguishable from
*a node that failed to answer at all* — today a dead node emits nulls and the run advances on
the conservative arm, and "conservative" must not silently become "blocked".

### 2. `coder/shared/escalation.py` — generalise the payload

`dev/flow.py:739 _escalation` hardcodes `block_kind="plan"` and `where="the plan stage"`.
Both become parameters supplied by the escalating node, and the helper moves out of
`dev/flow.py` into `shared/` so all four lanes call one thing. `compose_escalation`'s own
signature already takes `block_kind`, `where` and `tried` — the work is in the callers.

### 3. The four lane flows — route the signal

`coder/dev/flow.py`, `coder/review/flow.py`, `coder/docs/flow.py`, `coder/qa/flow.py`:

- **`_implement_classic` (`dev/flow.py:636`) assigns its result.** This is the root-cause line.
  Both callers branch on it instead of unconditionally continuing to `self.lint`.
- Every `self.agent(...)` whose result is currently discarded is assigned and branched.
- Each branch applies the evidence test from §1: structured findings → fix demand at the
  gate-derived target; otherwise → escalate.
- The operator answer resumes at the escalating node. `Await`'s contract requires the target
  to be a state with a cheap prefix (resume replays it from the top with no intra-state memo),
  so each escalation site needs a thin consume-the-answer state that reads everything else
  through `self.output(...)`.

### 4. `pyflow/engine.py`, `workhorse/sessions.py`, the runner backends — session memory

- The backend-minted id, currently written only to `session_id_path`, is surfaced back to the
  workflow so it can be held in checkpointed state.
- `engine.agent`'s `session:` parameter accepts a literal id in addition to today's chain key.
  The `enter` event already records `chain` / `resumed_session`; it records the threaded id on
  the same terms.
- `reset_session` (`engine.py:451`, mirrored at `workflow.py:350`) keeps working for the two
  existing chains (`qa-plan-repair:<story>`, `docs-repair:<story>`) and for the repair loops
  added here.
- Chains are added to the repair loops that currently have none — `apply-qa-fixes`,
  `rework_plan`, the `fix-*` laps — and to nothing else.

### 5. `coder/workflow.py` + `coder/shared/queue.py` — split the commit node

`workflow.py:726 commit` does three jobs and `queue.py:919 commit_story` does two more. They
separate:

| job | where it goes |
| --- | --- |
| per-repo `git commit` | the agent, at will |
| Conventional Commit subject + `Epic:`/`Story:` trailers, scoped per package | the agent's prompt (§6) |
| **story-passed stamp** | a **stamp-only node at the same graph position** |
| zero-diff guard | deleted (§7) |
| affected-repo resolution from `plan-context.json` | stays, feeding the cleanliness check |

The stamp is queue integrity, not development work: "Nothing else on the success path writes
that status, and story selection reads it, not the git log: without the stamp a story that
just passed is re-selected on the next loop iteration and its epic never reads as complete."
An agent that forgets it re-runs the story forever, and the failure is invisible until the
epic never completes.

The cleanliness check subtracts `snapshot_worktree_state`'s pre-existing dirty paths, so an
agent is never blamed for the operator's leftovers. First dirty reading re-enters the same
agent chained; second escalates.

### 6. `coder/prompts/*.md` — 16 prompts have no blocked outcome

Of 33 coder prompts, 17 mention a blocked outcome and **16 do not** — and the 16 are the ones
that churned:

```
audit-qa.md          check-code-reuse.md   code-review.md        code-reuse.md
dream-reflect.md     fix-ci.md             fix-lint.md           fix-merge.md
fix-regression.md    plan-qa.md            repair-qa-plan.md     replan-epic.md
report-qa-dev.md     report-qa-dev-pass.md review-implementation.md  triage-qa.md
```

Each gains the blocked outcome in its own return contract — **no shared preamble**; the
vocabulary belongs in the prompt's documented outcome, which is where the other 17 already
carry it. Producer prompts additionally gain the commit instruction from §5, including the
per-package scope and the `Epic:`/`Story:` trailers.

### 7. `scripts/check_no_giveup.py` + the three unmigrated exits

AGENTS.md already names these as give-up-shaped exits the guard does not yet cover. This
change migrates all three and widens the guard behind them:

- `zero-diff-streak` (`workflow.py:750-757`) — **deleted**, counter and `WorkflowFailed` alike.
  `MAX_ZERO_DIFF_COMMITS`, the `zero_diff` state parameter threaded through ~25 node
  signatures, and its `BUDGET_LABELS` entry go with it.
- `blocked_docs` (`workflow.py:396-419`) — `WorkflowFailed` → escalation. It is one more
  thing that goes to the operator.
- `docs-not-passed` — same.

Leaving them as `WorkflowFailed` after this change would mean the run still dies on exactly
the grounds AGENTS.md says it may not, with the guard still blessing it.

## Done when

- `make lint` clean from the repo root (ruff **and** ty, zero findings).
- `make test` passes, including `make check-no-env`, `make check-public` and the widened
  `make check-no-giveup`.
- No `WorkflowFailed` remains in `coder/` on the grounds of an exhausted repair budget, a
  zero-diff streak, or a docs block.
- A blocked result from **any** coder node reaches `context.md` as an `Await`, resumable
  through `POST /api/run/{run_id}/outbox`, and resumes at the node that raised it.
- A repair lap's second turn resumes the first turn's session, and a **resumed run** does too
  — the case the `.sessions` file cannot serve today.
- `grep -L blocked workflows/src/workhorse_workflows/coder/prompts/*.md` returns nothing.
- A rerun of the motivating story escalates within the first dev turn instead of entering the
  QA lane.

## What this deliberately does not do

- **No mechanical no-progress detector.** Not a lap counter, not a diff-hash identity check.
  Settled and dropped.
- **No cap on escalations.** `escalation.py`'s reasoning stands: "a run-side backstop would
  turn 'ask again' into 'give up', and the second escalation is often the one that gets a real
  answer."
- **No change to the inbox.** It stays a message log. Giving it a second way to write the gate
  file means two writers to `context.md` with no ordering between them.
- **No workflow-generated session ids.** Not portable across backends; capture-and-thread is
  the closest available shape.
- **No lane-by-lane rollout.**
