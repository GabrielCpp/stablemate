# Author Workflow Documentation

The **author** workflow is the producer counterpart to the **coder** workflow. Coder *consumes*
`docs/epics/*` and writes code; author *produces* `docs/epics/*` from a high-level feature
backlog, emitting exactly the artifact contract coder requires.

It exists because epics written ad-hoc in one shot were unreliable — judged against the wrong
source-of-truth, self-certified without evidence, or too coarse to test. Author replaces that
with a disciplined, gated pipeline and two deterministic validators.

## Modes

The author workflow has three modes, dispatched at `decide_mode` on the `mode` var (mirroring the
coder workflow's mode dispatch):

- **`epic`** (default) — the full pipeline: decompose the whole backlog into epics, write each
  epic, split it into stories, write+validate every story, validate epic coverage. Unchanged.
- **`survey`** — for complex/cross-cutting bullets whose work-list is the codebase itself. It runs
  the nested `surveyor` flow first to generate backlog bullets plus `docs/survey/unit-manifest.json`,
  then continues through the normal epic pipeline with the coverage gate forced to `full`.
- **`story`** — turn **one bullet** into a single coder-ready story appended to an **existing
  epic of your choice**, then stop. It runs the same per-story pipeline (gather knowledge →
  validate → write → validate) but skips epic decomposition, epic write, story split, and
  whole-epic coverage. `story_setup` (`scripts/seed-story.py`) appends one `seed.json` item +
  one `dependencies.json` story entry (the same contract `split-stories` emits) surgically — it
  never re-runs the split, so sibling stories are untouched. It is idempotent (a rerun reuses the
  story already covering the bullet). Story mode **requires the epic to already exist** and
  hard-fails otherwise — it appends to an epic, it never creates one.

## Inputs

```bash
make agent-native WF=author                                  # epic mode; reads docs/backlog.md
make agent-native WF=author PARAMS='{"backlog":"docs/other.md"}'   # override backlog
# survey mode: exhaustively discover work from code units, then author the generated backlog
make agent-native WF=author PARAMS='{"mode":"survey","rubric":"docs/survey/rubric.md"}'
# story mode: author ONE bullet into an existing epic
make agent-native WF=author PARAMS='{"mode":"story","epic":"<epic-slug>","bullet":"<[id] or text>"}'
```

- `mode` (default `epic`) — `epic` (whole backlog), `survey` (survey first, then whole backlog), or
  `story` (one bullet → existing epic).
- `epic` (story mode, required) — target epic slug under `epics_dir` (must already exist).
- `bullet` (story mode, required) — a backlog `[id]` (reused verbatim, then pruned on success) **or**
  literal bullet text (a stable kebab id is derived; nothing is pruned).
- `backlog` (default `docs/backlog.md`) — repo-relative path to a markdown bullet list of features.
- `epics_dir` (default `docs/epics`).
- `rubric` / `survey_dir` (survey mode) — concern definition and durable survey artifact directory.

The backlog is a **live worklist**: when an epic passes coverage validation (fully authored), its
consumed bullets are pruned from the backlog by `prune-backlog.py` (matched via each seed item's
`sourceBullet`), so the file shrinks to the outstanding scope — the same idea as coder pruning
finished epics from `epics-todo.json`.

`load-config.py` reads `agents.yml` `template.*` for path conventions (`knowledge_dir`,
`features_dir`, `surface_manifest`, `mockup_dir`). The source of truth is always the **OKF graph
via ostler**: every surface is grounded against the ostler-managed planning docs (feature docs,
knowledge records, epics/stories), and ostler owns id allocation (the prefix is derived from the
repo name). Any repo-specific grounding aid beyond that lives in the repo's author *flavor*
prompts, never baked into this shared library.

**Repo prompt flavors.** Any base prompt can be extended by the launching repo without forking the
shared workflow: drop a same-named override at `<repo>/.agents/flavors/<workflow>/<node>.md` that
`{% extends "prompts/<node>.md" %}` and fills the base's named extension blocks (e.g.
`repo_authoring_rules` in `write-story.md`, `repo_review_rules` in `review-coverage.md`). The base
engine (workhorse) renders the override automatically when the file is present; absent ⇒ the base
renders unchanged (the blocks extend to nothing). This keeps repo-specific authoring/review rules —
like a legacy-parity-matrix requirement — owned by the repo, not baked into the shared library.

**Running on another CLI (Codex/Copilot).** The agent backend is chosen with `AGENT_CLI`
(`claude` default | `codex` | `copilot`); the launcher checks that CLI is on PATH and forwards it
to workhorse:

```bash
make agent-native AGENT_CLI=copilot WF=author     # native runs honour AGENT_CLI
```

