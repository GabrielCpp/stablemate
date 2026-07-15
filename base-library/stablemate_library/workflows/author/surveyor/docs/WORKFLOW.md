# Surveyor Flow

Exhaustive discovery for large cross-cutting initiatives — "bring accessibility to every
UI component", "i18n-ready everywhere", "migrate every endpoint to the new error
convention" — where the work-list is the codebase itself, not a human-curated backlog.
Design rationale: `../../docs/survey-intake-design.md`.

The surveyor is a nested flow inside the **author** workflow. It emits author's *existing*
input contract, then the same author run continues through the epic pipeline with
`coverage_mode: "full"` so author's own gates prove nothing was dropped:

- **generated backlog bullets** — one `[survey-<cluster-id>]` bullet per finding cluster,
  written into a marker-fenced `## Survey findings` section of `docs/backlog.md`
  (everything outside the fence — a human backlog, coder's `## Filed by coder` section —
  is untouched, and re-emitting replaces the fenced section idempotently);
- **the unit manifest** (`docs/survey/unit-manifest.json`) — the unit-level surface list
  author's `verify-surface-coverage.py` consumes (the role `cfg.surface_manifest` plays),
  each unit carrying the bullet ids that cover it.

Traceability chains end-to-end: **unit → finding record → backlog bullet → seed
(`sourceBullet`) → story**.

## The one project-facing input: the rubric

`docs/survey/rubric.md` (override with `--params '{"rubric":"..."}'`) defines the concern:
what counts as a finding, what "clean" means, and which repo skills (installed by farrier,
e.g. a `*-accessibility` pair) the assessors must read. The workflow YAML, scripts, and
prompts contain zero stack knowledge and zero concern knowledge — swap the rubric and the
same workflow surveys a different concern.

## Pipeline

```
load_config → check_inventory →
  plan_units (agent, ONE bounded judgment: enumeration RULES, not the list)
  → expand_inventory (script: rules → inventory.json, complete by construction, FROZEN)
  ┌──────────────────────────────────────────────────────────────┐
  │ select_unit → assess_unit → validate_record (+ bounded fix)  │  loop until no
  │      ↑            │ split → split_unit (inventory grows)     │  pending unit
  │      └── mark_unit ┴ blocked → recorded gap, loop continues  │
  └──────────────────────────────────────────────────────────────┘
  → verify_records (deterministic coverage gate; operator gate on failure)
  → partition_findings (agent, clusters over RECORDS) → validate_partition (lossless gate)
  → emit_artifacts (backlog section + unit manifest) → return to author epic pipeline
```

Discretion only where it is cheap and auditable: two agent judgments carry weight (the
planner's granularity call, each unit's assessment — plus the partitioner's clustering,
which a deterministic gate bounds). Everything that makes the exhaustiveness *claim* —
enumeration, the loop, coverage — is a script.

## Key mechanics

- **Planner precedence** (`check-inventory.py`): a frozen `inventory.json` beats
  everything (a resume never re-plans — a different list would silently break the
  coverage claim); an existing `units.yml` (operator-pinned) beats the planner; the
  planner runs only when neither exists. For units that are not files (endpoints, DB
  tables), a rule may supply a `command` whose stdout lines are the units.
- **Loop-until-empty** (the author `select_epic`/`select_story` idiom): the empty pending
  set IS the coverage proof. `refuel: unit_id` tops up workhorse's gas tank only on
  genuine forward progress, so a non-advancing loop halts loudly.
- **Self-healing granularity**: an assessor that cannot faithfully assess a too-big folder
  returns `split`; `split-unit.py` replaces the entry with its children (split lineage
  stays detectable — children extend the parent's path) and the loop continues. No global
  re-planning.
- **Nothing per-unit halts the survey**: a `blocked` unit (or a record that never
  validates) is durably recorded as an open gap and the loop advances;
  `verify-records.py` re-surfaces every gap at the coverage gate, where the operator (or
  the auto-resolver) either fixes the precondition and re-pends the unit or records
  `disposition: accepted` in the record. Shrinkage vs the committed inventory with no
  split lineage is flagged reconcile-style.
- **Compression before synthesis**: the partitioner reads the finding *records*, never
  the code. `remediation_pattern` slugs (proposed by assessors, normalized by the
  partitioner) let N units sharing one fix shape become ONE mechanical checklist story,
  while gnarly units get dedicated clusters. `validate-partition.py` asserts no assessed
  unit falls out.

## On-disk artifacts (all durable, committed by the parent author run)

| Path | What |
|---|---|
| `docs/survey/rubric.md` | the concern definition (human-authored, REQUIRED) |
| `docs/survey/units.yml` | enumeration rules (planner-authored or operator-pinned) |
| `docs/survey/inventory.json` | the frozen unit list `{id, path, kind, status}` |
| `docs/survey/findings/<slug>.md` | one finding record per unit (YAML front-matter) |
| `docs/survey/partition.yaml` | the epic/story clusters |
| `docs/survey/unit-manifest.json` | emitted manifest for author's full-coverage gate |
| `docs/survey/_survey-context.md` | operator Q&A for blocked gates |
| `docs/backlog.md` | gains the marker-fenced `## Survey findings` section |

## Running It

Run author in survey mode:

```bash
make agent-native WF=author PARAMS='{"mode":"survey","rubric":"docs/survey/rubric.md"}'
```

For a baseline-vs-current product parity inventory, use the sibling `parity-surveyor` flow through
author's `parity-survey` mode. It freezes one unit per baseline surface, compares each against the
current OKF books, and emits one bullet per uncovered, not-already-owned surface. It deliberately
stops after backlog emission; run normal author epic mode after reviewing the bullets:

```bash
AGENT_REPO_DIR="$PWD" timeout 7200 workhorse run author parity-surveyor --cli opencode \
  --params '{"baseline_inventory":"docs/legacy/screens/inventory.json","target_features":"docs/features"}'
```

The parent author run owns branching, final validation, commit, and PR. In survey mode,
author automatically runs its surface-coverage gate in `full` mode against the emitted
unit manifest.

## Initiative-level done-check

The survey is idempotent: after the epics merge, delete `docs/survey/inventory.json` and
the findings (or run in a fresh clone on the merged branch), re-run author in survey mode
with the same rubric, and diff the finding records before/after. Findings that survived a coder run
— most likely on the mechanical checklist stories — show up as still-`assessed` units.
Note the flip side: re-emitting regenerates the fenced backlog section, so re-surveying
*mid-initiative* (after author pruned consumed bullets but before the fixes merged) will
re-list still-present findings; do the done-check after the work lands.

## Operator gates

Same machinery as author: `operator_mode: "auto"` (default) puts a high-effort resolver
in front of every gate (plan, coverage, partition), bounded by per-gate resolve/rework
counters, escalating to a halting `await-operator.py` (inotify-resumable, groom-visible)
only when it genuinely cannot proceed; `"human"` halts at every gate.
