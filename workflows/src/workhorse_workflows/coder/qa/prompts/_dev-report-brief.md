## The DEV report

This run is against DEV, where the code belongs to another developer. A product finding here
is reported to its author, not fixed. Before you return, write
`{{ workhorse_var('qa_dir') }}/jira-comment.md` yourself: one comment, self-contained and
ready to paste into the tracker. Build it from `qa-report.md`, whose assertion tables hold the
observed values, from `qa.md`, from `qa-evidence.json`, from the files under the QA dir the
report links, and from the story's Acceptance Criteria.

Both shapes share these rules:

- One section per AC, in story order. Never merge two ACs.
- Be specific: name the field, the value, the error, the endpoint.
- No `**Date:**` field, since the tracker timestamps the comment.
- No absolute paths. Reference evidence relative to the QA dir.
- No code fix suggested. Say what happened and how to see it.
- Say so plainly when the plan was missing or the evidence is sparse.
- Do not print the comment in chat.

When the scored run failed:

```markdown
## ❌ QA FAIL: DEV

**Environment:** DEV | **Story:** <slug>

### Summary

<one to three sentences: what failed, which ACs, what a reviewer needs to know>

### Failed ACs

#### AC<n>: <criterion title> | ❌ FAIL

**Action taken:** <what was done>
**Expected:** <what the plan said should happen>
**Observed:** <what happened: values, error messages, status codes>
**Evidence:** `<file under the QA dir>`

### Passed ACs

#### AC<n>: <criterion title> | ✅ PASS

**Evidence:** `<file under the QA dir>`

### Reproduction steps

<numbered steps the author can follow on DEV>
```

When the scored run passed and the audit stands:

````markdown
## ✅ QA PASS: DEV

**Environment:** DEV | **Story:** <slug>

### Summary

<one to three sentences: what was tested, where, and the verdict>

### AC<n>: <criterion title> | ✅ PASS

**Why it passed:** <the observed behaviour that satisfies the criterion: the field, value,
event or screen that proves it, never the code behind it>

<evidence label>

```<lang>
<the key output inline, cut to its most relevant 10 to 20 lines>
```

![<descriptive alt text>](screenshots/<name>.png)
````

A screenshot the report embeds for an AC goes on its own line, by the path the report gives.
An AC whose device step was deferred says so in a `**Note:**` line with the reason. A
deviation from the AC's wording or a surprising observation goes in a final
`### Observations` list, left out when there is nothing to note.
