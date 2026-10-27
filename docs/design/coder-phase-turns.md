# A strong mind for the plan, a cheap one for the build

**Disclosure.** I read the existing solution before this note was written. That covers
the dev flow and its prompts, the QA and docs prompts, the coder prompt-role resolver,
the engine's agent call, recovery ladder, session chains and delegate catalog, the claude
and codex backends, the skill reference helpers, and the operator's profile config. The
four options this note designs came out of a brainstorm over that code. Every design
decision they carry is a claim in section 1b. Section 4 re-derives or rejects each one.

## 1. Problem

**Who feels this.** An operator runs the coding workflow on a story and pays for every
token the story owner reads. Today one strength of model carries the whole story, from
the plan to the last fix. The plan, where judgement matters most, gets the same model as
the mechanical build. Every repair lap resends the owner's full rulebook, about 5,300
tokens, to a conversation that already holds it. The owner also reads every helper's
procedure in full, though it only hands those procedures on.

**Done looks like this.**

- The strongest tier in the operator's profile writes the story's plan. The build and the
  review run on a cheaper tier, in the same conversation, so nothing the plan turn
  learned is lost.
- When the cheaper owner meets a design call it should not make alone, a strong-tier
  advisor answers it in a fresh context. Every declined finding and every departure from
  the plan carries the advisor's answer. A check refuses the story when one does not.
- A repair lap sends what changed and a pointer to the rules, under 1,000 tokens in the
  common case. A conversation the engine replaced opens with its phase's full rules.
- The owner's briefs carry no helper procedure. Each phase brief stays under 2,500
  tokens. The helpers read their procedures themselves.
- The story's gates, findings and settlement decide "ready" exactly as they do today.

**Out of scope.**

- Splitting the QA, docs or fix-item owners into phases. Their procedures move to skills,
  and their repair laps get short follow-up notes. Their turn structure stays.
- Migrating body overrides or flavor files that target repos wrote for `dev-story` or
  `dev-rework`. The retired roles fail loudly at render. The repo that owns the override
  rewrites it (A5).
- Changing ostler's answer format or settlement rules.
- Choosing which model each tier maps to. The operator's profile owns that.
- Cutting the cost of a plan turn. Moving the plan to the strongest tier raises its price
  on purpose (section 5b, row "cost per story").

## 1b. Claims

1. Split the dev prompt into plan, build and answer prompts. Each runs as a turn on the
   same story conversation at its own power. (brainstorm, option 1)
2. Plan on high power, build on a cheaper model. (brainstorm, option 1)
3. A repair lap sends only the report. The full prompt goes again only after compaction
   or a failed resume, detected through the rebrief hook. (brainstorm, option 2)
4. The reviewer brief, the triage rules, the docs writer's, reviewer's and fixer's rules
   and the QA plan contract move into workhorse-pack skills. The subagent loads them
   through `skill_command` or `skill_path`. (brainstorm, option 3)
5. A Sonnet owner consults an Opus `advisor` delegate, a role next to `lookup` and
   `worker`. (brainstorm, option 4)
6. In-turn builder, triager and fixer subagents are handoffs the single-agent guidance
   argues against. (session analysis of the decoder article)
7. One owner per story on one conversation. Judges run in fresh contexts.
   (`docs/design/lead-agent-workflows.md`)
8. A new stage needs two attended sessions on a real target before it runs unattended.
   (constitution, aim 9)
9. The owner prompt should say the run builds on the next turn, so the plan turn writes
   the plan and stops. (session analysis)

## 2. Parts and concepts

### Level 1: parts

| Part | Owns | Never knows | Hands to |
|---|---|---|---|
| **Work order** | The order of the owner's work on one story, and the strength each stretch of it runs at | The text of any brief, or which model a strength maps to | Briefing: the phase to brief. The conversation: the turn to run. |
| **Briefing** | What the owner is told at each turn: a full brief or a short follow-up note | Why a phase comes next, or how a conversation is kept | The conversation: the text of the turn |
| **Conversation keeping** | The one conversation a story's owner keeps across turns, and the moment it is replaced | What the owner is told, or why | Briefing: "this conversation is new" |
| **Counsel** | The strong second opinion the owner consults at named moments, and the proof it did | The owner's phase order, or the procedures helpers follow | Work order: a refusal when a consult is missing |
| **Helper procedures** | The procedures each helper follows: reviewer, triager, docs writer, docs reviewer, docs fixer, QA planner | Which owner sends a helper, or at what strength | Briefing: a pointer the owner forwards |

