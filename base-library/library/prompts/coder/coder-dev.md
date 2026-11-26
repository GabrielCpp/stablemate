---
description: "Take one specified story to reviewed code in this session: the plan, the build, the review, the triage and the repair laps. The coder dev subflow by hand. coder-book-qa picks the branch up from here."
argument-hint: "<story-id>"
---

# Build story $ARGUMENTS

This command does by hand what the coder `dev` subflow does in its plan, build and review
turns (`workhorse-coder run dev`). Story `$ARGUMENTS` is specified: its model and its book
delta are committed on its branch, as coder-docs leaves them. You own it from there to a
reviewed branch. Each step ends on a check. A step whose check fails is repaired in place
before the next one starts.

Load {{ skill_link("ostler-cli") }} for the planning graph and {{ skill_link("ostler-book") }}
for the book.

## 1. Start

- `ostler path story $ARGUMENTS` names the story file. `ostler path spec $ARGUMENTS`
  names its spec folder. `ostler path branch $ARGUMENTS` names its branch.
- Work on that branch, in a worktree when the main checkout is busy.
- Read the story, every acceptance criterion, the epic around it and `<spec>/model.md`.
- Read the book delta the story committed. The code makes those claims true.

**Done when** the branch is checked out and you can name each service the story touches.
A story with no `model.md` goes to the coder-docs command first.

## 2. Plan

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
- **Acceptance Walk**: left empty. Step 3 fills it.
- **Verification Commands**: the exact gate commands, each under a timeout.

Commit the plan on the branch. To check the plan before building, run the coder-review
command on `<spec>/plan.md $ARGUMENTS` and fix what it reports.

**Done when** every acceptance criterion has at least one test scenario and the plan is
committed.

## 3. Build

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
  the coder-docs command.
- Commit by path: `git commit --only -m "<message>" -- <paths>`. End the message with an
  `Epic:` trailer, then a `Story:` trailer.

**Done when** every verification command exits 0 and every criterion has a Met by line
and an Observed line.

## 4. Review

Dispatch a reviewer with none of this session's context. It runs the coder-review command
on `<base branch> $ARGUMENTS` and returns its findings. Do not hand it your view of the
change.

**Done when** the reviewer returned its findings.

## 5. Triage and fix

Triage each finding yourself as a real defect, not a defect, behaviour the story asks for,
or an improvement. Before you decline a finding, read the code it targets and say what you
read. Fix a real defect at its cause and re-walk the criteria it touches. File an
improvement with `ostler backlog add`, naming its repo, area, pattern and symbols. Write
the triage with its reasons to `<spec>/review-answers.md`.

**Done when** every finding has a triage line and every real defect is fixed and committed.

## 6. Repair laps

Rerun the verification commands. A red gate starts a repair lap. A repair lap fixes only
what the failure names and runs no new review. A repair makes the code meet the check.
The check stays as strict as the plan wrote it. Stop after three laps that leave the gate
red and report the failure with its output.

**Done when** every verification command exits 0 on the last commit. Then run the
coder-book-qa command on `$ARGUMENTS`.
