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
- [x] B3b — REWORK (supervisor, 2026-08-20): B3's sweep covered dev/review/docs/qa, but the
  FIFTH lane escaped: `coder/fix/flow.py` `implement` (~line 188) discards its `ImplResult`
  and unconditionally `return Continue(None, self.check)` — the exact dropped-verdict shape.
  Assign it, branch on the derived blocked signal like the other lanes (evidence test,
  escalate via `shared/escalation.py`). Also note `qa/flow.py::report_dev_pass` discards a
  `QaReport` on a green story — decide deliberately and leave a comment saying why it is
  fine (or branch it); do not leave it undocumented.
  (193e8a3, fbeb495) — `Fix.implement` assigns and branches; the block parks on the drained
  story's own `context.md` and `read_operator_impl` re-enters `implement` with the answer in
  the prompt. Two things the other four lanes did not need: `escalation()` gained an explicit
  `story` override, because the drain's `ctx` is the workspace (it draws a new story per
  iteration) rather than a `StoryPaths`; and there is no resolver arm, since the drain has no
  `operator_mode` and no queue of stories waiting behind this one. `report_dev_pass` is
  deliberately left unrouted — it runs only after the story passed every binding gate — but
  now assigns its `QaReport` and warns when it is blocked, so a missing tracker note is
  visible rather than silently absent. The QA-verdict arms of the drain (`recheck` flagging a
  bullet) are untouched: those are B7's.
- [x] B4 — session memory: surface the backend-minted session id to the workflow;
  `engine.agent`'s `session:` accepts a literal id; `enter` event records the threaded id;
  chains added to `apply-qa-fixes`, `rework_plan`, and the `fix-*` laps (and nothing else).
  Done when: a repair lap's second turn resumes the first turn's session across a run
  resume (the case `.sessions` cannot serve), covered by an engine test. (1be4eaa)
  The engine half was pre-existing (`sessions.is_session_id`, `Engine.session_id`,
  `chain`/`resumed_session` on `enter`, `_story_chain()` on the QA fix laps and
  `ci-fix:`/`qa-feedback:`/`qa-regression-fix:` chains); the `coder/fix` lane deliberately
  has none, since it runs exactly one lap. Missing was the composite the done-criterion
  names, now `test_a_repair_lap_resumes_its_own_session_after_the_run_dies_and_restarts`:
  it kills a run between laps and resumes into a fresh run dir, asserting the chain file is
  absent first. Note the loop's premise — an ordinary `--resume-run` reuses the run dir, so
  the chain file *does* survive that; what it cannot survive is artifacts moving or a lane
  resumed into a scope of its own, which is what the test models.
- [x] B5 — split the commit node (`coder/workflow.py:726` + `queue.py:919`): agent commits
  per-repo with Conventional subject + `Epic:`/`Story:` trailers (prompt-side); story-passed
  stamp becomes a stamp-only node at the same graph position; cleanliness check subtracts
  `snapshot_worktree_state` pre-existing dirt; first dirty→re-enter chained, second→escalate.
  (pre-existing: 87ee1af, plus c5a54f2) — the split landed whole in `87ee1af`:
  `commit_story` is off the epic success path (only story-mode's PR and the fix drain still
  call it), `check_repos_clean` + `stamp_story_passed` sit at that graph position,
  `preexisting` is subtracted, and `settle` is the chained first-dirty lap with `_dirty_gate`
  behind it. What was missing was a test for the *second* reading arriving by the other
  route: the blocked-settle test drives the gate from a lap that announces its own failure,
  and nothing drove a lap that reports `settled` while changing nothing — the optimistic
  self-report the design says not to believe. `c5a54f2` adds it. The prompt-side half of this
  line (telling the producer turns to commit) is deliberately B6's: `87ee1af` wrote
  `settle-worktree.md` and touched no other prompt, and `implement-plan.md` still carries no
  commit instruction.
