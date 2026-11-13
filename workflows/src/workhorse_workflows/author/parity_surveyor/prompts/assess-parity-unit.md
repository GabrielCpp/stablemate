---
agent: agent
---

# Compare one baseline surface with the current service books

Assess exactly one baseline surface. This is an inventory diff, not discovery of new work: do not write
feature nodes, epics, stories, or source code. Write only the survey finding record.

## Inputs

- unit: `{{ workhorse_var('unit_id') }}`
- baseline surface doc: `{{ workhorse_var('unit_path') }}`
- baseline inventory: `{{ workhorse_var('baseline_inventory') }}`
- current books: `services/`
- existing epics: `{{ workhorse_var('epics_dir') }}`
- record: `{{ workhorse_var('record_path') }}`

The open records of the surveyed repository, one per line, tab-separated: id, repo, area, status, pattern, summary.

```
{{ workhorse_var('register_listing') }}
```
{% include "pm/prompts/books.md" %}

Read the baseline surface in full. Search all current service books with `ostler book search`, then `ostler book explain` the
entries it finds. Correspondence is behavioral, not name-only: a renamed
route counts only when the new books cover the baseline surface's purpose, controls, and outcomes.

Also search the open records above and the epics for existing ownership of this exact surface.
Ownership does not make an absent implementation covered, but it prevents a duplicate record:
record the owner in the optional top-level `existing_owner` field.

Write a standard `survey-finding` record:

- `status: clean`, `findings: []` when the current books behaviorally cover the surface.
- `status: assessed` with exactly one finding when coverage is absent or materially incomplete.
  The finding description must be a self-contained, one-line-ready statement naming the
  legacy title/route and the missing new-app behavior. Use `remediation_pattern:
  legacy-surface-parity`, an effort enum, and concrete baseline plus graph-search evidence.
- If an open record, an epic or a story already owns the missing surface, keep `status: assessed`
  and add `existing_owner: <epic slug, story slug, or record id>` so emission suppresses the
  duplicate while retaining the audit result.

Use this exact finding shape. `effort` MUST be exactly one of `trivial`, `small`, or `substantial`;
never write hours, days, points, or another value.

```yaml
findings:
- description: >-
    One self-contained statement. Always use this block-scalar form so punctuation such as
    colons cannot make the YAML invalid.
  remediation_pattern: legacy-surface-parity
  effort: small
  evidence:
  - Baseline evidence with path and lines.
  - Current book evidence with entry names or search results.
```

Final response:

```json
{"status":"clean"|"assessed","notes":"one-line result"}
```
