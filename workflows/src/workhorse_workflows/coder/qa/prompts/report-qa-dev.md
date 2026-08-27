---
agent: agent
---

# Report The DEV QA Failure

QA ran against the DEV environment and found failures. This code is owned by another developer — fixing it is not your job. Your job is to write a clear, actionable Jira comment that tells the story's author exactly what failed and how to reproduce it, then terminate cleanly.

{% include "_dev-report-brief.md" %}

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

## Output

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
