# Design: Survey intake — exhaustive discovery for large cross-cutting initiatives

**Status:** Implemented as the author workflow's nested `surveyor` flow — see
`workflows/author/surveyor/docs/WORKFLOW.md`. The author-side change landed in
`load-config.py` (the unit manifest becomes `cfg.surface_manifest` by presence).
**Superseded in one place:** §5's plan to reuse author's intake-time surface-coverage gate.
That gate has since been removed — it ran *upstream* of the seeds that were its own input, so it
could only grade the previous run, and in survey mode its "full" assertion searched a haystack
containing the backlog `emit-artifacts.py` had just written. Exhaustiveness is proved inside the
surveyor instead (`verify-records` → `validate-partition` → `emit-artifacts`), and downstream by
`reconcile-artifacts.py`, `check-story-grounding.py` and `validate-epic-coverage.py`. Read §5 as
history.

**Also superseded:** author's per-story *surface knowledge record* (`gather_knowledge` and its
validate/fix loop), referenced below as the per-unit "note it" idiom, is gone as well. The
okf-builder now derives that surface documentation from the code into the OKF book, so a story
grounds itself by **citing** book node ids rather than by re-gathering the surface. The surveyor's
own finding records — a separate type with their own `openGaps` — are unaffected. Where the text
below leans on knowledge records, read it as the design-time state of the art, not current
machinery.
**Scope:** an author intake flow that emits generated backlog bullets + inventory manifest,
then continues through the normal author epic pipeline.
**Motivating scenario:** "bring accessibility to every UI component of a large codebase" —
an initiative whose work-list is the codebase itself, not a human-curated backlog.

---

## 1. Problem

