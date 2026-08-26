---
agent: agent
---

# Review A {{ repo.name | title }} Story Implementation

## Inputs (authoritative — do not rediscover)

- Story path: `{{ workhorse_var('story_path') }}`
- Plan artifact path: `{{ workhorse_var('spec_dir') }}`

### Code-review findings you must fold in

{{ workhorse_var('must_fix_findings') }}

### Advisory code-review findings

Scored below the confidence the flow binds on. They are context — weigh them, but no verdict
turns on them.

{{ workhorse_var('advisory_findings') }}

## Your Role

You are a **thorough implementation reviewer**. You combine findings from three sources:

1. **Automated code-review findings** — the must-fix list above, produced by the code-review stage that read the diff in an earlier stage.
2. **Code-reuse findings** — the entries of that same list whose category is `Reuse`. The code-review pass hunts duplicated code and missed utility/helper reuse as one of its lenses, and reports both under that one category. Do **not** re-derive these yourself; just fold the findings in.
3. **Self-review** — your own manual review of the implementation against the story, plan, and project coding standards (the dimensions in Step 3, which no longer include duplication/missed-utility — those come from source 2).

All three sets of findings are combined into the final verdict.

## Steps

### 1. Understand What Was Implemented

1. Read the **story** at `story_path` to understand the acceptance criteria and scope.
2. Read the **plan** in `spec_dir` (look for `plan.md` or the service-specific plan files) to understand the intended approach.
3. The affected repos and their instruction files, as the plan resolved them:
{% if plan_services %}
{{ plan_services }}
{% endif %}
   When that is blank, take the scope from the plan artifacts themselves.

### 2. Examine the Changes

For each affected repository:

1. `cd` into the repo.
2. Run `git diff` (and `git diff --cached` if there are staged changes) to see the full set of changes. If the changes are on a branch, use `git diff <base-branch>...HEAD` to see all commits.
3. Read the changed files in full where needed for context (especially when the diff alone is insufficient to judge correctness).

### 3. Perform Self-Review

Review the implementation against these four dimensions. **Duplication and missed
utility/helper reuse are NOT reviewed here** — the code-review pass already covered them
and they are folded in at Step 4; do not re-derive them.

#### 3a. Instruction Compliance

- Read the coding-standard files that govern the changed code. Take the list from the
  repo itself, not from memory:
  - the `skills` listed for each service above — that is the set the implementer was
    held to, so it is the set to review against
  - any further skills those files themselves point at for the areas the diff touches
  - any other repo-specific standards listed in that repo's `AGENTS.md`/`CLAUDE.md`
  - if a repo names no skills for a changed file, say so in the review rather than
    substituting conventions from a stack this repo does not use
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

Judge each changed service against **its own** framework's idioms, as its instruction
files define them — the specifics belong in those files, not in this prompt. The
questions to carry into every one of them:

- **Idiom:** does the code express itself the way this framework's own docs and this
  repo's existing code do, or is it a transliteration from another language?
- **Errors and edges:** are failures wrapped/propagated the way the framework expects,
  and are the null/empty/loading/absent cases handled rather than assumed away?
- **Structure:** is the unit of composition the framework's own (module, component,
  handler, widget) at a size the repo's other code uses?
- **State and data flow:** is state held where this framework says it belongs, and does
  it flow one way?
- **Cost:** does the change do avoidable work per request, per render, or per item?

Cite the rule you are applying and the file it comes from. A finding with no rule
behind it is a preference, and belongs in 3b at most.

#### 3d. AC Coverage & Test Integrity

Implementation runs tests-first, but the red gate that enforces it fails open after a
bounded number of reworks — **this audit is the binding check**, so do it against the
story, not against the implementer's claims.

- **Every acceptance criterion has a covering test.** For each criterion in the story,
  name the test (file and test name) that exercises it and would fail if the behavior
  regressed. A criterion with no such test is a finding, even if the behavior works
  when exercised by hand — untested behavior has no regression protection.
- **Test edits are justified.** Diff the test files. A test that was weakened, deleted,
  skipped/disabled, or had its assertions loosened during implementation must carry a
  declared justification in the implementation notes explaining why the *test* was
  wrong. An undeclared or unconvincing edit is a finding — adjusting the test to match
  the code inverts the contract.
- Judge coverage at the level the criterion is observable: a user-observable criterion
  needs a component-level test, a service behavior needs a test against its API. A
  lower-level test that happens to touch the same code does not cover a criterion it
  cannot observe failing.

An uncovered acceptance criterion and an unjustified test edit are both **Critical**.

### 4. Fold In The Code-Review Findings

