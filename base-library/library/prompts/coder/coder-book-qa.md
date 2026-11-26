---
description: "Prove a built story through its service books: state each acceptance criterion as a book claim, play it against a local stack, judge every criterion, then land the book. The coder book_qa subflow by hand. A story no book covers goes to coder-qa."
argument-hint: "<story-id>"
---

# Book QA for story $ARGUMENTS

This command does by hand what the coder `book_qa` subflow does
(`workhorse-coder run book_qa`). The story's code is built and reviewed on its branch. This session proves each
acceptance criterion by playing the book against the running app. A criterion is proven
when a play observed it. A green unit test alone leaves it unproven.

Load {{ skill_link("ostler-book") }} before the first edit under a book. Load
{{ skill_link("ostler-cli") }} for `ostler env` and QA plans.

## 1. Read

Read the story, its acceptance criteria, `<spec>/plan.md` and `<spec>/review-answers.md`.
`ostler path spec $ARGUMENTS` names the spec folder. Read the decisions the story touches
with `ostler book decisions <module> --story $ARGUMENTS`.

**Done when** you can name each service whose behaviour the story changed.

## 2. Pick the books

Run `ostler book stale <module> --app <repo root> --story $ARGUMENTS` for each service.
A service with a book takes the book path below. A story no book covers goes to step 8.

**Done when** every touched service is on the book path or on the fallback.

## 3. Bring the stack up

Run `ostler env up` for the services the books play against. `ostler env address <name>`
prints where each one listens. Play the base calls first with
`ostler book run <module> --only <call>`. A base that plays red means the stack or the
fixtures are broken. Repair that before any claim, or stop and report it when the repair
needs a person.

**Done when** the base calls play green.

## 4. State each criterion in the book

For each acceptance criterion:

1. Search `ostler book search <noun>` and `ostler book pages` for each main noun the
   criterion names. The company, team, product and decision pages bound what the claim
   may say.
2. State the criterion as a claim in a journey or a call class. Keep every `source=`
   pointer current.
3. Restructure the book when its shape leaves no place for the claim.
4. Mark a claim `unreached` only when no call can observe it.

Where the app breaks a claim, the book keeps the intent. Declare the known defect in the
book and list it as a finding for the code.

**Done when** every criterion maps to a claim, or to an `unreached` claim with its reason.

## 5. Play

Run `ostler book check <module> --app <repo root>` until it exits 0. Run
`ostler book affected <module> --app <repo root> --story $ARGUMENTS` to list what the
story reaches. Play each affected journey with `--journey <name>`, then each affected
call with `--only <call>`. Run one play at a time, under a timeout. Play only what the
story reaches.

Fix a red play at its cause. A wrong book is fixed in the book. A wrong app is fixed in
the code, committed by path, and played again.

**Done when** check exits 0 and every affected journey and call plays green, or carries a
declared defect.

## 6. Judge every criterion

Dispatch a reviewer with none of this session's context. Give it the story, the book
diff and the play output. It gives each criterion exactly one verdict, the first that
applies:

- **unmet**: the app does not do it.
- **played**: a book play observed it.
- **tested**: a test observed it and no play could.
- **recorded**: the book states it as a declared defect or `unreached`.
- **checked**: `ostler book check` covers it and nothing runs it.
- **unobserved**: nothing observed it.

A step whose cells came back empty observed nothing. The reviewer may run one extra
`--only` or `--journey` play per criterion under `timeout 300`, edits nothing, and
touches no deployed environment.

**Done when** no criterion is unmet or unobserved. Each one that is goes back to step 4
or to the code.

## 7. Land

Run `ostler book verified <module> --app <repo root> --story $ARGUMENTS`. Commit the book
change by path with a `test` subject and the `Epic:` and `Story:` trailers. Run
`ostler book land` to move the book onto its branch.

**Done when** `ostler book verified` passes and `ostler book land` exits 0.

## 8. Fallback: scenario QA

A story no book covers, and each criterion no book claim can state, goes to the coder-qa
command on `$ARGUMENTS`.