Per-node `model:` is CLI-specific — `model: { claude: opus, codex: "@gpt-5.5" }` (copilot omitted
→ its own default). A bare `model: opus` would apply to every backend. To resolve `instruction_ref`
to the right adapters, enable the assistant in `agents.yml` (`agents: { copilot: true }`) and
`make agent-install`; that emits `.agents/agents-context.copilot.json` (skills → `.github/skills`),
which the launcher/workhorse select by `AGENT_CLI`. The Copilot CLI must be installed + authed and
runs fully autonomous (`--allow-all-tools --no-ask-user`) — prefer a scratch branch. The Docker run
path remains Claude-oriented for now.

**Availability vs. registration.** Workflows run directly from the library
(`WORKFLOW_DIR ?= $(AGENTS_DIR)/workflows/$(WF)`), so `make agent-native WF=author` works in any
repo whose context manifest already includes the skills these prompts reference
(process-story-docs, process-write-epics-and-stories, and — for fidelity — the repo's
legacy-visual-capture overlay). Listing `author` under the repo's top-level `workflows:` in
`agents.yml` *registers* it in the generated `agents.mk` "Installed workflows" list, but farrier
picks the default `WF` as the **alphabetically first** registered workflow — so registering
`author` flips a repo's no-arg default away from `coder`. Register it only where author should be
(or share) the default; otherwise run it explicitly with `WF=author`.

## Control structure (nested loops, two validation altitudes)

```
load_config
  └─ SURVEY INTAKE     [survey] generate backlog bullets + unit manifest, then continue as epic
  └─ INTAKE            build_inventory  compile docs/features/*.md → inventory.json (derived)  [epic]
  └─ SURFACE COVERAGE  verify_surface_coverage  grounding(default): claims ⊆ feature set
                          ↑ or full (coverage_mode=full): backlog covers every in-scope surface
                          ↑ fail → operator gate (add a feature doc / bullet, or mark out of scope)  [epic]
  └─ EPIC SPLIT        decompose_epics → review_epics ──(approved)─┐
                          ↑ needs_rework→rework  ↑ blocked→await    │
  ┌──────────────────────────────────────────────────────────────┘
  PER EPIC: select_epic ──(no)→ validate_artifacts → done
     │ (yes)
     ├─ 2a write_epic            epic.md + seed.json (in-scope items, RESEARCHED per item)
     ├─ 2b split_stories         dependencies.json skeleton (sized from the seed research)
     ├─ 2c PER STORY: select_story ──(no)→ 2d
     │        │ (yes)
     │        ├─ gather_knowledge research surface; read feature-doc journeys; record chrome/transient
     │        ├─ write_story      ACs incl. journey + context-conditional chrome + transient feedback
     │        ├─ validate_story   HARD structural: shape + status line + no open decisions
     │        ├─ check_story_grounding  gate: seedItems valid + knowledge record + journey recorded
     │        └─ audit_story      adversarial: refute coder-readiness ──pass→ next story / fail→ rework
     │                              (rework reads the attempts ledger — don't repeat failed approaches)
     └─ 2d validate_coverage      HARD: seed coverage + acyclic + slug==folder
            └─ review_coverage    LLM adequacy: "too few / too coarse?" ──ok→ next epic
```

Every produce stage has a bounded rework loop (`max_reworks = 3`) and an on-demand operator gate.
A `validate_story` failure feeds `rework_story` and, when exhausted or genuinely blocked, the
operator gate. Authoring/review agent nodes run at `effort: high`; the high-value authoring nodes
(`decompose_epics`, `split_stories`, `write_story`, `review_coverage`) and the verification
resolvers run at `effort: xhigh`.

**Research is two-tier, not skipped.** `write_epic` researches each seed item in the codebase and
records `currentState` / `legacySurface` / `backing` / `prerequisites` / `notes` — the detail
`split_stories` uses to size and sequence stories. `write_story` then researches that one surface
**in full depth** and captures old-side evidence. Implementation-level planning is coder's `plan`
stage; author's job is a well-scoped, evidence-grounded story, not the build plan.

## The two validators (why epics can't be "incomplete" anymore)