- [x] B6 — the 16 prompts with no blocked outcome each gain it in their own return contract
  (no shared preamble); producer prompts gain the commit instruction from B5. (`5e9fbe2`)
  Done when: `grep -L blocked workflows/src/workhorse_workflows/coder/prompts/*.md` is empty.
  Notes: the blocked-outcome half was already satisfied — `grep -L blocked` is empty, and two
  of the plan's named sixteen (`check-code-reuse.md`, `fix-lint.md`) no longer exist. The real
  work was the second clause: 19 producer prompts gained the commit instruction, and
  `story_slug`/`epic` had to be threaded through 23 turn briefs (including `qa/flow.py`'s
  shared `_plan_args`) for the `Epic:`/`Story:` trailers to render. `test_prompt_variables.py`
  cannot see coder turns — they pass `turn.prompt`, not a literal — so the new
  `tests/coder/test_commit_instruction.py` classifies every prompt as producer or not and
  renders the trailers both ways.
- [x] B7 — migrate the three give-up exits and widen `scripts/check_no_giveup.py`:
  zero-diff-streak deleted (counter, `MAX_ZERO_DIFF_COMMITS`, threaded `zero_diff` param,
  `BUDGET_LABELS` entry); `blocked_docs` and `docs-not-passed` become escalations. (`c7b2424`)
  Done when: widened `make check-no-giveup` passes and would fail on the old code.
  Notes: the three exits were already migrated — the zero-diff mechanism in `87ee1af`, the
  docs block and `docs-not-passed` in `fa4ccb3`. What was NOT done is the second half: the
  guard banned only the two `failure_class` strings, and by the commit that deleted the
  zero-diff mechanism that exit had already become a gate, so the string was gone and the
  guard would have reported ok on the old code. `MAX_ZERO_DIFF_COMMITS`, `_zero_diff_gate`
  and `zero_diff=` are now banned too (bare `zero_diff` is not — the docstring saying why
  the counter is gone may name it); over the pre-migration `workflow.py` the widened list
  reports 54 offenders where the old one reported none. `workflows/tests/test_giveup_guard.py`
  pins that a planted line exits non-zero and that the vocabulary list cannot lose an entry.
- [x] B8 — phase gate: full `make test` (includes lint, check-no-env, check-public,
  check-no-giveup) green from the repo root. Fix anything this surfaces before moving on.
  (b25805b, e6a57dd, d4aa4ac, 629a1a3)
  Green from the repo root, rc=0. It surfaced four real defects, none of them in the work
  the earlier B items landed. `check_public.py` assembled `.git/hooks/pre-commit` by hand
  and so reported every guard missing in a worktree whose commits those guards had just
  been seen blocking; it now asks `git rev-parse --git-path`, and `scripts/` finally has a
  test package (`make test-scripts`). `check_parsers` caught three format-shaped regexes:
  the prompt-agnostic guard's `{% if %}`/`{% endif %}` pair, now jinja2's own lexer with
  identical exempt spans over all 90 prompts, and the dev-lane fix-envelope reader, now
  `ostler.markdown` — which also closes a live false positive, since the gate output fenced
  directly beneath those two bullets can quote a markdown line. The fourth was the gate
  lying quietly: `farrier install --check` treats a bundled script's own `__pycache__` as
  an asset, hits a non-UTF-8 file and *skips* the generated-file check, so running a skill
  script once disables that guard on your machine. The remaining skip on this tree
  ("Unknown selected prompt reference") is the documented public-clone path.

## Phase Q1 — QA baseline (measure before touching the QA lane)

