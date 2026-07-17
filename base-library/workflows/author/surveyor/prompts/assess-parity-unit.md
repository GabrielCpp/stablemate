---
agent: agent
---

# Compare one baseline surface with the current OKF book

Assess exactly one baseline surface. This is an inventory diff, not gap discovery: do not write
knowledge nodes, gap nodes, epics, stories, or source code. Write only the survey finding record.

## Inputs

- unit: `{{ workhorse_var('unit_id') }}`
- baseline surface doc: `{{ workhorse_var('unit_path') }}`
- baseline inventory: `{{ workhorse_var('baseline_inventory') }}`
- current OKF books: `{{ workhorse_var('target_features') }}`
- existing backlog: `{{ workhorse_var('backlog') }}`
- existing epics: `{{ workhorse_var('epics_dir') }}`
- record: `{{ workhorse_var('record_path') }}`

Read the baseline surface in full. Search all current service books with `ostler graph`, `search`,
and `trace`, then inspect the linked nodes. Correspondence is behavioral, not name-only: a renamed
route counts only when the new graph covers the baseline surface's purpose, controls, and outcomes.

Also search the backlog and epics for existing ownership of this exact surface. Ownership does not
make an absent implementation covered, but it prevents a duplicate bullet: record the owner in the
optional top-level `existing_owner` field.

Write a standard `survey-finding` record:

- `status: clean`, `findings: []` when the current OKF graph behaviorally covers the surface.
- `status: assessed` with exactly one finding when coverage is absent or materially incomplete.
  The finding description must be a self-contained, one-line-ready backlog statement naming the
  legacy title/route and the missing new-app behavior. Use `remediation_pattern:
  legacy-surface-parity`, an effort enum, and concrete baseline plus graph-search evidence.
- If an existing backlog bullet or epic already owns the missing surface, keep `status: assessed`
  and add `existing_owner: <epic slug, story slug, or backlog id>` so emission suppresses the
  duplicate while retaining the audit result.

Use this exact finding shape. `effort` MUST be exactly one of `trivial`, `small`, or `substantial`;
never write hours, days, points, or another value.

```yaml
findings:
- description: >-
    One self-contained backlog statement. Always use this block-scalar form so punctuation such as
    colons cannot make the YAML invalid.
  remediation_pattern: legacy-surface-parity
  effort: small
  evidence:
  - Baseline evidence with path and lines.
  - Current OKF graph evidence with paths or query results.
```

Final response:

```json
{"assess_result":{"status":"clean"|"assessed","notes":"one-line result"}}
```