- **`validate-story.py`** (per story) — the **bare-minimum** contract: `story.md` has a
  `- **Status**:` line (coder's selector parses it), a non-empty `## Context`, and a non-empty
  `## Acceptance Criteria`; and the story carries **no open questions / unresolved decisions**
  (markers like `Decision to surface`, `accept, or tune`, `TBD`, `TODO`, `decide whether…` are
  rejected — the writer must resolve the call or escalate via `blocked`). Nothing more is required:
  depth (plan, file lists, dependencies, QA method) is the **coder's** job, which iterates
  implementation and files follow-ups; over-specified stories shipped defects unnoticed and just
  rot. Repo-specific authoring rules live in that repo's author *flavor*, not this generic gate.
- **`validate-epic-coverage.py`** (per epic) — `dependencies.json` parses & is acyclic, slug ==
  folder, paths exist, and **every `seed.json` item id is covered by some story's `seedItems`**.

An LLM reviewer adds the judgment a script can't:
- **`review_coverage`** (per epic) — are the stories granular enough, or too coarse to implement
  and assess? A repo flavor can extend this reviewer's rubric (the `repo_review_rules` block) with
  repo-specific checks.

## Authoring-quality gates (the author analog of the coder's QA gate + auditor)

Three more layers harden authoring at full-site scale — each mirrors the coder QA stage's
"deterministic gate → adversarial auditor → bounded loop" pattern:

- **The feature set is the human source; the manifest is derived.** A human writes one prose
  feature doc per screen under `template.features_dir` (default `docs/features`) — a `##
  Title (route: …, area: …)` heading plus behavior bullets; `(out-of-scope)` marks a screen as
  not-in-scope. **`build-inventory.py`** (epic mode, intake) compiles those docs into
  `template.surface_manifest` (default `docs/features/inventory.json`) so nobody hand-writes the
  JSON. Non-lossy merge: undeclared fields a manifest already carries (`mockup`, `role`) are
  preserved. Opt-in by presence: no feature docs ⇒ **skip** (existing manifest untouched). The
  feature set is *living* — `gather_knowledge` may append a newly-discovered journey/behavior to a
  documented screen's doc (additive, marked), and the next intake picks it up; it never invents a
  doc for an undocumented screen (that's an `openGaps[]` operator decision).
- **`verify-surface-coverage.py`** (epic mode, after intake) relates the authored work to the
  feature set in one of two modes, because the backlog is not always a full rewrite:
  - **grounding** (default, always-on): every surface the work *claims to touch* (a seed's
    `legacySurface`, a knowledge record's `surface`/`route`) must exist in the feature set —
    catches **phantom scope** without ever flagging an untouched screen, so an incremental backlog
    is not forced to re-cover the whole app.
  - **full** (opt-in, `--params '{"coverage_mode":"full"}'`): the **migration / greenfield-buildout**
    assertion — every in-scope manifest surface must be covered by some backlog bullet/epic/story/
    knowledge record. This is the mode for a "migrate the whole app" backlog.

  Opt-in by file presence: no manifest on disk ⇒ a clean **skip**. A surface marked
  `capture:false` / `optional:true` is out of scope. A failure routes to the operator gate.
- **Feature-doc / user-journey grounding** (`gather-surface-knowledge.md` + `write-story.md`) —
  when `template.features_dir` (default `docs/features`) exists, `gather_knowledge` reads the
  surface's feature doc and records its **user journeys** (`journeys[]`) plus **context-conditional
  chrome** (`chromeContext`) and **transient feedback** (`feedbackKind`). `write_story` then must
  include a journey-level AC, a presence/absence AC per context-conditional element, and an
  appear-then-disappear AC for transient feedback — so e.g. a picker that differs inside vs. outside
  a project becomes a *planned* check, not luck at QA. **Greenfield reference:** for a genuinely
  new screen, the visual reference is the **design mockup** from the manifest entry's
  `mockup` field (under `template.mockup_dir`, default `docs/design`).
- **`check-story-grounding.py`** (gate) + **`audit-story.md`** (adversarial) — after the structural
  `validate_story` passes, a thin deterministic gate confirms the story *can* be grounded
  (its `seedItems` exist; a knowledge record covers the surface; and, when feature docs are
  configured, a journey was actually recorded), then a skeptical auditor tries to **refute
  coder-readiness** (each AC observable+verifiable+grounded, no hidden decisions, journey-complete).
  Either failing re-enters the **existing** bounded story rework loop (no new counter/gate).

## Attempts ledger (Arbor-inspired negative-constraint memory)

The bounded rework loop used to carry only the *latest* failure into the next attempt, so a
reworker could re-try an approach that already failed. `record_attempt` (`scripts/ledger.py`)
appends each failed attempt to `<story_dir>/attempts.md` and feeds the full ledger into
`rework-story.md` as `prior_attempts` — the negative constraints the next rework must not repeat.
It is a plain tracked markdown file (no store), idempotent on resume, and never halts the run.

## Operator interaction — on-demand only (no approval gate)

There is **no mandatory approval halt**. When any producer returns `status: blocked`, the matching
`await-operator.py` node records the questions in a `context.md` (`<epics_dir>/_author-context.md`
for the epic split, `<epic_dir>/context.md` per epic, `<story_dir>/context.md` per story) and
HALTS (exit 2). The operator answers inline, sets `STATUS: ANSWERED`, and re-runs; the producer
re-reads its context and continues. Same resumable state machine as coder's `await_operator.py`
(ANSWERED→CONSUMED, re-arm on re-block). Bounded rework loops escalate to the same gate.

### Non-blocking operator feedback (per story)

Separate from the blocking gate above, the per-story loop also polls for **mid-flight feedback
that never pauses the run**. After a story passes validation, `check_story_feedback`
(`scripts/check_feedback.py`, always exits 0) reads
`<story_dir>/feedback.md`: a human can drop it at any time while the run is busy. With feedback it
routes ONE rework pass through `rework-story.md` (`apply_story_feedback`, feedback as required
changes) then re-validates; with none it advances to the next story. The inbox uses the same
`STATUS: NEW → CONSUMED` machine as the coder feedback checkpoints, so each drop reworks once and is
bounded; it is consumed at the next checkpoint the run reaches (no live polling). Orthogonal to the
`context.md` operator gate. (A coverage-stage checkpoint, before `prune_backlog`, is a natural
future extension.)

## Emitted contract (what coder consumes)

| Artifact | Shape |
|---|---|
| `docs/epics/epics-todo.json` | ordered JSON array of epic folder names |
| `docs/epics/<epic>/epic.md` | goal / why / method (source-of-truth) / scope / acceptance |
| `docs/epics/<epic>/seed.json` | `{epic, items:[{id, summary, sourceBullet, currentState, legacySurface, backing, prerequisites, notes, status}]}` (author-only; the research fields feed story-split + per-story writing) |
| `docs/epics/<epic>/dependencies.json` | `{stories:[{slug, path, dependencies, seedItems, …}]}` acyclic, slug==folder |
| `docs/epics/<epic>/stories/<slug>/story.md` | bare-minimum: `## Implementation Status` (`- **Status**: Not started`) + `## Context` + `## Acceptance Criteria` (observable, user-facing) |
| `docs/epics/<epic>/stories/<slug>/evidence/old-{1280,390}.png` | fidelity mode: captured old-side layout |

`seed.json` and `seedItems` are author-only bookkeeping (coder ignores them); they drive the
coverage validator so no scope item is silently dropped.

## Scripts

| Script | Role |
|---|---|
| `load-config.py` | read `agents.yml`, validate backlog exists → `cfg` |
| `init_counter.py` / `incr_counter.py` | generic bounded-loop counters (key as arg) |
| `select-epic.py` | next epic needing authoring |
| `select-story.py` | within an epic, next story whose `story.md` is missing/placeholder |
| `validate-story.py` | hard per-story structural validator |
| `build-inventory.py` | compile human feature docs (`docs/features/*.md`) → derived `inventory.json` |
| `verify-surface-coverage.py` | grounding(default) / full(opt-in) site-surface gate (opt-in by manifest presence) |
| `check-story-grounding.py` | thin grounding pre-gate before the story auditor |
| `validate-epic-coverage.py` | hard per-epic coverage + graph validator |
| `validate-artifacts.py` | final global coder-consumability check |
| `prune-backlog.py` | remove a fully-authored epic's bullets from the backlog (live worklist) |
| `ledger.py` | append-only attempts ledger (negative-constraint memory for rework) |
| `board.py` | read-only status board over the file model (see tooling below) |
| `await-operator.py` | resumable on-demand recorded-Q&A gate (blocking) |
| `check_feedback.py` | non-blocking per-story feedback poll (`feedback.md`; never halts) |

`load-config.py` ships these convention defaults (a repo overrides via `agents.yml` `template.*`):
`surface_manifest` (`docs/features/inventory.json`), `features_dir` (`docs/features`), `mockup_dir`
(`docs/design`). Each stays inert until the referenced file exists on disk.

## File-native tooling (no service, no DB)

The git-tracked files are the single source of truth; two thin helpers sit on top (generated into
`.agents/agents.mk` by farrier — `make agent-install`):

- `make agent-status` — a read-only **status board** (`scripts/board.py`): walks `epics-todo.json`
  → `dependencies.json` → each `story.md` `**Status**` line and prints epic → story → status with
  totals (and open-backlog count). `BOARD_ARGS='--json'` for machine output. Starts no daemon,
  writes nothing.
- `make agent-chain` — runs **author then coder in sequence** (one call instead of two);
  `AUTHOR_PARAMS` / `CODER_PARAMS` optional.

## Tests

`python3 -m pytest tests/` — subprocess unit tests of every script against sandbox fixtures
(`AGENT_REPO_DIR` pointed at a tmp dir, the same way the local-worker runs them). No workhorse
runtime required.

## Diagram

`docs/author-workflow.dot` (regenerate SVG with `dot -Tsvg author-workflow.dot -o author-workflow.svg`).