- [x] Q1 — run the existing harness: `benchmarks/replay.py capture` then
  `replay.py run --flow qa --story expense-list -n 3 --label before` (see the script's own
  docstring for exact `uv run` invocation). Record the resulting table in
  `docs/plans/optimize-qa.md` under `## Progress`, `git add -f` it, commit `docs:`.
  This can run in the background of later Q-items but MUST complete before Q7.
  (bcbafae, 12cab91, 520593c)
  Notes: the harness could not run at all until two fixture defects were fixed. The
  `expense-list` pin was reachable from no ref in the source repo, so `git bundle --all`
  had been silently dropping it and a capture overwrote a working bundle with one the
  story could not be checked out of — `capture` now verifies every pin before replacing
  the bundle. The pinned story also predates the `## Dependencies` section
  `prepare_story` requires, so it is re-pinned at `c0478a9`. The baseline itself is a
  floor, not evidence for §2/§3: all four nodes exit first lap in 3/3 trials, $0.64,
  ~11–12 min per trial, and `apply-qa-fixes` never runs because this story's QA passes.
  Also: the trial agents committed their QA artifacts through the *outer* repo despite
  `benchmarks/.replay/` being gitignored; two stray commits were rebased off the branch.
  Worth a guard of its own if it recurs.

## Phase Q6 — ostler cold-start (the named pain, §6)

- [x] Q2 — diff-hash memoization of the `build_okf_context` packet in
  `coder/shared/okf.py`: same (docs_root state, diff) → reuse the packet instead of a fresh
  `Ostler(docs_root)` build. Done when: a repeat visit in a test hits the memo and the
  packet is byte-identical; `make lint` + workflows tests green. (74644a2)
  - The memo is a stamp file on disk, not an in-process cache: the repeated visits are
    separate node calls in separate processes, so nothing in memory survives between them.
  - The trap: the packet and its stamp are written *inside* the docs repo and are untracked,
    so the first signature counted them and every later visit missed. They are now excluded
    from the diff pathspec and the untracked scan they feed.
- [x] Q3 — on-disk snapshot cache in `ostler/ostler/api.py` keyed by
  (docs_root, HEAD, dirty-digest), so a fresh `Ostler` instance and the CLI stop paying the
  ~28s rebuild when nothing changed. Invalidation on any key component change; corruption →
  silent rebuild, never a wrong answer. Done when: ostler tests cover hit/invalidation/
  corruption; second construction in a test is >5x faster than the first on a warm cache.
  (ef8948f)
  Notes: the key is NOT (docs_root, HEAD, dirty-digest) as written. A git-shaped key is
  moved by every write into `docs/specs/`, which is exactly what a coder run does between
  two loads that want the same graph — the cache would have missed on every lap of the
  workflow it exists for. The entry instead records its own dependencies: the files read,
  the story paths probed and not found, and a listing digest of the three doc roots `load`
  actually reads. Measured on a generated 550-document book: 0.97s cold, 0.35s from a warm
  parse index, 0.023s from a snapshot — 15x over the leg the ledger's 5x bar is about.
- [x] Q4 — profile before anything cleverer: py-spy (or cProfile) one cold `ostler qa
  validate` on a real docs root; commit the findings as a short note in optimize-qa.md §6.
  If the cache from Q3 already makes cold-start irrelevant in the replay numbers, record
  that and stop here. (7dc4133)
  Notes: it stopped here, per the escape clause — Q3 puts a repeat visit at 0.19 s and the
  worst case a run can reach at 2.5 s, so what is left is a once-per-clone cost. The
  profile also refuted §6's premise twice: the time is not the symbol inventory (57.7 s of
  60.3 s is `_load_features`), and the hot loop is redundant re-parsing — markdown-it runs
  9,325 times for 844 documents because `refs` re-tokenizes what `sections` already parsed.
  Recorded, deliberately not scheduled.

## Phase Q2..Q5 — the QA lane itself (order: §2 → §3 → §5 → §4)