**The flow.** Work order starts the story in its plan phase. Briefing gives the
conversation the plan brief, and the strong tier writes the plan. Work order moves to
build. Briefing sees the conversation has not had the build brief and sends it in full,
and the cheap tier builds. Work order moves to review. The owner sends reviewers, each
pointed at its procedure. The owner answers their findings, and consults counsel before
it declines one. The story's checks run. When a check fails, work order sends the story
back to review with the report. Briefing sees the conversation already holds the review
brief and sends a follow-up note. When the engine replaces the conversation, conversation
keeping says so, and briefing sends the full brief of the current phase again. When the
review phase ends, counsel audits the result before the story counts as ready.

**The split in one paragraph.** A story's owner works in three stretches: plan, build,
review. The plan gets the strongest mind, the rest a cheaper one, all in one running
conversation. The owner is told its rules once per stretch, and after that only what
changed. When the cheaper mind meets a real decision, it asks a strong advisor and writes
down the answer, and the story cannot finish with a decision nobody asked about. The
helpers keep their own instructions, so the owner never carries them.

### Level 2: concepts

**Work order**

| Concept | Owns | Never knows |
|---|---|---|
| Phase | One stretch of the owner's work: its goal and its end condition | The brief's text |
| Phase strength | The tier each phase runs at | The model a tier maps to (the profile) |
| Phase route | The next phase after a phase ends, a check fails, QA sends the story back, or the operator answers | What the phase brief says |
| Phase result | What one phase reports back: ready, blocked, its findings, its consults | How the result is checked |

**Briefing**

| Concept | Owns | Never knows |
|---|---|---|
| Phase brief | The full rules of one phase | The conversation it lands in |
| Follow-up note | What changed since the brief, and where the brief can be reread | The brief's rules |
| Brief copy | The kept, rendered brief of one phase for one story | Whether the conversation still holds it |
| Brief ledger | Which phase briefs the current conversation has received | The text of any brief |
| Brief choice | Full brief or follow-up note, for one turn | How the ledger learns of a new conversation |

**Conversation keeping**

| Concept | Owns | Never knows |
|---|---|---|
| Conversation identity | Which conversation the story's owner is on | What was said in it |
| Conversation replacement | The fact that a turn started a new conversation | Why briefing cares |
| Restart brief | The text a replacement conversation opens with: the current phase brief plus where the work stands | Which phase comes next |

**Counsel**

| Concept | Owns | Never knows |
|---|---|---|
| Advisor | Answering one design question in a fresh context, at the strong tier | The owner's conversation |
| Consult trigger | The named moments the owner must consult: declining a finding, departing from the plan | How the advisor answers |
| Consult record | The owner's account of one consult: the question, the answer, what it decided | Whether the record is checked |
| Consult audit | Refusing a result whose declines or departures lack a consult record | The advisor's reasoning |
| Counsel availability | Whether this run can reach an advisor | Which CLI or model provides it |

**Helper procedures**

| Concept | Owns | Never knows |
|---|---|---|
| Procedure | One helper's full instructions | The owner that sends the helper |
| Procedure pointer | The line an owner forwards so a helper can find its procedure | The procedure's content |

The procedure catalog is a read-only reference every part consults. It is the skill
catalog the run already renders with. It is not a concept of this design.

## 3. Invariants

1. **A conversation never gets a follow-up note for a phase whose brief it has not
   received.** Owner: brief choice. Upheld by the brief ledger and conversation
   replacement.
2. **Every declined finding and every departure from the plan carries a consult record.**
   Owner: consult audit. Upheld by the consult trigger in the review and build briefs.
3. **A replacement conversation opens with its current phase's full brief and the result
   contract.** Owner: restart brief.
4. **Every procedure pointer resolves in the catalog when the brief renders.** A missing
   one fails the render, not the helper. Owner: procedure pointer.
5. **No phase brief contains a procedure's body.** Owner: phase brief, held by a prompt
   test that renders each brief and searches it for each procedure's headings.
6. **A story is ready only when its gates pass and its findings settle.** Owner: the
   story's existing check. This design moves nothing in it.
