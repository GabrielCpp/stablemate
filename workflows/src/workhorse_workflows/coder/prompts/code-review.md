---
agent: agent
---

# Code Review Stage

You are running the **code review** stage of the autonomous story workflow. Your job is to run a code review against each affected repository's local changes — usually uncommitted working-tree edits, sometimes commits on a story branch, occasionally an open pull request — and return the findings in a structured result for the implementation reviewer.

## Inputs

- Story path: `{{ workhorse_var('story_path') }}`
- Affected repo paths: `{{ workhorse_var('affected_repo_paths') }}`
{% if workhorse_var('instruction_paths') %}- Coding standards the implementer built against: `{{ workhorse_var('instruction_paths') }}`
{% endif %}{% if workhorse_var('branch') %}- Branch: `{{ workhorse_var('branch') }}`
{% endif %}{% if workhorse_var('pr_number') %}- PR number: `{{ workhorse_var('pr_number') }}`
{% endif %}

## Steps

For each path in `affected_repo_paths`:

1. `cd` into that repo.
{% if workhorse_var('branch') %}2. The target branch is `{{ workhorse_var('branch') }}`. If the repo is not already on that branch, run `git fetch origin {{ workhorse_var('branch') }} && git checkout {{ workhorse_var('branch') }}`.
3{% else %}2{% endif %}. Determine the review scope:
   - `git status --porcelain` — uncommitted working-tree changes.
   - `git log --oneline main..HEAD` (substitute the repo's default branch if it is not `main`) — story-branch commits.
   - If both are empty, the repo has nothing to review — skip it.
{% if workhorse_var('branch') %}4{% else %}3{% endif %}. Check for an open PR: run `timeout 30 gh pr view {% if workhorse_var('pr_number') %}{{ workhorse_var('pr_number') }} {% endif %}--json number,state --jq '.state'`. Treat any failure (no PR, no remote, `gh` not authenticated) as "no PR" — that does NOT skip the review; the review target is the local diff either way.
{% if workhorse_var('branch') %}5{% else %}4{% endif %}. Read the diff itself — `git diff` for the working tree and `git diff main...HEAD` for the branch commits. **The diff is the review target**: lines nobody in this change touched are out of scope.
{% if workhorse_var('branch') %}6{% else %}5{% endif %}. Review it, sizing the effort to the diff rather than fanning out by reflex:
   - **Under ~400 changed lines across all repos: review it yourself, in this turn, with no subagents.** A diff this size fits in one head, and a subagent costs more to brief and collect than it saves.
   - 400–1500 changed lines: split by concern across **at most 3** parallel subagents.
   - Over 1500: **at most 5**. That is a hard cap, whatever the diff's size.
   - Whoever does the reading covers these lenses:
     a. **Bugs** — a shallow scan of the changed lines for real defects: wrong logic, unhandled errors, races, resource leaks, broken invariants. Stay on the diff; do not go spelunking for extra context.
{% if workhorse_var('instruction_paths') %}     b. **The standard** — read the instruction files listed under `instruction_paths` above. Those are the coding standards this change was *written* against, so a violation of them is a real finding, not a style opinion. Only flag what the instruction text actually says; quote the line you are relying on.
{% else %}     b. **The standard** — if the repo carries a root `CLAUDE.md` or one beside the changed files, read it and check the change against it. Only flag what the instruction text actually says; quote the line you are relying on.
{% endif %}     c. **Local guidance** — comments in the modified files that state an invariant or a rule the change now breaks.
{% if workhorse_var('branch') %}7{% else %}6{% endif %}. Score every candidate finding from 0 to 100 for how confident you are that it is real, using this rubric:
   - **0**: Not confident at all. This is a false positive that doesn't stand up to light scrutiny, or is a pre-existing issue.
   - **25**: Somewhat confident. This might be a real issue, but may also be a false positive. You weren't able to verify that it's a real issue. If the issue is stylistic, it is one that was not explicitly called out in the relevant instructions.
   - **50**: Moderately confident. You were able to verify this is a real issue, but it might be a nitpick or not happen very often in practice. Relative to the rest of the change, it's not very important.
   - **75**: Highly confident. You double checked the issue, and verified that it is very likely a real issue that will be hit in practice. The existing approach in the change is insufficient. The issue is very important and will directly impact the code's functionality, or it is an issue that is directly mentioned in the relevant instructions.
   - **100**: Absolutely certain. You double checked the issue, and confirmed that it is definitely a real issue, that will happen frequently in practice. The evidence directly confirms this.

   For an issue flagged against the standard, double check that the instruction file actually calls out that issue specifically before scoring it above 50.
{% if workhorse_var('branch') %}8{% else %}7{% endif %}. **Drop every finding scoring below 80.** What survives goes into the `findings` array below, with its score.
{% if workhorse_var('branch') %}9{% else %}8{% endif %}. If (and only if) step {% if workhorse_var('branch') %}4{% else %}3{% endif %} found an open PR, also post the surviving findings as a single `gh pr comment`: a `### Code review` heading, `Found N issues:`, then one numbered brief description each, citing the file and line. Keep it brief, no emojis. The implementation reviewer consumes the JSON below, not PR comments, so the findings must be complete here whether or not a PR exists.

## Not findings

Do not report any of these — they are the false positives this pass exists to keep out:

- Pre-existing issues, and real issues on lines this change did not modify.
- Something that looks like a bug but is not actually a bug.
- Pedantic nitpicks that a senior engineer wouldn't call out.
- Anything a linter, typechecker, or compiler would catch — missing or incorrect imports, type errors, formatting, style. Those run separately; do not run a build or typecheck yourself.
- General code-quality complaints (test coverage, documentation, generic security posture) unless the instructions explicitly require it.
- Something the instructions call out but the code explicitly silences, e.g. with a lint-ignore comment.
- Changes in behaviour that are plainly intentional and part of the story.

## Constraints

- Do NOT modify any source files.
- Do NOT commit anything.
- Do NOT open or close PRs.

## Output

Return this JSON as your final response:

```json
{
  "status": "findings" | "clean" | "skipped" | "blocked",
  "findings": [
    {
      "repo": "<repo directory name>",
      "file": "<path relative to that repo>",
      "line": 0,
      "issue": "<what is wrong>",
      "required_fix": "<what to change>",
      "score": 0
    }
  ],
  "findings_summary": "<one-sentence summary of what was flagged, or 'No issues found.', or 'No local changes to review.'>"
}
```

- `findings` — at least one finding scored 80 or above in one or more repos; each is listed in `findings`.
- `clean` — the review ran on at least one repo with local changes and found no issues meeting the threshold; `findings` is empty.
- `skipped` — no affected repo had any local changes to review; `findings` is empty.
- `blocked` — the diff could not be read at all: the repos you were given are not the ones the
  change landed in, or the working tree is in a state (an unresolved conflict, a detached or
  missing branch) that no review of it would mean anything. `clean` and `blocked` are not the
  same answer — one says the diff is fine, the other says there was no diff to judge — and the
  binding reviewer downstream is handed this verdict as prose. `findings` is empty and
  `findings_summary` names what stopped you.