- [x] Q5 — §2 break up `apply-qa-fixes` (the 50% lever): one fix item per failing scenario
  with per-scenario dry-run proof; product-class failures route to the dev flow instead of
  being "fixed" in the QA lane; per-item budget spends toward `Await`, never a give-up.
  Done when: flow tests cover the per-scenario split and the product-class routing;
  `make check-no-giveup` still green. (8838bac)
  Note: the whole-report `apply-qa-fixes` turn had to stay — a run that names no failing
  scenario (evidence class, routed finding, operator note) still has nothing to split — so
  the fix loop now has two prompts sharing one budget, and every count assertion in the
  suite goes through the new `_Agent.fix_args()` rather than one stem. With
  `MAX_FIX_ITEM_REWORKS = 2` the exhaust arm is only reachable when the two refusals
  *differ*; two identical ones hit the stall check first, by design.
- [x] Q6 — §3 shrink the remaining plan-lane laps, building on `b619a7e` (do-not-reopen
  list in the plan: reviewer deletion, forbidden whole-plan self-validation, power=low
  repairs, stack-first). Two levers: (a) mine the rejection taxonomy from the transcript
  archive into `prompts/plan-qa.md`; (b) the first authoring turn dry-runs its 1–2 riskiest
  scenarios — the plan turn passes a non-empty `dry_run=(...)` into `_validated`. (aa13169,
  b2a6ba2)
  - (a) came off 110 `repair-qa-plan` briefs and 130 structured `review-qa-plan` findings in
    the groom transcript archive; the thirteen shapes that recur all *run green*, which is
    why the executing gates never caught them and why the brief is the only place to spend
    the knowledge.
  - (b) needed a schema field of its own (`QaPlanResult.proved_scenarios`) rather than
    reusing `repaired_scenarios`: the draft nominates, the repair reports, and the flow gates
    the two from different sources. An empty nomination has to skip the gate — otherwise "the
    author judged nothing risky" becomes a repair lap nothing can clear.
  - The test fake needed a second dry-run knob (`plan_dry_run`), because half the existing
    suite asks for a *repair* refused and wants the draft before it to have gone through.
- [x] Q7 — §5 lap discipline: `_repeating()` (qa/flow.py) gains an Await arm — two
  identical rejections → block through the MAX_QA_BLOCKS resolver path; finish power
  tiering on the repair laps. Done when: a test drives two identical rejections into an
  `Await`, not a third lap. (33c5747)
  - The post-run half of this was already built: `_repeating` → `_stalled` → one class
    switch → `_gate`. The gap was the *pre-run* half, and `_repeating` cannot serve it —
    it fingerprints a suite run, and no run happens between a repair and the schema or
    dry-run refusal that sends it round again. So the detector is a second field,
    `QaLoop.plan_rejections`, over the gate's own rendered notes.
  - Half the plan-gate suite asserted ceilings by refusing every pass with the *identical*
    message, which the new rule now stops at lap two. The fixture varies the finding per
    pass by default (a lane still moving) and `plan_invalid_stuck` asks for the identical
    one, so both directions are tested rather than one of them silently relaxed.
  - The tiering half was one line: `fix-qa-scenario` was still `power="high"`. Left
    provisional in the comment, because the plan makes it conditional on §1's measurement.
- [x] Q8 — §4 scenario budget derived from the qa-okf-context.json obligation packet; the
  plan gate rejects over-planning; the `covers:` fail-closed direction untouched. (70c6e05)
  - The bound landed in `ostler qa validate` (`validate_v2`), not in `evidence.py` as the
    plan listed: evidence.py is the *post*-run gate, and rejecting an over-planned plan
    after the suite has run pays the very cost the section exists to avoid. The pre-run
    refusal already routes through the existing repair lap.
  - Two halves, because the coverable fence only ever policed *which* ids a scenario claims:
    a scenario claiming none of them is refused, and the total is capped at one per coverable
    id plus half again (minimum one spare) for a requirement whose conflict branch needs its
    own run.
  - A packet with no obligations and no criteria bounds nothing — the evidence gate already
    accepts that surface on run-log proof, so a budget derived from it would refuse every
    plan that could be written.
