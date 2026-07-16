---
agent: agent
---

# Review A {{ repo.name | title }} Story Implementation

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Plan artifact path: `{{ workhorse_var('spec_dir') }}`
- Automated code review result: `{{ workhorse_var('code_review_result') }}`
- Code-reuse review result: `{{ workhorse_var('code_reuse_result') }}`

## Your Role

You are a **thorough implementation reviewer**. You combine findings from three sources:

1. **Automated code-review findings** — collected from the `code_review_result` input (produced by the `/code-review` skill in an earlier stage).
2. **Code-reuse findings** — collected from the `code_reuse_result` input (produced by the dedicated code-reuse stage that hunts duplicated code and missed utility/helper reuse). Do **not** re-derive these yourself — that concern was extracted into its own stage; just fold the findings in.
3. **Self-review** — your own manual review of the implementation against the story, plan, and project coding standards (the dimensions in Step 3, which no longer include duplication/missed-utility — those come from source 2).

All three sets of findings are combined into the final verdict.

## Steps

### 1. Understand What Was Implemented

1. Read the **story** at `story_path` to understand the acceptance criteria and scope.
2. Read the **plan** in `spec_dir` (look for `plan.md` or the service-specific plan files) to understand the intended approach.
3. If a `plan-context.json` exists in the spec dir, read it to identify affected repos and instruction files.

### 2. Examine the Changes

For each affected repository:

1. `cd` into the repo.
2. Run `git diff` (and `git diff --cached` if there are staged changes) to see the full set of changes. If the changes are on a branch, use `git diff <base-branch>...HEAD` to see all commits.
3. Read the changed files in full where needed for context (especially when the diff alone is insufficient to judge correctness).

### 3. Perform Self-Review

Review the implementation against these three dimensions. **Duplication and missed
utility/helper reuse are NOT reviewed here** — they are handled by the code-reuse stage
and collected in Step 4b; do not re-derive them.

#### 3a. Instruction Compliance

- Read the relevant coding-standard files for each affected repo:
  - **api-service (Go):** `.claude/skills/api-service/SKILL.md` plus any domain skills (`api-service-db`, `api-service-test`, `api-service-events`, `api-service-grpc`, etc.) relevant to the changed files
  - **mobile-app (Dart/Flutter):** `.claude/skills/mobile-app/SKILL.md` (if applicable)
  - **web-app (TypeScript/Svelte):** `.claude/skills/web-app/SKILL.md` (if applicable)
  - Any other repo-specific skills listed in that repo's CLAUDE.md
- Verify naming conventions, code structure, and patterns match the documented standards
- Identify any violations with specific file and line references; explain which rule was broken

#### 3b. Code Conciseness

- Identify verbose or unnecessarily complex code that could be simplified
- Look for:
  - Redundant variables or intermediate steps
  - Overly nested conditionals that could be flattened
  - Long methods/functions that should be broken down
  - Repeated logic that could be extracted
- Suggest more concise alternatives while maintaining readability

#### 3c. Framework Best Practices

For the specific framework of the affected repo:

- **Go (api-service):** Error wrapping, early returns, function length, constant extraction, `util.Ptr()`, DynamoDB reserved-word prefixes, proto enum UNSPECIFIED values
- **Dart/Flutter (mobile-app):** Widget composition, state management, performance (const constructors, unnecessary rebuilds), null safety, async patterns
- **TypeScript/Svelte (web-app):** Type safety, reactive patterns, component decomposition, store usage

### 4a. Collect Automated Code-Review Findings

Process the `code_review_result` input:

- If `code_review_result.status` is `findings`:
  - Use the `findings` array (each entry has repo, file, line, issue, required fix, and score).
  - Fallback: if the array is empty despite the status, and an affected repo has an open PR, fetch the inline comments with `timeout 30 gh pr view --comments` and extract findings from there.

- If `code_review_result.status` is `clean`:
  - No automated findings.