7. **Phase briefs and procedures stay stack-neutral.** Owner: the existing neutrality
   check, extended to the new procedure files.
8. **Only the plan phase writes the plan.** A later phase changes the plan only through a
   consulted departure. Owner: consult audit (invariant 2 covers the departure).

## 4. Forces and patterns

### Forces

- **F1. Judgement need varies by phase.** A plan fixes the approach, the stages and the
  tests. A build follows it. A review triage is mostly mechanical, except a decline.
- **F2. Price varies about five-fold between the strong and the cheap tier.** The plan is
  a small share of a story's tokens. The build and the fix laps are most of them.
- **F3. The tier-to-model mapping varies by operator and by CLI.** The operator's claude
  profile maps `high` to Sonnet and `max` to Opus. The codex profile maps them to other
  models. A workflow must speak in tiers.
- **F4. A conversation can lose its rules two ways.** The engine replaces it after a
  failed resume or a failed compaction, and knows it. The CLI can also compact on its
  own, and the engine does not see that.
- **F5. Helper procedures grow, and several owners and humans share them.** The target
  repos install the stablemate skill pack.
- **F6. Not every CLI can host a subagent.** Claude and codex define delegates at launch.
  Copilot and cline do not.
- **F7. An agent that can get by alone stops consulting a specialist.** The decoder
  article reports one merge that broke this way.
- **F8. A new stage runs attended twice before it runs alone.** (claim 8)
- **F9. Each turn on a conversation rereads its transcript.** A tier switch rereads it
  once without the cache.

### Between parts

- **One conversation, a sequence of phases** (F1, F2). Work order runs plan, build and
  review as separate turns on the story's one conversation. Each turn names its tier.
  The conversation carries what the plan learned into the build. A cache miss at each of
  two switches is the price (F9).
- **Tiers, not models** (F3). Phase strength names a tier. The profile resolves it.
- **Pointer, not payload** (F5). Briefing forwards a procedure pointer. The helper reads
  the procedure.
- **A signal from conversation keeping to briefing** (F4). Conversation replacement is an
  event briefing reads: the conversation's identity changed since the ledger last saw it.

### Inside each part

- **Phase strength: a plain table** (F1). Plan: `max`. Build: `high`. Review: `high`.
  The advisor: `max`. No pattern. One line changes when an operator wants a different
  split.
- **Phase route: a state machine** (F1). Each phase is a state. A failed check goes to
  review. A send-back from QA goes to review. An operator answer returns to the phase
  that blocked.
- **Brief choice: a plain function** of the ledger and the conversation identity (F4).
- **Follow-up note carries the brief copy's path** (F4). The note tells the owner where
  its brief is and to reread it when it no longer holds it. This covers the compaction
  the engine cannot see. A silent compaction costs one file read, not a wrong turn.
- **Counsel: a role with two variants** (F6). The role is "answer a design question at
  the strong tier".
  - *Delegate advisor*: a subagent the CLI defines at launch, at the advisor tier.
  - *Self counsel*: no subagent exists, so every phase runs at the strong tier and the
    owner decides alone.
  - The choice belongs to the part that assembles the turn: work order asks counsel
    availability and picks the phase strength from it. Neither variant knows the other.
- **Consult audit: a hard check, not a reminder** (F7). The audit reads the phase
  result's consult records and the settlement's declines. A decline with no record sends
  the story back to review with a report naming it.
- **Procedure pointer: a path, not a command** (F5, F6). A helper may lack the skill
  tool. A read-only helper has only read and search tools. Every helper can read a file.

### Claims

1. **Re-derived, renamed** from F1 and F2. The third phase is "review", not "answer",
   because failed checks and QA send-backs land there too.
2. **Re-derived** from F2, in tiers (F3). On the operator's claude profile the owner runs
   at `high`, which is Sonnet already. The change moves the plan up to `max`. It does not
   move the build down.
3. **Re-derived in part.** The engine-visible replacement is kept. The silent compaction
   is answered by the pointer in every follow-up note (F4). The rebrief hook must send the
   phase brief, not only the resume note (section 5, finding R3).
4. **Re-derived** from F5, with `skill_path` only (F6). `skill_command` renders a slash
   command a helper without the skill tool cannot run.