- [x] Q9 — re-measure: `replay.py run --flow qa --story expense-list -n 3 --label after`,
  `replay.py report` both labels, fill the 30-minute table in optimize-qa.md `## Progress`
  with before/after, commit `docs:`. If ≤30 min is not met, write the diagnosis there —
  do not massage the claim (memory: measure before claiming optimization). (0fde6d7)
    - Notes: after = 10.9 min/trial mean vs before's 11.0, every node still 100% first-lap,
      0 excess turns, cost $0.64 → $0.74. The honest reading is written into the plan: this
      instrument replays a story whose QA *passes*, so it never spends the ~15 min the
      30-minute budget reserves for fix items and a repair lap. It shows a floor and the
      absence of a regression — not the envelope met. Confirming that needs a seeded-defect
      `app:` fixture and `score`, which is nobody's ledger item yet.
    - `replay.py report` prints convergence and cost but no duration, so wall clock came
      from the span of each trial's artifact directory.
- [x] Q9b — REWORK (supervisor, 2026-08-20 05:2x EDT): the stray replay-agent commit leak
  recurred — `ed36cff` ("docs(benchmarks): append independent expense-list QA audit") is
  trial 1 of `after` committing its qa.md through the *outer* repo, same shape as the two
  Q1 strays you rebased off. (a) Rebase every such stray off `optimize-full` before or
  with the Q9 tick, as before. (b) Build the guard you noted in Q1: a replay trial's
  agent must be unable to commit through the enclosing stablemate worktree — diagnose why
  the sandbox's own `.git` does not contain the commit (timing of the clone? agent cwd?)
  and make `replay.py` enforce it (e.g. verify outer HEAD unchanged after each trial and
  fail the trial loudly, and/or ensure the sandbox repo exists before the lane starts).
  Done when: a fresh replay trial on the fixed harness leaves outer `git log` untouched,
  covered by a test or an assertion inside `replay.py` itself; `make lint` green.
    - (a), partly, at the Q9 tick: the `after` arm leaked two strays — `ed36cff` (trial 1)
      and `5409f95` (trial 2), both appending a replay sandbox's `qa.md`. `5409f95` was
      unpushed and was dropped. `ed36cff` had already been pushed by the supervisor's own
      push, and AGENTS.md forbids force-pushing a shared branch, so it stays in history and
      a plain `revert` is what removes its content. (b), the harness guard, is what remains.
    - (b) done in `25aefda` (detection) + `f76c5ba` (prevention), verified by a live
      `--label guard2` trial: the four agent commits landed in the sandbox's own `.git`,
      outer HEAD stayed at `f76c5ba` and the tree stayed clean.
    - The surprise: `Popen(cwd=repo)` alone did **not** stop the leak — a `guard` trial with
      only that in place still committed three strays here. The child inherits `$PWD` from
      the launcher, and the agent CLI resolves its project root from `$PWD` rather than
      `getcwd()`, so the harness must set `PWD` (and drop `OLDPWD`) itself. This is the same
      alignment `workhorse/runner/process.py::_align_pwd` performs — but only for a node that
      declares a `cwd`, and the QA nodes declare none. Generalising `_align_pwd` to the
      `cwd is None` case would fix this workhorse-side for every caller; that is not done.

## Phase D — dev-lane plan (optimize.md), remaining steps only

Steps 1, 2 and 8 are recorded done in the plan itself. For each item below FIRST check the
tree/plan for evidence it already landed; tick `(pre-existing)` if so.

