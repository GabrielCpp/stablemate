# Overnight ledger — full optimize program on top of `stable-bench`

This file is the **program counter** for a ralph loop: each iteration picks the FIRST
unchecked `- [ ]` item below, does that one item, and ticks it `- [x] (<commit-hash>)`.
State lives here and in git, never in a conversation. Rules for every iteration are in
`docs/plans/ralph-prompt.md`.

The four source plans (read the relevant one before touching its items):

- `docs/plans/blocked-handoff-and-session-memory.md` (B-items)
- `docs/plans/optimize-qa.md` (Q-items)
- `docs/plans/optimize.md` + `docs/plans/optimize-baseline.md` (D-items)

Some items may already be partly landed on `stable-bench`. **Verify against the tree
first**; if an item is already fully done, tick it with the existing commit hash and a
`(pre-existing)` note instead of redoing it.

## Phase B — blocked handoff & session memory (prerequisite infrastructure)

- [x] B1 — `coder/shared/schemas/_base.py`: consolidated blocked marker on `CoderResult`
  (replacing `unfixable`/`not_passed`/`invalid`/`blocked` spellings) + `findings:
  list[Finding]` with location+demand; default distinguishable from a dead node's nulls.
  Done when: schema tests cover the dead-node case; `make lint` clean.
  (pre-existing: 71a83d7) — `blocked` is derived from `status` against `BLOCKED_STATUSES`
  rather than declared as a field, which is what keeps a dead node's nulls off the
  escalation arm; `findings` is read off the subclass so `QaAssessment`/`DocumentationReview`
  keep their narrowed element types. `workflows/tests/coder/shared/test_blocked_signal.py`
  covers the dead-node case (9 passed); `make lint` clean.
- [x] B2 — move/generalise `_escalation` (`dev/flow.py:739`) into `coder/shared/escalation.py`
  with `block_kind`/`where` as parameters; all lanes call the shared helper.
  (pre-existing: 0c0a547) — `shared/escalation.py::escalation(flow, *, block_kind, where,
  notes, number, result, findings)` takes the story identity off the flow; dev/docs/qa/review
  all import it and their surviving `_escalation` methods are thin per-lane defaults for
  `block_kind`/`where`/the counter, not second implementations. The helper also gained a
  `What the node found` findings section. 77 shared-coder tests pass; `make lint` clean.
- [x] B3 — the four lane flows route the signal. Root cause first: `_implement_classic`
  (`coder/dev/flow.py:636`) assigns its agent result and both callers branch on it.
  Every discarded `self.agent(...)` result in dev/review/docs/qa flows assigned and
  branched; evidence test (findings→fix, else escalate); each escalation site gets a thin
  consume-the-answer state (Await resumes with a cheap prefix).
  Done when: a blocked result from any coder node reaches `context.md` as an `Await` and
  resumes at the raising node; flow tests cover the dropped-verdict case.
  (pre-existing: 139f963) — `_implement_classic` returns its result and both callers branch;
  no statement-level `self.agent(...)` remains in the four flows; dev gained `_gate_impl` +
  the thin `read_operator_impl` consume state. Advisory turns (review feeders, the dev
  report) deliberately warn and carry on rather than escalating, since a binding check runs
  after them. `test_an_implementation_turn_that_says_it_cannot_reaches_the_operator` drives
  the dropped-verdict case end to end. 776 coder tests pass; `make lint` clean.
- [ ] B3b — REWORK (supervisor, 2026-08-20): B3's sweep covered dev/review/docs/qa, but the
  FIFTH lane escaped: `coder/fix/flow.py` `implement` (~line 188) discards its `ImplResult`
  and unconditionally `return Continue(None, self.check)` — the exact dropped-verdict shape.
  Assign it, branch on the derived blocked signal like the other lanes (evidence test,
  escalate via `shared/escalation.py`). Also note `qa/flow.py::report_dev_pass` discards a
  `QaReport` on a green story — decide deliberately and leave a comment saying why it is
  fine (or branch it); do not leave it undocumented.
- [ ] B4 — session memory: surface the backend-minted session id to the workflow;
  `engine.agent`'s `session:` accepts a literal id; `enter` event records the threaded id;
  chains added to `apply-qa-fixes`, `rework_plan`, and the `fix-*` laps (and nothing else).
  Done when: a repair lap's second turn resumes the first turn's session across a run
  resume (the case `.sessions` cannot serve), covered by an engine test.
- [ ] B5 — split the commit node (`coder/workflow.py:726` + `queue.py:919`): agent commits
  per-repo with Conventional subject + `Epic:`/`Story:` trailers (prompt-side); story-passed
  stamp becomes a stamp-only node at the same graph position; cleanliness check subtracts
  `snapshot_worktree_state` pre-existing dirt; first dirty→re-enter chained, second→escalate.
- [ ] B6 — the 16 prompts with no blocked outcome each gain it in their own return contract
  (no shared preamble); producer prompts gain the commit instruction from B5.
  Done when: `grep -L blocked workflows/src/workhorse_workflows/coder/prompts/*.md` is empty.
- [ ] B7 — migrate the three give-up exits and widen `scripts/check_no_giveup.py`:
  zero-diff-streak deleted (counter, `MAX_ZERO_DIFF_COMMITS`, threaded `zero_diff` param,
  `BUDGET_LABELS` entry); `blocked_docs` and `docs-not-passed` become escalations.
  Done when: widened `make check-no-giveup` passes and would fail on the old code.