5. **Re-derived** from F6 and F7 as the counsel role, with the audit added. The role is
   tier-named: `advisor` at `max`, not "Opus".
6. **Re-derived** from F1 and F2. The build phase is the builder, so a builder handoff
   inside it has no reason left. Triage and fixes belong to the review phase's owner. The
   worker delegate stays for parallel bounded work. Reviewers stay subagents, because a
   reviewer must not share the builder's view (claim 7).
7. **Kept.** One conversation per story. Reviewers and QA judge in fresh contexts.
8. **Kept** as F8. Each new phase gets its two attended sessions in its slice.
9. **Re-derived** from F1. The plan brief ends the plan phase at a written plan.

### Open lookups

- L1. Does the codex CLI accept a model change on `exec resume`? Waits: phase strength
  on codex.
- L2. Can a workflow learn whether a delegate role is defined for this run? Waits:
  counsel availability.
- L3. Can a workflow render a prompt template with its args, outside a turn? Waits: brief
  copy.
- L4. Does a phase's node keep its full brief on disk after a follow-up turn on the same
  node? Waits: brief copy.
- L5. Which target repos override `dev-story` or `dev-rework`? Waits: the retirement of
  those roles.

### SOLID check

- **Single responsibility.** Each Owns reads without "and". Restart brief joins two
  texts, but owns one thing: what a replacement conversation opens with.
- **Open/closed.** A third counsel variant, such as an operator desk consult, adds one
  concept and one line in work order's choice.
- **Liskov.** Delegate advisor and self counsel are each a kind of counsel only.
- **Interface segregation.** Work order asks counsel availability one question: is an
  advisor reachable.
- **Dependency inversion.** Work order's Never-knows names the CLI and the model. It
  depends on counsel availability alone.

## 5. Mapping onto the existing system

### Revision log

- R1. Section 2, counsel availability: added after L2 showed no workflow can see the
  delegate set (`workhorse/workhorse/profile.py:100` resolves it inside the engine only).
- R2. Section 2, brief copy: made a flow-owned file after L4 showed the engine overwrites
  `<run>/<node>/prompt.md` on every turn of a node
  (`workhorse/workhorse/runner/ladder.py:53`).
- R3. Section 3, invariant 3: added after the restart brief was found to carry the resume
  note only (`coder/dev/flow.py:139`).
- R4. Section 4, claim 2: restated after the profile showed the dev owner already runs on
  Sonnet under the claude profile (`~/.config/stablemate/config.toml`, `powers.high`).
- R5. Section 2, brief ledger: kept on disk per work item as a map from phase to the
  conversation id its last turn ran on, and cleared when the dev flow starts. The flow
  compares the story's current conversation id against it. No engine signal of a new
  conversation was needed, because the session chain already exposes the id.
- R6. Section 2, brief copy: the engine gained a pure render, `Workflow.render_prompt`,
  that writes no step. The flow needs the brief's text before the turn runs, and the only
  render path before it lived inside the turn itself.
- R7. Section 2, consult record: kept in a per-work-item file keyed by finding id, so a
  decline consulted on an earlier lap stays consulted. The departure audit runs in the build
  state and sends the build back. Only the decline audit runs at settlement, because a
  departure has no finding id for the settlement to check against.

### Parts

| Part | Verdict | Where |
|---|---|---|
| Work order | **Reshape** | `coder/dev/flow.py:159`. One `build` state runs one turn for the whole story at `power="high"` (line 180). It becomes three states. |
| Briefing | **Reshape** | `coder/dev/prompts/dev-story.md` (417 lines) and `dev-rework.md`. One prompt, rendered in full on every lap. |
| Conversation keeping | **Exists** | `story_chain` in `coder/shared/conversation.py`. The engine's chain files in `workhorse/workhorse/sessions.py`. Replacement happens in the ladder (`runner/ladder.py:276`, `:322`). |
| Counsel | **New** | A delegate role in the engine catalog. Audit in the dev flow's check. |
| Helper procedures | **Reshape** | Inline today, inside the owner prompts. They move to `base-library/library/skills/workhorse/`. |

### Concepts

**Work order**

- Phase: **New**, as three states in `coder/dev/flow.py`: `plan`, `build`, `review`.
- Phase strength: **Reshape**. `power="high"` at `coder/dev/flow.py:180` becomes a table
  in the dev package: plan `max`, build `high`, review `high`.
