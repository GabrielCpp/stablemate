# Design: Survey intake — exhaustive discovery for large cross-cutting initiatives

**Status:** Implemented as the author workflow's nested `surveyor` flow — see
`workflows/author/surveyor/docs/WORKFLOW.md`; the author-side changes landed in
`load-config.py` / `build-inventory.py` / `verify-surface-coverage.py` (unit-manifest
source, opt-in by presence).
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
- `gather_knowledge` is per-story and runs *after* stories exist. It deepens known scope;
  it can never expand it. Work no story points at is never discovered.

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
| `build_inventory` + `verify_surface_coverage` (`coverage_mode: "full"`) | mechanically-built inventory + deterministic "everything is covered" gate — the exact shape needed, currently limited to human-authored feature docs |
| `select_epic` / `select_story` loop pattern (deterministic select-next script → bounded agent → durable file record → loop, `refuel:` on the unit key) | the resumable "for each X, do Y" engine |
| knowledge records under `cfg.knowledge_dir` | the idiom for durable, accumulating, per-surface derived truth — the per-unit "note it" file |
| operator gates + bounded rework/resolve counters | escalation for units that cannot be assessed |
| `reconcile-artifacts.py` (scope-drop vs git baseline) | the pattern for detecting silent shrinkage of a frozen list |
| farrier-installed skills (universal contract skill + per-stack skill, e.g. `stablemate-accessibility` + `stablemate-htmx-accessibility`) | the channel through which stack-specific mechanics reach generic prompts |
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
  with `coverage_mode: "full"`, and its existing gate proves nothing was dropped.

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
  - `blocked`: recorded as an open gap and routed to the standard operator gate
    (mirrors `openGaps` in knowledge records).
- `validate_record` (script) + bounded fix loop (mirrors
  `validate_knowledge` → `fix_knowledge`).
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

Then **author continues** through the epic pipeline with `coverage_mode: "full"`. The existing
`sourceBullet` chain yields end-to-end traceability:
**unit → finding → backlog bullet → seed → story**.

---

## 5. Changes required in author (small, additive)

1. **Generalize the manifest source.** `build_inventory` / `verify_surface_coverage`
   currently assume feature docs (screens). They must accept a survey-produced unit
   manifest as an alternative source — same contract, different producer. Opt-in by
   presence, as today.
2. **Nothing else.** The epic split, story split, per-story research, validation,
   grounding, audit, reconcile, integrity, and operator machinery all apply as-is. The
   `coverage_mode: "full"` design comment ("the migration / greenfield-buildout
   assertion") already anticipated exactly this use — it only ever lacked a code-derived
   inventory to run against.

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
