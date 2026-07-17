---
agent: agent
---

# Report DEV QA Pass — {{ repo.name | title }}

QA ran against the DEV environment and all acceptance criteria passed. Write a clear, evidence-backed Jira comment that tells the story's author exactly what was tested and confirmed, then terminate cleanly.

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`
- QA notes: `{{ workhorse_var('qa_notes') }}`

## What to write

Read:

- `{{ workhorse_var('spec_dir') }}/qa-plan.md` — the runbook that was executed
- `{{ workhorse_var('spec_dir') }}/qa.md` — the QA report with per-AC verdicts and evidence
- `{{ workhorse_var('spec_dir') }}/qa-evidence.json` — captured evidence (if present)
- Any files under `{{ workhorse_var('qa_dir') }}` — screenshots, command output, etc.
- `{{ workhorse_var('story_path') }}` — to confirm the acceptance criteria

Produce one file: `{{ workhorse_var('qa_dir') }}/jira-comment.md`

The comment must be self-contained and copy-paste ready into Jira. Structure it as:

```markdown
## ✅ QA PASS — DEV

**Environment:** DEV | **Story:** <slug>

---

### Summary

<1–3 sentences: what was tested, which environment and tenant, and the overall verdict>

---

### AC<n> — <criterion title> | ✅ PASS

**Why it passed:** <One or two sentences explaining the observed behaviour and why it satisfies the
acceptance criterion. Be specific: name the field, value, event, or screen that proves the claim.>

<Evidence label>

```<lang>
<key content reproduced inline — truncate to the most relevant 10–20 lines if output is large>
```

![<descriptive alt text>](acN-<slug>/<key-screenshot>.png)

### AC<n+1> — <criterion title> | ✅ PASS

...
```

Rules:
- Open with `## ✅ QA PASS — DEV`. Never `❌ FAIL` here — this prompt only runs on a confirmed pass.
- Do not include a `**Date:**` field — Jira timestamps the comment automatically.
- One `###` section per AC, in story order. Never collapse two ACs into one.
- The **"Why it passed"** sentence is mandatory for every AC. It must reference the specific observed
  behavior (field name, event type, screen name, API response) — not the code that implements it.
- After the rationale, include the key evidence as a labelled fenced code block. Reproduce the most
  relevant content inline — a reader must be able to verify the claim without opening local files.
- If a screenshot exists for the AC, include it on its own line (blank lines above and below) using
  `![alt](acN-<slug>/filename.png)` with a path relative to the `qa/` directory.
- Do not reference local absolute file paths in prose.
- If any AC was deferred (e.g. device unavailable for a Maestro step), note it clearly:
  `**Note:** Device step deferred — <reason>. Code-pattern check substituted per runbook.`
- Do not add a trailing blockquote crediting the tester.
- If there are any deviations from the AC wording or surprising observations, add a final
  `### Observations` section as a short bulleted list. Omit it if there is nothing to note.
- Do not print the comment body in chat.

## Structured Output Requirement

Return this exact JSON object in your **final response**:

```json
{
  "qa_report_result": {
    "status": "reported",
    "notes": "Jira comment written to <spec_dir>/qa/jira-comment.md — all ACs passed"
  }
}
```

- `status` is always `"reported"`
- `notes` must name the output path and confirm that all ACs passed