- Phase route: **Reshape**. `check` sends a failure to `build` today. It will send it to
  `review`. `read_operator` returns to `build` (`coder/dev/flow.py:468`). It will return to
  the phase that blocked, carried in its args. A QA send-back today picks `dev-rework`
  (`flow.py:172`). It will enter `review`.
- Phase result: **Reshape**. `DevResult` (`coder/shared/schemas/dev_story.py:41`) stays
  the review phase's result and gains `consults`. The plan phase returns a small
  `PlanResult`: status and notes. The build phase returns a `BuildResult`: status, notes,
  departures, consults.

**Briefing**

- Phase brief: **Reshape**. `dev-story.md` splits into `dev-plan.md`, `dev-build.md` and
  `dev-review.md` under `coder/dev/prompts/`. The shared inputs block moves to a
  `_dev-inputs.md` include. `dev-rework.md` retires: its findings block is the review
  brief's findings block. Three new roles go into `ROLES` (`coder/shared/roles.py:21`).
  `dev-story` and `dev-rework` leave it.
- Follow-up note: **New**, `coder/dev/prompts/dev-follow-up.md`. Rendered on its own node
  id, so the phase node's `prompt.md` keeps the full brief for inspection.
- Brief copy: **New** (revised, R2). The flow renders the phase brief and writes it under
  the run's state dir at `briefs/<work-id>/<phase>.md`. Rendering outside a turn needs an
  engine call (L3). `render_text` in `workhorse/workhorse/templates.py` renders inline
  text. A file-template counterpart exposed on the workflow is **New**.
- Brief ledger: **New**, in `coder/shared/conversation.py` beside `story_chain`. It keeps
  the conversation id it last saw and the phases briefed on it. It persists in the state
  dir, so a resumed run keeps it.
- Brief choice: **New**, a function in the same module. Its input is the ledger and
  `self.session_id(story_chain(slug))` (`workhorse/workhorse/pyflow/engine.py`,
  `session_id`).

**Conversation keeping**

- Conversation identity: **Exists**. Owns and never-knows match.
- Conversation replacement: **Exists, implicit**. The ladder deletes the chain file and
  starts fresh. The id changes on the next turn. Brief choice detects it by comparing ids.
  No engine change. A compaction that keeps the id stays invisible. The pointer in the
  follow-up note covers it (F4).
- Restart brief: **Reshape** (revised, R3). `_rebrief` (`coder/dev/flow.py:139`) returns
  the resume note only. A replacement conversation gets neither the phase's rules nor the
  result schema. The code is wrong here. A replaced build turn today runs with no rules.
  The restart brief becomes the brief copy of the current phase followed by the resume
  note.

**Counsel**

- Advisor: **New**. An `advisor` entry in `ROLES` in
  `workhorse/workhorse/runner/backends/delegates.py:29`, read-only, with instructions to
  answer one design question from the pointers it is given. Its model comes from
  `delegates.advisor` in the profile. When that is unset, it falls back to the profile's
  `max` tier. `delegates_for` today drops a role with no configured model (line 83). The
  fallback is a mismatch with today's rule that only named roles exist. The design wins:
  the operator's config names no delegates at all, so an opt-in advisor would never run.
- Consult trigger: **New**, a section in `dev-build.md` and `dev-review.md`.
- Consult record: **New**, a `Consult` model in `coder/shared/schemas/dev_story.py`.
- Consult audit: **New**, a step in `check` after `_settle` (`coder/dev/flow.py:334`). It
  compares the settlement's `declined` ids (`Settlement.declined`, line 90) and the build
  result's departures with the consult records.
- Counsel availability: **New** (revised, R1). The engine resolves delegates per backend
  and profile (`workhorse/workhorse/profile.py:100`) but tells the workflow nothing. A
  `has_delegate(role)` query on the workflow is **New**. It answers false on copilot and
  cline (`runner/backends/copilot.py:154`, `cline.py:204`).

**Helper procedures**

- Procedure: **Reshape**. New skills in the `stablemate` pack under
  `base-library/library/skills/workhorse/`:
  - `workhorse-coder-review`: the reviewer's brief, now in `dev-story.md`.
  - `workhorse-coder-triage`: the triage and answer-file rules, now in `dev-story.md` and
    `_fix-at-the-cause.md`.
  - `workhorse-coder-docs-writer`, `-docs-reviewer`, `-docs-fixer`: now in
    `document-story.md`.
  - `workhorse-coder-qa-plan`: `_qa-plan-contract.md`, about 5,400 tokens.
