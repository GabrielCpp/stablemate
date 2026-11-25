---
description: "Take one story from its spec to reviewed code in this session: the book delta, the plan, the build, the review and the repair laps. The story-book-qa command picks the branch up from here."
argument-hint: "<story-id>"
---

# Specify and build story $ARGUMENTS

You own story `$ARGUMENTS` from its spec to a reviewed branch. The book states what the
story changes before any code does. The code then makes the book true. Each step ends on
a check. A step whose check fails is repaired in place before the next one starts.

Load {{ skill_link("ostler-cli") }} for the planning graph and {{ skill_link("ostler-book") }}
for the book. Load {{ skill_link("behaviour-model") }} before step 2.

## 1. Start

- `ostler path story $ARGUMENTS` names the story file. `ostler path spec $ARGUMENTS`
  names its spec folder. `ostler path branch $ARGUMENTS` names its branch.
- Work on that branch, in a worktree when the main checkout is busy.
- Read the story, every acceptance criterion and the epic around it.
- Run `ostler book decisions <module> --story $ARGUMENTS` for each service the story
  touches. Read `ostler book pages`. Read the book's `DISAGREEMENTS.md` when it has one.

**Done when** the branch is checked out and you can name each service the story touches.

## 2. Specify into the book

1. Write the behaviour model to `<spec>/model.md`. Every cell holds a decision: a
   transition, a refusal, a no-op or impossible.
2. Write the story's delta into each service's book as intent. Rewrite a changed element
   to state the new behaviour. A note beside the old text leaves the book wrong.
3. Write each decision you settled as a file under the book's `decisions/`, or as a line
   in the decision that already covers it.
4. Dispatch a reviewer with none of this session's context. Give it the story, the
   model and the book diff. It answers two questions:
   - Which acceptance criterion or step has no cell in the model?
   - Which cell has no claim in the book, and which claim would pass unchanged on the
     code as it stands?
5. Fix each gap it names. Run `ostler book check <module> --app <repo root>` until it
   exits 0.

A product decision that no page settles stops the story. Write the question into the
spec folder and hand it to the person who owns the product.

**Done when** the reviewer names no gap and `ostler book check` exits 0 for every touched
book.

## 3. Plan

Search the code for what the story can reuse before you plan anything new. Create the
plan with `ostler create spec $ARGUMENTS plan.md`, then fill these sections:

- **Approach**: the shape of the change in a paragraph.
- **Changes**: one line per change, marked reuse, extend or new, with the search that
  found or ruled out the existing code.
- **Stages**: the order to build in, each stage green on its own.
- **Testability**: the seams the tests drive.
- **Blast Radius**: every caller and consumer the change reaches.
- **Test Scenarios**: one entry per behaviour as given, when, should. Each carries an
  `AC` bullet and a `Level` bullet: unit, component, endpoint, integration or QA-only.
- **Acceptance Walk**: left empty. Step 4 fills it.
- **Verification Commands**: the exact gate commands, each under a timeout.

Commit the plan on the branch.

**Done when** every acceptance criterion has at least one test scenario and the plan is
committed.

## 4. Build

- Build stage by stage. Each new behaviour gets a test you saw fail first.
  {{ find_by_tags("tests") }}
- Run every verification command and one smoke run of the changed path, each under a
  timeout.
- Fill the Acceptance Walk with one entry per criterion:

  ```markdown
  ### AC 1: <first words of the criterion>
  - **Met by**: <repo>/<path>:<line>
  - **Observed**: <what the smoke run or test showed>
  ```

- Record each departure from the plan in the plan, with the reason.
- Leave the book alone in this step. A code fact that contradicts the book goes back to
  step 2.
- Commit by path: `git commit --only -m "<message>" -- <paths>`. End the message with an
  `Epic:` trailer, then a `Story:` trailer.

**Done when** every verification command exits 0 and every criterion has a Met by line
and an Observed line.

## 5. Review

Size the review to the diff against the base branch. Use one reviewer under 400 changed
lines, up to three under 1500, and at most five beyond. Each reviewer runs with none of
this session's context and takes one or two lenses:

- **Bugs**: wrong behaviour, races, unhandled failures.
- **Standard**: the repo's written conventions. {{ find_by_tags("standards") }}
- **Local guidance**: the instruction files nearest each changed path.
- **Reuse**: new code that duplicates code already in the repo.
- **Spec**: each acceptance criterion and book claim against the diff.
- **Test integrity**: tests that cannot fail, mocks that hide the behaviour, weakened
  checks.

A reviewer reports only findings it scores 80 or above. Each finding names the target,
the issue, the repair, the lens and the score.

Triage each finding as a real defect, not a defect, behaviour the story asks for, or an
improvement. Fix a real defect at its cause and re-walk the criteria it touches. File an
improvement as a follow-up with its repo, area, pattern and symbols. Write the triage
with its reasons to `<spec>/review-answers.md`.

**Done when** every finding has a triage line and every real defect is fixed and committed.

## 6. Repair laps

Rerun the verification commands. A red gate starts a repair lap. A repair lap fixes only
what the failure names and runs no new review. A repair makes the code meet the check.
The check stays as strict as the plan wrote it. Stop after three laps that leave the gate
red and report the failure with its output.

**Done when** every verification command exits 0 on the last commit. Then run
the story-book-qa command on `$ARGUMENTS`.