- [x] D1 — Plan A step 3: `FailureReport` + `fix` role + one session per lane in `dev`;
  power ladder + `max_session_turns`. Done when: dev happy path is plan → implement →
  gates; `BUDGET_LABELS` is the three-tuple.
  (pre-existing: a38380e, with `5e37578`, `1aec51a` and `4c181b9` around it) — the whole of
  step 3 is already on the branch. `coder/shared/failure.py` is the one seam
  (`from_gate`/`from_command`/`from_findings` → `FailureReport`), `dev/flow.py::fix` is the
  single repair role for every gate, it runs on `self._story_chain()` — the implementer's own
  conversation — bounded by `max_session_turns = 8`, and its power ladder is
  `"high" if stalled or fix_lap >= 2 else "low"`, i.e. low → low → high with the
  same-digest-twice escalation brought forward. The happy path is
  `dispatch → layer → implement → gates`, and `BUDGET_LABELS` is
  `("plan_rework", "fix_lap", "plan_blocks")`. `make lint` green; 1343 workflow tests pass.
  Note: the plan's own third clause for step 3 — "one-lint-failure path is three turns in the
  bench telemetry" — is a measurement, not a code state, and the ledger item deliberately
  omits it; D5 is where it gets measured.
- [x] D2 — Plan A step 4: `PlanResult` carries the structure; `plan-context.json` becomes a
  Python-written projection; `validate_plan_context` shape checks and `rework_paths` go;
  no prompt under `coder/` names `plan-context.json`.
  (pre-existing: 368c58e) — all four criteria hold. `PlanResult`
  (`coder/shared/schemas/dev.py`) carries `services` / `implementation_order` /
  `shared_packages` / `verification_setup`, so a malformed plan is a pydantic parse retry
  rather than a workflow state; `coder/shared/dev.py::validate_plan` writes the projection
  itself (`json.dumps(doc)` into `<spec>/plan-context.json`) and then validates *that*
  document, keeping only the semantic checks — declared path exists, marker file present,
  build order references declared services. `validate_plan_context` and `rework_paths` no
  longer exist anywhere in `workflows/src` or `base-library`, and no prompt under
  `coder/prompts/` mentions `plan-context.json`; the remaining mentions are Python readers
  (`shared/queue.py`) and docstrings explaining the projection. `make lint` green;
  1343 workflow tests pass.
