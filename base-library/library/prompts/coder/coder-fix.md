---
description: "Repair one backlog item end to end in this session: the fix at its cause, a test that fails without it, a fresh QA check, triage and the commit. The coder fix subflow by hand."
argument-hint: "<backlog item text or id>"
---

# Fix backlog item: $ARGUMENTS

This command does by hand what the coder `fix` subflow does for one item
(`workhorse-coder run fix`). The item is a repair, not a feature. You own it until the
repair is committed in every repository it belongs in and a QA record shows it works.

Load {{ skill_link("ostler-cli") }} for the backlog and the planning graph.

## 1. Read

- Find the item. `ostler backlog list` shows the register, with each item's repo, area,
  pattern and symbols. Fix only this item. Do not substitute another.
- The item was written by the QA of another story. A sentence about what that story owned
  binds that story, not this repair.
- Read the code the item names and the repo's `AGENTS.md`.

**Done when** you can name the behaviour the item says is wrong and the code that causes it.

## 2. Fix

- Write a test that fails without the repair, in the shape the touched layer's tests
  already have. See it fail. {{ find_by_tags("tests") }}
- Repair the cause, not the symptom. Leave unrelated surfaces alone.
- Run the changed repositories' gates, lint then test, each under a timeout.

**Done when** the new test passes and the gates exit 0.

## 3. QA

Dispatch a QA checker with none of this session's context, on a strong model. Give it the
item, the diff and the gate commands, never your reasoning. It runs the narrowest
verification that proves the repair: the touched packages' tests, the lint gate and, for a
user-visible change, the behaviour itself. It rules out what a green suite hides: a
swallowed 5xx, a console error, a partial write, a test that asserts presence. It reports
what it ran, what it observed and whether the repair stayed in scope.

**Done when** the checker reported.

## 4. Triage and repair

Give each finding one verdict with its reason: a defect of this repair, a failure the code
carries from elsewhere, or behaviour the item asks for. Both kinds of failure are real.
Fix each at its cause, run the gates and QA again.

**Done when** QA passes with no real finding open.

## 5. Commit

Commit the repair in each repository it changed. Close the message with the `Epic:` and
`Story:` trailers when the item belongs to one, then any other trailer, as one last
paragraph. Do not push. Prune the item with `ostler backlog prune` as done. File no new
backlog item.

**Done when** the repair is committed and the item is pruned. Report what you fixed and
what QA observed.