- [ ] B8 — phase gate: full `make test` (includes lint, check-no-env, check-public,
  check-no-giveup) green from the repo root. Fix anything this surfaces before moving on.

## Phase Q1 — QA baseline (measure before touching the QA lane)

- [ ] Q1 — run the existing harness: `benchmarks/replay.py capture` then
  `replay.py run --flow qa --story expense-list -n 3 --label before` (see the script's own
  docstring for exact `uv run` invocation). Record the resulting table in
  `docs/plans/optimize-qa.md` under `## Progress`, `git add -f` it, commit `docs:`.
  This can run in the background of later Q-items but MUST complete before Q7.

## Phase Q6 — ostler cold-start (the named pain, §6)

- [ ] Q2 — diff-hash memoization of the `build_okf_context` packet in
  `coder/shared/okf.py`: same (docs_root state, diff) → reuse the packet instead of a fresh
  `Ostler(docs_root)` build. Done when: a repeat visit in a test hits the memo and the
  packet is byte-identical; `make lint` + workflows tests green.
- [ ] Q3 — on-disk snapshot cache in `ostler/ostler/api.py` keyed by
  (docs_root, HEAD, dirty-digest), so a fresh `Ostler` instance and the CLI stop paying the
  ~28s rebuild when nothing changed. Invalidation on any key component change; corruption →
  silent rebuild, never a wrong answer. Done when: ostler tests cover hit/invalidation/
  corruption; second construction in a test is >5x faster than the first on a warm cache.
- [ ] Q4 — profile before anything cleverer: py-spy (or cProfile) one cold `ostler qa
  validate` on a real docs root; commit the findings as a short note in optimize-qa.md §6.
  If the cache from Q3 already makes cold-start irrelevant in the replay numbers, record
  that and stop here.

## Phase Q2..Q5 — the QA lane itself (order: §2 → §3 → §5 → §4)

- [ ] Q5 — §2 break up `apply-qa-fixes` (the 50% lever): one fix item per failing scenario
  with per-scenario dry-run proof; product-class failures route to the dev flow instead of
  being "fixed" in the QA lane; per-item budget spends toward `Await`, never a give-up.
  Done when: flow tests cover the per-scenario split and the product-class routing;
  `make check-no-giveup` still green.
- [ ] Q6 — §3 shrink the remaining plan-lane laps, building on `b619a7e` (do-not-reopen
  list in the plan: reviewer deletion, forbidden whole-plan self-validation, power=low
  repairs, stack-first). Two levers: (a) mine the rejection taxonomy from the transcript
  archive into `prompts/plan-qa.md`; (b) the first authoring turn dry-runs its 1–2 riskiest
  scenarios — the plan turn passes a non-empty `dry_run=(...)` into `_validated`.
- [ ] Q7 — §5 lap discipline: `_repeating()` (qa/flow.py) gains an Await arm — two
  identical rejections → block through the MAX_QA_BLOCKS resolver path; finish power
  tiering on the repair laps. Done when: a test drives two identical rejections into an
  `Await`, not a third lap.
- [ ] Q8 — §4 scenario budget derived from the qa-okf-context.json obligation packet; the
  plan gate rejects over-planning; the `covers:` fail-closed direction untouched.
- [ ] Q9 — re-measure: `replay.py run --flow qa --story expense-list -n 3 --label after`,
  `replay.py report` both labels, fill the 30-minute table in optimize-qa.md `## Progress`
  with before/after, commit `docs:`. If ≤30 min is not met, write the diagnosis there —
  do not massage the claim (memory: measure before claiming optimization).

## Phase D — dev-lane plan (optimize.md), remaining steps only

Steps 1, 2 and 8 are recorded done in the plan itself. For each item below FIRST check the
tree/plan for evidence it already landed; tick `(pre-existing)` if so.

- [ ] D1 — Plan A step 3: `FailureReport` + `fix` role + one session per lane in `dev`;
  power ladder + `max_session_turns`. Done when: dev happy path is plan → implement →
  gates; `BUDGET_LABELS` is the three-tuple.
- [ ] D2 — Plan A step 4: `PlanResult` carries the structure; `plan-context.json` becomes a
  Python-written projection; `validate_plan_context` shape checks and `rework_paths` go;
  no prompt under `coder/` names `plan-context.json`.
- [ ] D3 — Plan A step 5: `agents.yml` service commands + deterministic test/lint/smoke
  nodes; genesis writes the block; farrier doctor warns; delete the "MANDATORY" prose.
- [ ] D4 — Plan A step 6: goal setting in the envelope + `goal` adapter; TDD gate with the
  `tdd:` key.
- [ ] D5 — Plan A step 7: re-measure with `benchmarks/devlane.py` per
  optimize-baseline.md's reproduce section; fill optimize.md's success table row by row.
- [ ] D6 — Plan B steps 9–10: dispatch from markers + `qa_stack` rename (see memory:
  plan-context `qa_stack` field vs `qa-stack.yml` schema collision — this is where it gets
  fixed); review/QA apply steps re-enter the implementer session.
- [ ] D7 — Plan B step 11: final re-measure; B claims only turn-count/schema rows unless
  the table says otherwise. Full `make test` green. Write a closing summary at the top of
  this ledger.

## Blocked

(Items land here with a dated reason when an iteration cannot ground them. They are
revisited by later iterations only if something changed; otherwise they wait for the
operator.)