- If `code_review_result.status` is `skipped`:
  - The automated review did not run (no local changes or tool unavailable). No automated findings.

### 4b. Collect Code-Reuse Findings

Process the `code_reuse_result` input (produced by the dedicated code-reuse stage). Do
NOT re-scan for duplication or missed utilities yourself — just consume this:

- If `code_reuse_result.status` is `findings`:
  - Use the `findings` array (each entry has repo, file, line, `category` — `Code Duplication` or `Missed Utility` — `severity`, issue, and required fix). Carry each finding's `severity` through to the verdict below.

- If `code_reuse_result.status` is `clean` or `skipped`:
  - No code-reuse findings.

### 5. Determine Verdict

Combine findings from all three sources (self-review + automated code-review + code-reuse). Apply the verdict:

- **approved** — no findings require a fix (either no findings at all, or all are informational/minor suggestions).
- **needs_changes** — one or more findings are severity Critical or Major and require a fix before QA.

Severity guidelines:
- **Critical**: Violates a mandatory rule from CLAUDE.md/skill files, introduces a bug, or breaks an acceptance criterion.
- **Major**: Significant code quality issue (heavy duplication, missed existing utility that makes code fragile, major conciseness problem).
- **Minor**: Stylistic suggestion, nice-to-have simplification, or informational note. Does NOT block approval.

### 6. Write Artifacts

1. **Write `review.md`** to `{{ workhorse_var('spec_dir') }}/review.md` using the structure below.
   Create it through `ostler` first — `timeout 30 ostler create spec <story-name> review.md`,
   where `<story-name>` is the folder name of `{{ workhorse_var('spec_dir') }}`. That stamps the
   `type: spec.review` frontmatter which makes it an OKF Concept. Write the structure below
   **underneath that `---` block, leaving it in place** — a doc with no `type:` is an
   `okf-missing-type` error against the graph.

2. **Write `review.json`** to `{{ workhorse_var('spec_dir') }}/review.json`:
   ```json
   {"verdict": "Approved" | "Needs changes"}
   ```

3. **Update the story** `## Implementation Status` section: link the review and set status to `Reviewed`.

## review.md structure

```markdown
# Review: <Story Name>

## Verdict

Approved | Needs changes

## Summary

<2-3 sentences summarizing the review outcome across the automated, code-reuse, and self-review passes.>

## Automated Code-Review Findings

<Findings from `code_review_result`. If none, write "None.">

### Finding N: <Title>

- **Severity**: as reported
- **Reference**: repo, file path, and line
- **Issue**: as reported
- **Required fix**: as reported

## Code-Reuse Findings

<Findings from `code_reuse_result` (duplication + missed utilities). If none, write "None.">

### Finding N: <Title>

- **Category**: Code Duplication | Missed Utility
- **Severity**: as reported
- **Reference**: repo, file path, and line
- **Issue**: as reported
- **Required fix**: as reported

## Self-Review Findings

<Findings from your own review (Steps 3a-3c). If none, write "None.">

### Finding N: <Title>

- **Category**: Instruction Compliance | Code Conciseness | Framework Best Practices
- **Severity**: Critical | Major | Minor
- **Reference**: repo, file path, and line number(s)
- **Issue**: clear description of the problem
- **Required fix**: specific code improvement or reference to existing solution
- **Rule reference**: instruction file and rule that applies (if Instruction Compliance)

## Required Fixes Before QA

<Consolidated list of all Critical and Major findings from ALL THREE sources that must be addressed. If none, write "None.">

## Notes

<Any skipped items, informational observations, or positive aspects of the implementation worth noting.>
```

## Output

Return this JSON as your final response:

```json
{
  "review_impl_result": {
    "status": "approved" | "needs_changes",
    "notes": "<brief summary of findings from all three review passes, or 'No issues found.'>"
  }
}
```

- `approved` — no Critical or Major findings from either review pass.
- `needs_changes` — one or more Critical or Major findings require a fix before QA.

{% block repo_review_rules %}{% endblock %}
