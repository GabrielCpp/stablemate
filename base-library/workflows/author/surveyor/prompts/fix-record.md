---
agent: agent
---

# Repair a finding record so it validates

A survey finding record was written but the deterministic validator rejected it — most
commonly malformed YAML front-matter or a missing required field. Your ONLY job is to make
the record parse and validate **while preserving all of its content**. You are a mechanic,
not an assessor: do not re-assess the unit, do not soften or drop findings, do not change
what the record claims — fix its shape.

## The record

- File: `{{ workhorse_var('record_path') }}`
- Unit it must describe: `{{ workhorse_var('unit_id') }}`

## Validator errors to fix

{{ workhorse_var('record_errors') }}

## The contract the record must meet

Markdown with a leading YAML front-matter block:

```markdown
---
type: survey-finding
unit: <exactly the unit id above>
kind: <the unit's kind>
status: assessed | clean | blocked
findings:                      # assessed: >= 1 entry; clean: empty/absent
  - description: <non-empty>
    remediation_pattern: <kebab-case-slug>
    effort: trivial | small | substantial
    evidence: <non-empty>
openGaps: [...]                # blocked: >= 1 entry saying why
---
<prose body — untouched>
```

Rules of repair:

- Fix YAML syntax (quoting, indentation, the closing `---` fence) in place.
- Map obviously-misnamed fields onto the schema (e.g. `pattern:` → `remediation_pattern:`)
  rather than deleting them.
- If a required field's value is genuinely absent from the record (e.g. a finding with no
  evidence anywhere in the file, including the prose body), do NOT invent one — move that
  finding's content into the prose body under a `## Unvalidated notes` heading and drop it
  from `findings`, so nothing is fabricated and nothing is lost.
- Never change `unit`, and never flip `status` except to reconcile it with the record's
  own content (e.g. `assessed` with zero findings and no salvageable finding → `clean`).

## Final response (REQUIRED, exact shape)

```json
{
  "fix_record_result": {
    "status": "fixed" | "unfixable",
    "notes": "What you repaired, or why it cannot be repaired."
  }
}
```
