---
agent: agent
---

# Partition the finding records into epic/story candidates

You are the **partitioner** of the surveyor workflow. Every unit has been assessed and its
findings sit in structured records. Cluster those findings into the epic/story candidates
the author workflow will turn into coder-ready work. You read the **records only, never
the code** — compression before synthesis is what makes a few hundred units fit one
planning context. If a record seems wrong, that is a survey problem to flag, not a reason
to go read the codebase.

## Inputs (authoritative — use exactly as given)

- Finding records: `{{ workhorse_var('findings_dir') }}/*.md` — read EVERY record whose
  status is `assessed`. (`clean` and `blocked` records carry no remediation work.)
- Inventory: `{{ workhorse_var('inventory') }}` — the frozen unit list (ids you must use).
- Rubric: `{{ workhorse_var('rubric') }}` — for the initiative's own sense of priority.
- Operator context: `{{ workhorse_var('context_path') }}` — read it if it exists; it may
  carry operator answers to earlier questions.
- Write the partition to: `{{ workhorse_var('partition_path') }}`

{% if partition_errors %}
## Rework — the deterministic gate rejected the previous partition

Fix exactly these problems (edit the partition file; do not start from scratch unless the
errors demand it):

{{ workhorse_var('partition_errors') }}
{% endif %}

## The judgment that matters: cluster granularity

N units must NOT become N stories, and they must not become 1 story either. The
`remediation_pattern` slugs are your main signal:

- **mechanical** cluster — many units sharing one fix shape (the same pattern slug, or
  near-identical shapes you normalize into one). This becomes ONE story carrying a
  per-unit checklist. Forty icon buttons missing accessible names is one mechanical
  cluster, not forty stories.
- **dedicated** cluster — a unit (or a couple of tightly-coupled units) whose findings are
  genuinely gnarly: many interacting findings, substantial effort, or work that needs its
  own design. It gets its own cluster so the author gives it a real story.

Normalize the pattern taxonomy as you go: assessors propose slugs independently, so merge
synonyms (`btn-no-label` / `icon-button-missing-accessible-name`) into one canonical slug
per fix shape. Order clusters so foundations come first (shared primitives before the
screens that use them) — the author preserves your ordering hints.

**Losslessness is non-negotiable**: every `assessed` unit must land in at least one
cluster. A deterministic gate checks this; a unit you leave out will bounce the partition
back to you.

## Output artifact — the partition file

Write `{{ workhorse_var('partition_path') }}` (YAML), exactly this shape:

```yaml
clusters:
  - id: icon-button-missing-accessible-name   # unique kebab slug → the backlog [id]
    title: "Give every icon-only button an accessible name"
    remediation_pattern: icon-button-missing-accessible-name
    strategy: mechanical                       # or: dedicated
    order: 1                                   # optional coding-order hint (low = first)
    units:                                     # inventory ids this cluster remediates
      - src/lib/components/IconButton
      - src/lib/components/Toolbar
    notes: "One checklist story; trivial per unit; do the shared Button primitive first."
```

## Final response (REQUIRED, exact shape)

After any markdown notes, return this JSON object as your final message:

```json
{
  "partition_result": {
    "status": "complete" | "blocked",
    "notes": "Cluster count + the granularity calls you made, or the blocking question."
  }
}
```

Use `blocked` only when a scope/priority decision you cannot make prevents partitioning;
put the precise question in `notes` (the workflow records it for the operator).