- Procedure pointer: **Exists**. `skill_path` with `has_skill` guards
  (`core/stablemate_core/skill_refs.py:159`, `:179`). A missing skill raises
  `MissingSkill` unless the render passes a fallback. The briefs call `skill_path` with
  no fallback, which upholds invariant 4.

### What the existing system has that the design lacks

- **Builder, triager and fixer subagent rows** in the dev prompt's subagent table. Waste
  under this design (claim 6). The build and review owners do that work.
- **`resume_note` rendered into every dev prompt** (`coder/dev/flow.py:190`). Waste on a
  live conversation, which holds the state already. It stays in the restart brief.
- **`review_prefix`, `follow_up_title`, `answers_file` args.** A concept the design
  missed: the review phase's inputs. They move to the review brief unchanged.
- **Body overrides through `agents.yml` `prompts:`** (`coder/shared/roles.py:80`). A
  concept the design missed: a repo-supplied phase brief. Each new role resolves a body
  override by its own name, as today. No design change.

### Lookups

- L1: **Resolved in part.** The codex backend passes `-m` on `exec resume`
  (`runner/backends/codex.py:270`, `:278`). Whether codex honours a changed model on
  resume is not settled by code (A3).
- L2: **Resolved.** No query exists. New, see counsel availability.
- L3: **Resolved.** No file-template render is exposed to a workflow. New, see brief copy.
- L4: **Resolved.** The engine overwrites it. See R2.
- L5: **Unresolved.** No override exists in this repo. Target repos are unknown (A5).

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| The operator's bill | Cost per story | nothing | not measured (A1) | Within +15% of the baseline, with the plan on `max` |
| The operator's wait | Wall time per story, start to ready | nothing | not measured (A1) | Within +20% of the baseline |
| The reviewer | Findings per story from the review | nothing | not measured (A1) | Within one finding of the baseline on the same story |
| The QA judge | Stories QA sends back | nothing | not measured (A1) | No more than the baseline on the same stories |
| The story's checks | Gates, settlement, leftovers and walk decide ready | the existing check in the dev flow | all pass on ready stories | unchanged |
| The ready verdict | Repair laps until green, capped at 3 | `MAX_LAPS` in `coder/shared/owner.py` | 3 | 3, counted across review re-entries |
| The operator desk | Blocks per story, capped at 3 | `MAX_BLOCKS` | 3 | 3, counted across all phases |
| A replaced conversation | Picks up the work | nothing | resume note only (R3) | Opens with the phase brief and the resume note (invariant 3) |
| Stack neutrality | No stack names in prompts | `workflows/tests/coder/test_prompt_stack_neutrality.py` | passes | passes, with the new skills in its scope |
| Repo prompt overrides | A body override for `dev-story` replaces its body | `coder/shared/roles.py:80` | 0 in this repo | Each repo rewrites against the new roles (out of scope) |

The first four rows are enforced by nothing. The design lets none of them go. Each
becomes a measurement in every slice's done-when. Rows one and two have no invariant
owner, because no check can hold a price. The operator agreed in section 1 that the plan
turn costs more.

## 6. Slices

Each slice runs on one real target story, attended, twice (claim 8). Slice 1's first
run is the baseline: the same story on today's code, measured for every row of 5b.

