---
description: "Review a branch's whole diff, or a plan before it is built, and report the findings without triage or fixes. The coder review step by hand, to compare against what a run's reviewer filed."
argument-hint: "<base-ref | plan.md> [story-id]"
---

# Review $ARGUMENTS

This command is the reviewer the coder `dev` subflow dispatches, run on its own. Use it to
check what a run's review should have found, or to review a plan before anyone builds it.
You edit nothing. You report findings and stop.

`$ARGUMENTS` holds the target, then an optional story id.

- A path to a markdown file is a plan. Review it as section 2 says.
- Anything else is a git ref. Review the diff from it to `HEAD` as section 1 says. With no
  target, the ref is the repository's default branch.
- A story id names the acceptance criteria the target answers to.
  `ostler path story <id>` names the story file, and `ostler path spec <id>` names its
  spec folder.

Load the skills the repository's instruction files name for the touched paths.

## 1. A diff

Read the story's acceptance criteria and the `plan.md` in its spec folder when a story id
was given. Then read `git diff <ref>...HEAD` and the working tree's `git diff`. Lines the
change did not touch are out of scope.

Size the review to the diff. Under 400 changed lines, review it yourself. Beyond that, split
the lenses below across up to five reviewers with none of this session's context, one or
two lenses each.

- **Bugs.** Wrong logic, unhandled errors, races, leaks and broken invariants on the
  changed lines.
- **The standard.** A rule an installed coding standard states, quoted.
  {{ find_by_tags("standards") }}
- **Local guidance.** A comment or instruction file near a changed path whose rule the
  change now breaks.
- **Reuse.** Added code that repeats code the tree already has. Search the whole tree by
  name and synonyms, by the behaviour in the domain's words, and by the signature's shape.
  The finding names the code the added lines repeat.
- **The spec.** An acceptance criterion the code does not meet, or behaviour the plan
  promises and the code does not deliver. A walk entry whose Observed line the code or its
  tests do not bear out.
- **Test integrity.** A criterion with no test that would fail without the change, a mock
  that hides the behaviour, or a weakened check.

## 2. A plan

Read the plan, and the story's acceptance criteria when a story id was given. Then read the
code the plan names, and check each claim the plan makes about the tree against the tree.

- **Coverage.** A criterion no step delivers, or delivers only in part.
- **The tree.** A file, symbol, route, table or service the plan names that the tree lacks
  or has under another name or shape.
- **Contradiction.** A step that breaks behaviour existing code relies on.
- **Order.** A step that depends on one after it.
- **Verification.** A declared test or command that cannot run as written, or a behaviour
  change with no test that would fail without it.
- **Data.** A stored-format change with no migration, or a migration that loses data.

## 3. Report

Score each candidate from 0 to 100 for how sure you are the defect is real. Report only
those at 80 or above. These are not findings: a pre-existing issue, a nitpick, what a
linter or type checker catches, a different design that would also work, and a change the
story asks for.

Report the findings as a numbered list, most certain first. Each one names:

- **Target**: `repo/path:line` for a diff, the section or step for a plan.
- **Issue**: the defect and what it breaks.
- **Repair**: the change that removes it.
- **Category**: `Bug`, `Standard` or `Reuse`.
- **Score**: 80 to 100.

**Done when** every lens has been applied to the whole target and each finding carries all
five fields.