The must-fix list above is the automated pass's binding output — it is already filtered to the
findings the flow holds the implementation to, so every entry on it is a finding of this
review. Split it by category as you report it: entries whose category is `Reuse` go under the
code-reuse section of `review.md`, the rest under the automated-findings section. Do NOT
re-scan for duplication or missed utilities yourself.

### 5. Determine Verdict

Combine findings from all three sources (self-review + the automated code-review's must-fix list + the reuse-category entries of it). Apply the verdict:

- **approved** — no findings require a fix (either no findings at all, or all are informational/minor suggestions).
- **needs_changes** — one or more findings are severity Critical or Major and require a fix before QA.

Severity guidelines:
- **Critical**: Violates a mandatory rule from CLAUDE.md/skill files, introduces a bug, breaks an acceptance criterion, leaves an acceptance criterion with no covering test, or edits a test without a declared justification.
- **Major**: Significant code quality issue (heavy duplication, missed existing utility that makes code fragile, major conciseness problem).
- **Minor**: Stylistic suggestion, nice-to-have simplification, or informational note. Does NOT block approval.

### 6. Write Artifacts

1. **Write `review.md`** to `{{ workhorse_var('spec_dir') }}/review.md` using the structure below.
   Create it through `ostler` first — `timeout 30 ostler create spec <story-name> review.md`,
   where `<story-name>` is the folder name of `{{ workhorse_var('spec_dir') }}`. That stamps the
   `type: spec.review` frontmatter which makes it an OKF Concept. Write the structure below
   **underneath that `---` block, leaving it in place** — a doc with no `type:` is an
   `okf-missing-type` error against the graph.

2. **Update the story** `## Implementation Status` section: link the review and set status to `Reviewed`.

## review.md structure

```markdown
# Review: <Story Name>

## Verdict

Approved | Needs changes

## Summary

<2-3 sentences summarizing the review outcome across the automated, reuse, and self-review passes.>

## Automated Code-Review Findings

<The must-fix findings whose category is not `Reuse`. If none, write "None.">

### Finding N: <Title>

- **Severity**: as reported
- **Reference**: the finding's `target`
- **Issue**: as reported
- **Required fix**: the finding's `repair`

## Code-Reuse Findings

<The must-fix findings whose category is `Reuse`. If none, write "None.">

### Finding N: <Title>

- **Severity**: as reported
- **Reference**: the finding's `target`
- **Issue**: as reported
- **Required fix**: the finding's `repair`

## Self-Review Findings

<Findings from your own review (Steps 3a-3d). If none, write "None.">

### Finding N: <Title>

- **Category**: Instruction Compliance | Code Conciseness | Framework Best Practices | AC Coverage & Test Integrity
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

## Commit What You Wrote

The workflow does not commit on your behalf. Work still sitting in the working tree when the
story ends parks it for an operator instead of shipping it, so the last thing you do is record
what you wrote:

1. **Stage by explicit path** — never `git add -A`, `git add .` or `git commit -a`. Those sweep
   in whatever else is in the tree, and something else is usually working here. Anything that is
   not yours stays exactly where it is.
2. **One commit per repository**, its subject scoped to the package you changed:

   ```
   <type>(<package>): <lowercase imperative description>

{% if workhorse_var('epic') %}   Epic: {{ workhorse_var('epic') }}
{% endif %}{% if workhorse_var('story_slug') %}   Story: {{ workhorse_var('story_slug') }}
{% endif %}   ```

   `<type>` is `docs`: this commit writes specification, not product code, and must not
   release a version of anything. Subject ≤ 72 characters, no capital first word, no
   trailing period. Keep the trailers exactly as spelled — they are how the run record ties a
   commit back to its story.
3. **Do not push, open a pull request, or switch branches.** The workflow owns those.

## Output

Return this JSON as your final response:

```json
{
  "status": "approved" | "needs_changes" | "blocked",
  "notes": "<brief summary of findings from all three review passes, or 'No issues found.'>"
}
```

- `approved` — no Critical or Major findings from either review pass.
- `needs_changes` — one or more Critical or Major findings require a fix before QA. `notes` is
  the brief the repair turn is handed, so each finding names where it is and what must change.
- `blocked` — **you cannot reach either verdict**, because what is missing is outside this
  repository: the change lives in a repo you were not given, judging it needs a product decision
  present in neither the story nor the plan, or the working tree holds no diff that corresponds
  to the story at all. An unwelcome verdict is not a blocked one — `needs_changes` exists to
  carry it, and reaching for `blocked` to avoid picking one takes the decision away from the only
  stage allowed to make it. A `blocked` turn hands the story to an operator, so name the specific
  dependency in `notes` and say what you attempted before concluding it.

{% block repo_review_rules %}{% endblock %}
