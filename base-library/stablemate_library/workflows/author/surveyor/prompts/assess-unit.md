---
agent: agent
---

# Assess one unit against the rubric

You are the **per-unit assessor** of the surveyor workflow. The survey walks a frozen
inventory of units; you get exactly ONE of them. Look at what work the rubric implies for
this unit and **note it** in a structured finding record. You assess — you do not fix, and
you do not author stories. Your context is this one unit; exhaustiveness across units is
the loop's job, not yours — so be exhaustive *within* the unit.

## Your unit (authoritative — use exactly as given)

- Unit id: `{{ workhorse_var('unit_id') }}`
- Path / locator: `{{ workhorse_var('unit_path') }}` (kind: `{{ workhorse_var('unit_kind') }}`)
- Rubric: `{{ workhorse_var('rubric') }}` — the concern being surveyed. **Read it first**;
  it defines what counts as a finding, what "clean" means, and points at the repo skills
  (under `.claude/skills/`) that carry the stack-specific mechanics. Read those skills too
  — they, not this prompt, know how the concern applies to this stack.
- Write the record to: `{{ workhorse_var('record_path') }}`
- Operator context: `{{ workhorse_var('context_path') }}` — read it if it exists; when this
  unit blocked before, the operator's answer is in there and you MUST honor it.

## Method

1. Read the rubric and the skills it references.
2. Read the unit — the whole unit (a folder unit means its files together form one
   surface; assess them as one). Trace enough of its usage/rendering to judge behaviour,
   not just text.
3. For each rubric criterion, decide: satisfied, or a concrete finding. Every finding
   needs **evidence** (file:line refs, observed behaviour) — a finding with no evidence is
   a guess, and guesses are worse than gaps.
4. Propose a `remediation_pattern` slug per finding — a short kebab name for the *shape*
   of the fix (e.g. `icon-button-missing-accessible-name`). Patterns are how the
   partitioner later folds N similar findings into one mechanical story, so reuse the same
   slug for the same shape of problem; invent a new one only for a genuinely new shape.

## Escape hatches (instead of a bad assessment)

- **Too big.** If this unit genuinely cannot be assessed faithfully in one bounded context
  (a folder that is really dozens of surfaces), do NOT sample it — return
  `"status": "split"` and write no record; the workflow replaces the unit with its
  children and assesses each.
- **Blocked.** If a precondition you cannot create stops the assessment (won't build, needs
  credentials, generated-only code), write the record with `status: blocked` and the
  reason(s) in `openGaps`, and return `"status": "blocked"`. Never guess your way past a
  blocker.

## Output artifact — the finding record

Write `{{ workhorse_var('record_path') }}` as markdown with YAML front-matter, exactly this
schema (concern-neutral — nothing stack-shaped goes in the structure; specificity lives in
the descriptions/evidence):

```markdown
---
type: survey-finding
unit: {{ workhorse_var('unit_id') }}
kind: {{ workhorse_var('unit_kind') }}
status: assessed        # assessed = findings below | clean = nothing to do | blocked
findings:
  - description: What is wrong / missing, concretely.
    remediation_pattern: kebab-slug-for-the-fix-shape
    effort: trivial | small | substantial
    evidence: file.ext:42 — what you observed there.
openGaps: []            # blocked only: why the unit cannot be assessed
---

# Survey finding: <unit>

Free prose for humans: what you looked at, judgment calls, anything the partitioner or
a future assessor should know.
```

A `clean` record is a real result — it documents that the check RAN and found nothing;
never skip writing it. Idempotent: if a record already exists (a re-run), re-assess and
rewrite it rather than trusting it.

## Final response (REQUIRED, exact shape)

After any markdown notes, return this JSON object as your final message:

```json
{
  "assess_result": {
    "status": "assessed" | "clean" | "split" | "blocked",
    "notes": "One line: what you found / why split / what blocks."
  }
}
```
