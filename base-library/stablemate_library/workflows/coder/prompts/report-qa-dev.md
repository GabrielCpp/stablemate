---
agent: agent
---

# Report DEV QA Failure — {{ repo.name | title }}

QA ran against the DEV environment and found failures. This code is owned by another developer — fixing it is not your job. Your job is to write a clear, actionable Jira comment that tells the story's author exactly what failed and how to reproduce it, then terminate cleanly.

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`
- QA failure notes: `{{ workhorse_var('qa_notes') }}`

## What to write

Read:

- `{{ workhorse_var('spec_dir') }}/qa-plan.md` — the runbook that was executed
- `{{ workhorse_var('spec_dir') }}/qa-evidence.json` — captured evidence (if present)
- Any files under `{{ workhorse_var('qa_dir') }}` — screenshots, command output, etc.
- `{{ workhorse_var('story_path') }}` — to confirm the acceptance criteria

Produce one file: `{{ workhorse_var('qa_dir') }}/jira-comment.md`

The comment must be self-contained and copy-paste ready into Jira. Structure it as:

```markdown
## ❌ QA FAIL — DEV

**Environment:** DEV | **Story:** <slug>

---

### Summary

<1–3 sentences: what the QA run found, which ACs failed, what a human reviewer needs to know>

---

### Failed ACs

For each AC that did not pass:

#### AC<n> — <criterion title> | ❌ FAIL

**Action taken:** <what was done>
**Expected:** <what the runbook said should happen>
**Observed:** <what actually happened — specific values, error messages, exit codes>
**Evidence:** `qa/<file>` (if captured)

---

### Passed ACs (if any)

#### AC<n> — <criterion title> | ✅ PASS

**Evidence:** `qa/<file>`

---

### Reproduction steps

<numbered steps the author can follow to reproduce the failure on DEV>
```

Rules:
- One section per AC, in story order. Never collapse two ACs into one.
- Be specific: name the field, the value, the error. "The button did nothing" is not useful; "Clicking Save triggered a 500 from `/api/alerts` (evidence: `qa/ac2-save-error.txt`)" is.
- Do not suggest code fixes — report what failed and how to reproduce it.
- Do not add screenshots inline; reference the file path in `qa/`.
- If the QA plan was missing or evidence is sparse, say so explicitly.

## Structured Output Requirement

Return this exact JSON object in your **final response**:

```json
{
  "qa_report_result": {
    "status": "reported",
    "notes": "Jira comment written to <spec_dir>/qa/jira-comment.md — <one-line summary of failures>"
  }
}
```

- `status` is always `"reported"`
- `notes` must name the output path and summarise what was found