- [x] D3 — Plan A step 5: `agents.yml` service commands + deterministic test/lint/smoke
  nodes; genesis writes the block; farrier doctor warns; delete the "MANDATORY" prose.
  (pre-existing: 8fbd112 + c98bac0) — `coder/shared/dev.py::_services_config` reads the
  repo's `services:` block (top-level or under `workflow:`), `service_keys` resolves a layer
  to its narrowest declaring key, and `dev/flow.py::gates` runs each of `GATE_ORDER` through
  `run_gate`, an undeclared gate being `skipped` rather than guessed. Genesis writes the
  block (`genesis/nodes.py:330` seeds `data["services"][service]` from the story's
  `"<gate>=<command>"` pairs, asserted at `workflows/tests/coder/genesis/test_flow.py:217`).
  `farrier doctor` warns on a missing block, a non-mapping entry, a missing test/lint
  command and a service root matching no key (`farrier/tests/test_doctor_command.py`, 305
  farrier tests pass). No "MANDATORY" prose survives anywhere under `coder/prompts/`; the
  implement envelope now prints "Gates that run after this turn: … / (nothing declared)".
  The bench repo `/tmp/bench-expense-split/agents.yml` carries a real `services.api` block
  (`lint`, `test`, `tdd: required`), which is the plan's own Done-when.
  Note — one gap against this item's *shorthand*, recorded rather than papered over:
  `smoke` is declarable in `services:` and documented in `_services_config`, but it is not
  a deterministic gate. `GATE_ORDER` is `("lint", "test")`. That matches the source plan's
  prose ("Deterministic nodes run `test` and `lint` after the implement turn and after
  every fix turn") and its Done-when, and smoke stays an agent-run step driven by
  `implement-plan.md`'s run plan — booting a service on every repair lap under the 600s
  gate timeout is a behaviour change the plan does not ask for. If smoke-as-a-gate is
  wanted, it is a new item, not a silent widening of this one.
- [x] D4 — Plan A step 6: goal setting in the envelope + `goal` adapter; TDD gate with the
  `tdd:` key.
  (pre-existing: 4c181b9) — both adapters landed in one commit and have been refined since
  (`a72b117`, `68a3e35`, `d3ed91f`, `de2d043`). The envelope asks for the promise
  (`implement-plan.md` prints `Gates that run after this turn` and `Tests, as this repo
  declares them: {{ tdd }}`, and the result schema carries `exit_conditions: ExitConditions`
  plus `tests_added` / `no_test_reason`); `dev/flow.py::_claims` reads that promise back
  through `check_promises` and then `tdd_gate`, both `skipped` where there is nothing to
  check, and a dirty one becomes a `FailureReport{source: "goal"|"tdd"}` into the same fix
  loop every declared gate feeds (`dev-fix.md` has the branch for each). `tdd_mode` reads
  `services.<type>.tdd` from the repo's `agents.yml`, `TDD_EXEMPT_TYPES = ("docs", "config")`
  is the only place `no_test_reason` is accepted, and `_claims` runs only after the declared
  gates are green.
  The plan's Done-when is asserted as a test rather than left to the bench:
  `workflows/tests/coder/dev/test_flow.py:995`,
  `test_a_test_less_story_is_caught_by_the_tdd_gate_and_repaired_in_the_same_loop`, declares
  `services.go.tdd: required`, runs a story that writes no test, and asserts
  `report["source"] == "tdd"` and that the same fix loop repairs it; the sibling at :973 does
  the same for `goal`. `make lint` green; 1343 workflow tests pass.
  Note: the Done-when's other half — "`ImplResult.exit_conditions` is populated **on the
  bench**" — is a telemetry observation, not a code state, and belongs to D5 with the rest of
  the measurement, same as D1's third clause.
- [x] D5 — Plan A step 7: re-measure with `benchmarks/devlane.py` per
  optimize-baseline.md's reproduce section; fill optimize.md's success table row by row.
  (5215a08) — the table existed already (written at `e733840` off runs `a12`–`a15`), so this
  iteration re-ran the measurement on today's HEAD and rewrote the table around the whole
  set rather than its best member. New run `c1` (`devlane.py run --at 3fa416f --story
  expense-list --run-id c1`, 23.4 min wall, $8.29) plus the existing `a12`–`a15`/`b1`–`b3`
  makes n=8 on one story from one commit. Median wall clock **13.9 min, 39 % under the
  22.7 min baseline** — target met, but on a spread of 11.0–23.2 min that is wider than the
  effect, which is why the median and not `a14`'s 11.7 min (48 %) is now the claim.
  Two surprises, both written into the plan rather than smoothed over:
  * `c1` is the slowest run in the set and it is the newest. It spent three repair turns —
    one `refine-plan` and two `test` laps — after the same two high-power turns everything
    else spends. The `refine-plan` lap is a defect, not a bad plan: `plan-story` wrote
    `plan_file: "docs/specs/expense-list/plan.md"` (repo-relative) and `validate_plan`
    resolves it under the spec dir, so the same string is right under one reading and
    unresolvable under the other. 203 s of high-power turn. Filed as D8 below.
  * The schema row was counting differently on each side — the baseline's "5 agent results"
    included `OperatorResolution`, the "3" did not. Like for like it is 5 → 4, or 4 → 3
    without the operator gate; the row now says so.
  Fix-lap rate is now measured on the A side (`goal` 3/3, `test` 1/2) but still has no
  baseline to be "not lower" than, exactly as optimize-baseline.md predicted, so it stays
  ⚠️ and carries to D7. Guard row re-checked live: `make check-prompt-agnostic` is clean over
  91 files (the plan said 90).
- [x] D6 — Plan B steps 9–10: dispatch from markers + `qa_stack` rename (see memory:
  plan-context `qa_stack` field vs `qa-stack.yml` schema collision — this is where it gets
  fixed); review/QA apply steps re-enter the implementer session.
  (pre-existing: 368c58e, b53fba4, cf6b078, ae962af/44169b2/8dcad96) — verified clause by
  clause rather than by commit subject, because the item is four separate landings:
  * **The agent returns the structure** (`368c58e`): `PlanResult` carries `services[]`
    (`PlanService` with repo/path/type/skills/plan_file/new_service), `implementation_order`
    and `shared_packages`; `shared/dev.py::record_plan` writes `plan-context.json` as a
    one-way *projection* and the module header says so. The remaining `load_json` sites are
    all outside the producing run — `shared/review.py` (standalone PR), `nodes/pr.py`,
    `shared/queue.py` — which is exactly the projection's stated readership.
  * **Dispatch from markers** (`b53fba4`): `shared/dev.py::declared_markers` reads
    `workspace.service_markers` off each repo and renders it into `plan-story.md`, with a
    written fallback branch for a workspace that declares none, instead of the planner
    recalling a taxonomy.
  * **The rename** (`cf6b078`): the field is `verification_setup`; the old spelling survives
    only as `validation_alias=AliasChoices("verification_setup", "qa_stack")` plus
    `shared/dev.py:152`'s `doc.get(...) or doc.get(...)`, because a checkpoint or a
    `plan-context.json` written before the rename is what a resume validates against.
    `qa_stack_manifest` is untouched on purpose — it is the *file* `qa-stack.yml`, the other
    half of the homograph, and renaming it would have collided the two again from the
    opposite side.
  * **Apply steps re-enter the implementer session** (`ae962af` threaded the backbone,
    `44169b2` fixed QA's fix laps onto it, `8dcad96` did review): review's three apply turns
    run on `_impl_chain()` and drop to `"low"` power when a `session_id` was threaded in,
    while the judging turns stay cold by design; QA's `_apply_fixes` runs the fix and
    operator-guided laps on `_story_chain()`, and `qa-feedback:`/`qa-regression-fix:` keep
    private chains deliberately, with the reason written on `_WORKLISTS`.
  Gate: `make lint` clean, `workflows` 1343 passed.
- [x] D8 — `plan_file` is ambiguous between repo-relative and spec-relative, and the
  disagreement costs a high-power `refine-plan` lap (seen in run `c1`, 203 s). Either accept
  both readings in `coder/shared/dev.py::validate_plan` or say which one the field means
  where the planner reads it — with a test either way.
  (e4e814a) — took the accept-both arm, and the surprise was that it could not be taken at
  `validate_plan` as the item proposed: the errors run `c1` got came from *two* checkers,
  this module's `(spec_abs / plan_file).exists()` and `ostler artifact vet`'s
  `artifact/kinds.py:95`, which resolves the field identically. Repairing the value in
  `plan_document` — where the projection is built, before it is written and before ostler
  vets it — is the one place that clears both, and it also means every later reader (QA on a
  later run, a human in the spec dir) sees a single spelling instead of whichever one the
  planner happened to hold. The repair is narrow: only a path resolving to a file *inside*
  the spec dir; anything else passes through verbatim so the error still quotes what was
  written. Both sides are `.resolve()`d before comparison because `story.py` hands the spec
  dir over already resolved while the repo root arrives as given — on a `/tmp` checkout the
  two would otherwise share no prefix. Tests: a flow-level one asserting zero `refine-plan`
  laps (red before the fix, and the flow really does run the lap without it) and a unit one
  pinning the outside-the-spec-dir passthrough. `make lint` clean, `workflows` 1345 passed.
- [ ] D7 — Plan B step 11: final re-measure; B claims only turn-count/schema rows unless
  the table says otherwise. Full `make test` green. Write a closing summary at the top of
  this ledger.

## Blocked

(Items land here with a dated reason when an iteration cannot ground them. They are
revisited by later iterations only if something changed; otherwise they wait for the
operator.)