The author workflow is **backlog-shaped**: it assumes `docs/backlog.md` already enumerates
the work at roughly bullet-per-story granularity, and everything downstream transforms
those bullets into coder-ready artifacts. For a cross-cutting initiative ("make every
component accessible", "i18n-ready everywhere", "migrate every endpoint to the new error
convention") the backlog would contain **one vague bullet**, and discovery would fall to
agent discretion in two places — both of which are the wrong altitude:

- `decompose_epics` is one agent pass over the whole backlog. To decompose "every
  component" it would have to enumerate hundreds of files inside a single context. Agents
  are unreliable at looking at each file of a large ensemble: they sample, generalize,
  and silently drop the tail.
- Per-story surface gathering (`gather_knowledge`, since removed) ran *after* stories exist. It
  deepened known scope; it could never expand it. Work no story points at is never discovered —
  and that is just as true of today's replacement, where the story cites the OKF book.

The result is **discretionary discovery**: the exhaustiveness of the authored plan rests
on an agent's recall instead of on a mechanical fact.

What we actually want to be able to say is: *"for each unit we have, look at what work is
needed and note it — then partition all of that into epics and stories."* No single agent
run can do that faithfully over a large ensemble; a workflow loop can.

---

## 2. What already exists (and must not be rebuilt)

The architecture already contains the answer in miniature; the surveyor is a composition
of existing idioms, not new machinery:

| Existing mechanism | Role it plays in this design |
|---|---|
| `cfg.surface_manifest` (the machine-readable surface inventory author's per-story stages read) | the "one entry per unit of work" artifact shape — at the time limited to human-authored feature docs |
| `select_epic` / `select_story` loop pattern (deterministic select-next script → bounded agent → durable file record → loop, `refuel:` on the unit key) | the resumable "for each X, do Y" engine |
| knowledge records under `cfg.knowledge_dir` *(the idiom at design time; since removed in favour of the okf-builder's book)* | durable, accumulating, per-surface derived truth — the per-unit "note it" file |
| operator gates + bounded rework/resolve counters | escalation for units that cannot be assessed |
| `reconcile-artifacts.py` (scope-drop vs git baseline) | the pattern for detecting silent shrinkage of a frozen list |
| farrier-installed skills (universal contract skill + per-stack skill, e.g. `stablemate-ui-accessibility` + a per-stack a11y skill) | the channel through which stack-specific mechanics reach generic prompts |
| `sourceBullet` traceability (seed → backlog line) | the chain that will extend down to unit → finding |

---

## 3. Design principles

- **Discretion only where it is cheap and auditable.** Two agent judgments are allowed:
  the planner's granularity call and each unit's assessment. Everything that makes the
  exhaustiveness claim — enumeration, the loop, coverage — is a script.
- **The planner decides the rule; a script materializes the list.** An agent must never
  emit the inventory itself (that re-introduces sampled-enumeration one stage earlier).
  It emits enumeration rules; glob/command expansion makes the list complete *by
  construction*.
- **Project-generic, like author.** The workflow YAML, scripts, and prompts contain zero
  stack knowledge and zero concern knowledge. Stack mechanics ride in through
  farrier-installed skills; the concern rides in through a rubric document. The
  surveyor's only project-facing input is the rubric.
- **Compression before synthesis.** Partitioning into epics happens over the finding
  *records*, never over the code. A few hundred files don't fit a planning context; a few
  hundred structured findings do.
- **Author stays the owner.** The surveyor emits author's *existing* input contract (a
  generated backlog + an inventory manifest). Author then runs its normal epic pipeline
  unchanged; the "nothing was dropped" proof lives in the surveyor's own
  `verify-records` → `validate-partition` → `emit-artifacts` chain.

---

## 4. The surveyor flow

An author subflow, selected with `mode: "survey"`. Pipeline:

```
load_config → plan_units → expand_inventory (freeze) →
  ┌────────────────────────────────────────────────┐
  │ select_next_unit → assess_unit → validate_record│   loop until inventory empty
  │        ↑  (split / blocked escapes)     │       │
  │        └────────── mark done ←──────────┘       │
  └────────────────────────────────────────────────┘
→ verify_records → partition_findings → emit_backlog+manifest → author epic pipeline
```

### 4a. `plan_units` — the granularity planner (agent, one bounded judgment)

Reads the repo layout and the rubric, **samples** a few candidate units, and outputs
enumeration rules with a granularity verdict — e.g. *"folder-per-unit under
`src/lib/components/` (component + test + stories are one unit), file-per-unit under
`src/routes/`"*. Mixed granularity is first-class, not a compromise. The prompt is fully
generic: "given this repo and this rubric, decide what a unit is."

Precedence (same idiom as research's program selection): **explicit config override beats
the planner** — for the day the planner misjudges a repo and the operator wants to pin the
rules without editing prompts. For units that are not files at all (API endpoints, DB
tables, CLI commands), the config/planner may supply a *command* that emits the unit
list; the workflow depends only on the inventory contract, never on how it was produced.

### 4b. `expand_inventory` — deterministic materialization + freeze (script)

Expands the rules into the inventory file: one entry per unit, `{id, path, kind, status}`.
The inventory is **durable and committed** (the survey's analog of `docs/epics/index.md`)
and **frozen once built**: a resumed run consumes the existing list and never re-plans —
otherwise a resume could produce a *different* list and the coverage claim silently
breaks. Units that vanish from the inventory without a finding record are a detectable
drop (reconcile-style gate), not silent shrinkage.

### 4c. The per-unit loop — loop-until-empty (existing idiom verbatim)

- `select_next_unit` (script): first inventory entry without a completed record;
  `has_unit: no` exits the loop. The empty list **is** the coverage proof — coverage
  becomes structural, not a post-hoc check.
- `assess_unit` (agent, bounded, can run below `power: high` — it assesses, it doesn't
  author): prompt embeds the unit's path/kind + the rubric; context is one unit, not the
  ensemble. Emits one finding record.
- **Self-healing granularity** — two escape statuses instead of global re-planning:
  - `split`: a script replaces a too-big folder entry with its children (inventory grows,
    loop continues);
  - `blocked`: recorded as an open gap (`openGaps`) and routed to the standard operator gate —
    never a bare shrug.
- `validate_record` (script) + bounded fix loop (mirrors `validate_story` → `rework_story`).
- `mark_done` (script) flips the inventory entry's status. `refuel:` on the unit id so
  gas replenishes on genuine forward progress. Fully resumable across runs.

### 4d. Finding record — concern-neutral schema

```yaml
unit: src/lib/components/DatePicker/   # id from the inventory
kind: folder
findings:
  - description: ...
    remediation_pattern: <slug>        # proposed by assess agents, normalized by the partitioner
    effort: trivial | small | substantial
    evidence: ...                      # file:line refs, observed behaviour
status: assessed | clean | blocked
```

Nothing stack-shaped, nothing concern-shaped. `remediation_pattern` values are
**emergent per initiative** (proposed by assess agents, normalized during partitioning),
keeping the schema closed while the taxonomy stays open.

### 4e. `partition_findings` — clustering over records (agent, high power)

Reads the finding records — *not* the code — and clusters into epic/story candidates.
**Granularity of the clusters is the real intelligence problem**: N units must not become
N stories. `remediation_pattern` is what makes this tractable — e.g. one mechanical story
carrying a checklist of 40 units sharing "icon button missing accessible name", alongside
one dedicated story per genuinely gnarly unit. A deterministic gate asserts every
non-clean record maps into ≥1 cluster.

### 4f. Emit author's contract

- generated `docs/backlog.md`: one `[id]`'d bullet per cluster (grouping/ordering hints
  in the bullet text);
- generated inventory manifest (unit-level), taking the role `cfg.surface_manifest`
  plays today.

Then **author continues** through the epic pipeline unchanged. The existing
`sourceBullet` chain yields end-to-end traceability:
**unit → finding → backlog bullet → seed → story**.

---

## 5. Changes required in author (small, additive)

1. **Generalize the manifest source.** `cfg.surface_manifest` currently assumes feature
   docs (screens). It must accept a survey-produced unit manifest as an alternative source
   — same contract, different producer. Opt-in by presence, as today. *(Landed in
   `load-config.py`.)*
2. **Nothing else.** The epic split, story split, per-story research, validation,
   grounding, audit, reconcile, integrity, and operator machinery all apply as-is.

> **Superseded.** This section originally also proposed running author's intake-time
> surface-coverage gate in `coverage_mode: "full"` over the emitted manifest. That gate is
> gone (see the Status note at the top): it sat upstream of its own inputs, and over a
> survey it would have checked the backlog against the backlog. The exhaustiveness proof
> belongs upstream, in §4's `verify-records` → `validate-partition` → `emit-artifacts`
> chain, which asserts it against the *frozen inventory* rather than against author's
> output.

---

## 6. Verification at initiative level

Coder QA proves each story; nothing today proves "every unit is now compliant." Because
the survey is idempotent, **re-running it is the done-check**: after the epics merge,
re-survey and diff the finding records before/after. This matters most for the mechanical
checklist-stories, where a coder run is likeliest to quietly skip an item.

---

## 7. Ostler as the spine (follow-up, not a blocker)

A `finding` / `inventory` concept type would let `ostler doctor` validate the
unit → finding → seed → story chain the same way it already catches dangling seeds.
Without it, the survey layer is a second, unvalidated doc graph beside the one that was
made self-checking. `ostler todo` already provides the queue mechanics.

---

## 8. Out of scope / explicitly rejected

- **Pushing exhaustive discovery into `decompose_epics`** — keeps the whole ensemble in
  one context; the original failure mode.
- **Planner-emitted inventories** — an agent listing hundreds of paths reintroduces
  sampled enumeration; only rule expansion is trusted for completeness.
- **Per-project survey config as a requirement** — the planner makes config optional;
  config remains only as an override.
- **Concern-specific schema fields or prompts** — the rubric document and the skill
  channel carry all concern/stack specificity.