**Slice 1. The plan moves to the strong tier.**
Parts: work order (phase, strength, route), briefing (phase brief for plan, a second
brief holding today's build and review rules).
The dev flow runs `plan` at `max`, then today's remaining work as one turn at `high`, on
the same conversation.
Done when: the plan files exist after the plan turn and before the build turn. The turn
usage shows the strong model on the plan and the cheap one after. The conversation id is
the same on both turns. Every 5b row is re-measured against the baseline and holds.

**Slice 2. Build and review split, and repair laps land in review.**
Parts: work order (review phase, route for failed checks, QA send-backs and operator
answers), briefing (review brief), helper procedures (none yet).
`dev-rework` retires.
Done when: a failed gate re-enters review, not build. A QA send-back on the attended
story enters review. An operator answer returns to the phase that blocked. Every 5b row
holds.

**Slice 3. Follow-up notes.**
Parts: briefing (follow-up note, brief copy, ledger, choice), conversation keeping
(restart brief).
Done when: a second review lap sends a follow-up note under 1,000 tokens. A forced
replacement, done by deleting the chain's session file between laps, opens with the
review brief and the resume note. Every 5b row holds.

**Slice 4. Counsel.**
Parts: counsel (advisor, trigger, record, audit, availability), work order (strength
from availability).
Done when: on claude, a decline on the attended story carries a consult, and the
advisor's turn shows the strong model. A result with a decline and no consult sends the
story back to review with a report naming the finding. On a CLI with no delegates, every
phase runs at `max`. Every 5b row holds.

**Slice 5. Dev procedures become skills.**
Parts: helper procedures (review, triage), briefing (pointers in the review brief).
Done when: the rendered review brief contains no reviewer or triage heading (invariant
5). Each phase brief is under 2,500 tokens. A reviewer subagent's transcript shows it
read the skill file. Every 5b row holds.

**Slice 6. QA and docs procedures become skills, and their laps get follow-up notes.**
Parts: helper procedures (docs writer, reviewer, fixer, QA plan), briefing (follow-up
notes for the QA and docs owners).
Done when: `qa-story` and `document-story` render without their procedure bodies. A
second QA lap and a second docs lap each send a follow-up note. Every 5b row holds on a
story that runs QA and docs.

## 7. Assumptions

1. **Assumption:** a story's cost, wall time, finding count and send-back count on today's
   code can be measured from one attended run per slice.
   **Decided:** slice 1 opens with a baseline run, and every slice compares to it.
   **Basis:** none. No past dev-story run exists on this machine.
   **If wrong:** section 5b's holds-when, every slice's done-when.
2. **Assumption:** the CLI-side compaction the engine cannot see keeps the conversation
   usable, so the owner can follow a pointer back to its brief.
   **Decided:** the follow-up note carries the brief copy's path, with no engine epoch.
   **Basis:** `runner/failure.py:137` says the headless CLI returns on overflow rather than
   compacting, so the engine sees most compactions.
   **If wrong:** section 4, brief choice and follow-up note. An engine-side compaction
   counter would replace the id comparison.
3. **Assumption:** codex honours a changed model when it resumes a thread.
   **Decided:** phase strength works on codex as on claude.
   **Basis:** the backend passes `-m` on resume (`runner/backends/codex.py:278`).
   **If wrong:** counsel availability treats codex as "no tier switch", and codex runs
   every phase at `max`.
4. **Assumption:** a cheap-tier owner asks the advisor when the audit makes it.
   **Decided:** the audit refuses any decline or departure with no consult record.
   **Basis:** the decoder article's failed merge, where the consult was optional.
   **If wrong:** section 3, invariant 2 needs a second trigger, such as plan size.
5. **Assumption:** no target repo relies on a `dev-story` or `dev-rework` body override
   that it cannot rewrite.
   **Decided:** the old roles retire, and an override for them fails loudly at render.
   **Basis:** none in this repo. Target repos unknown.
   **If wrong:** section 5, phase brief. `dev-story` would stay as an alias for the build
   brief for one release.
6. **Assumption:** the plan turn is a small share of a story's tokens, so moving it to
   `max` keeps cost per story within 15%.
   **Decided:** plan at `max`, build and review at `high`.
   **Basis:** the plan files are a few pages. The build and the laps read and write code.
   **If wrong:** section 4, phase strength. The plan would drop to `high` with the advisor
   consulted on the plan's approach.
7. **Assumption:** the stablemate skill pack is installed in every target repo a coder run
   works on.
   **Decided:** procedure pointers have no inline fallback.
   **Basis:** the pack ships with farrier's setup for every repo stablemate drives.
   **If wrong:** section 3, invariant 4 would fail renders on a bare repo. A fallback
   pointing into the stablemate checkout would be needed.
8. **Assumption:** two cache misses per story, one per tier switch, cost less than the
   prompts the change stops resending.
   **Decided:** three turns on one conversation.
   **Basis:** a story with two repair laps resends about 10,600 prompt tokens today. A
   switch rereads the plan transcript once.
   **If wrong:** section 4, between parts. Build and review would merge back into one
   turn.
