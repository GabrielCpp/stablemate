---
name: stablemate-code-review
description: "Multi-agent code review — 5 parallel reviewers + independent scorers, confidence-filtered. Mirrors the Claude Code /code-review plugin."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/stablemate-code-review/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-code-review/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Code Review

Provide a code review for the current repository's changes (working-tree diff, story-branch commits, or open pull request).

Follow these steps precisely:

## 1. Eligibility check (lightweight sub-call)

Skip if the PR is:
- closed or a draft
- an automated/bot PR or obviously trivial
- already has a code review comment from this session

If there is no PR (local diff only), proceed — eligibility only gates PR-comment posting.

## 2. Collect CLAUDE.md / instruction files

List the paths of any `CLAUDE.md`, `AGENTS.md`, or equivalent repo instruction files at the repo root and in any directory whose files the diff touches. Do not read their full contents yet — just collect paths.

## 3. Summarise the change

Read the PR title/description and diff (`gh pr diff`, or `git diff` for local changes) to produce a one-sentence change summary.

## 4. Run five parallel review sub-agents

Launch these **independently and in parallel** (each agent cannot see the others' findings):

| Agent | Task |
|-------|------|
| **#1 — CLAUDE.md compliance** | Audit the changes against instruction files from step 2. Flag only direct violations. Note that CLAUDE.md is guidance for writing code — not every rule applies during review. |
| **#2 — Obvious bugs** | Read the diff only (no extra context beyond the changed hunks). Flag large, impactful bugs. Skip nitpicks, style issues, and anything a linter/compiler/typechecker would catch. |
| **#3 — Historical context** | Run `git blame` and `git log` on the changed lines. Identify bugs that are only visible given the history of these lines. |
| **#4 — Prior PR comments** | Find previous PRs that touched the same files (`gh pr list --state merged --search "path:..."` or `gh search prs`). Check whether past review comments on those PRs also apply here. |
| **#5 — Inline code comments** | Read code comments in the modified files. Flag changes that violate guidance stated in those comments. |

Each sub-agent returns a list of findings: `{title, description, reason}`.

## 5. Score each finding (independent sub-agents)

For each finding, launch an independent scoring sub-agent that takes the finding, the PR diff, and the list of instruction file paths from step 2. The scorer returns a confidence score on a 0–100 scale:

| Score | Meaning |
|-------|---------|
| **0** | False positive — doesn't survive light scrutiny, or is pre-existing. |
| **25** | Possibly real but unverified; stylistic and not called out in instruction files. |
| **50** | Verified as real but minor or rare in practice. Not very important relative to the rest of the change. |
| **75** | Verified, will be hit in practice, or directly called out in instruction files. Existing approach is insufficient. |
| **100** | Confirmed, frequent, evidence directly confirms this. |

For findings flagged due to CLAUDE.md instructions, the scorer MUST verify that the instruction file actually calls out that issue specifically.

## 6. Filter

Discard findings with score < 80. If no findings remain, report "clean" (no issues).

## 7. False positive exclusions

Treat these as false positives regardless of score (do not flag them):

- Pre-existing issues not introduced by this change
- Things that look like bugs but aren't
- Pedantic nitpicks a senior engineer would ignore
- Issues a linter, typechecker, or compiler would catch (assume CI runs these separately)
- General quality issues (test coverage, docs) unless explicitly required in instruction files
- Issues on lines the change did not modify
- Issues silenced by lint-ignore comments
- Behaviour changes that are clearly intentional and in scope for the change

## 8. Re-check eligibility

Before posting, repeat step 1 to guard against the PR being closed or merged while the review ran. If reviewing local-only changes (no PR), skip this step.

## 9. Post results

**If findings remain after filtering**, post via `gh pr comment` (only when a PR exists and `--comment` was requested):

```
### Code review

Found N issues:

1. <brief description> (CLAUDE.md says "<exact quote>" | bug due to <file context>)

<https://github.com/owner/repo/blob/<full-sha>/path/to/file#L10-L14>

2. ...

🤖 Generated with Claude Code
```

**If no findings survive filtering:**

```
### Code review

No issues found. Checked for bugs and instruction-file compliance.

🤖 Generated with Claude Code
```

**Link format rules** (required for correct Markdown rendering):
- Always use the full commit SHA, never a branch name or `HEAD`
- Format: `https://github.com/owner/repo/blob/<sha>/path/file#L<start>-L<end>`
- Include at least 1 line of context before and after the flagged line
- Repo name must match the repo being reviewed

## Notes

- Do NOT check build signal or attempt to build or typecheck the app. These run separately in CI.
- Use `gh` for GitHub interactions (fetch PR, create comments), not web fetch.
- You MUST cite and link each finding (if referring to CLAUDE.md, link it).
- Do NOT modify source files, commit anything, or open/close PRs.
