---
description: "Specify one story in its service books before any code: the behaviour model, the book delta and a fresh review of both. The coder docs subflow by hand. coder-dev picks the story up from here."
argument-hint: "<story-id>"
---

# Specify story $ARGUMENTS

This command does by hand what the coder `docs` subflow does in one turn
(`workhorse-coder run docs`). No code for story `$ARGUMENTS` exists yet. You write what it
will do, before anyone builds it. The build follows what you write, and book QA plays the
claims you write. A behaviour you leave out is one nobody builds on purpose and nobody
checks.

Load {{ skill_link("ostler-cli") }} for the planning graph, {{ skill_link("ostler-book") }}
for the book and {{ skill_link("behaviour-model") }} before step 2.

## 1. Read

- `ostler path story $ARGUMENTS` names the story file. `ostler path spec $ARGUMENTS`
  names its spec folder. `ostler path branch $ARGUMENTS` names its branch.
- Work on that branch, in a worktree when the main checkout is busy.
- Read the story, every acceptance criterion and the epic's `## User Journeys`.
- For each service the story touches, read the book's `decisions/*.md` and its
  `DISAGREEMENTS.md`. `ostler book decisions <module> --story $ARGUMENTS` lists the
  decisions the story reaches. Read every page `ostler book pages` lists.

**Done when** the branch is checked out and you can name each service the story touches.

## 2. Model

Write the behaviour model to `<spec>/model.md`. Its sources are the acceptance criteria,
the epic's journeys and the book as it stands. Read the code only to learn a record's
present states, never to decide the story's new behaviour.

- Every record the story touches has its states and the read that tells them apart.
- Every action has the surface that reaches it and its inputs partitioned into classes,
  with a class at each bound the story states or implies.
- Every cell holds a transition with its observable effects, a refusal, a no-op, or
  impossible with its reason.
- A decision the story changes is named in the model, with whether the story keeps it or
  overturns it.

Decide an open cell by the convention the book follows for a similar record, and say so in
the cell. A cell that needs a product decision nobody wrote down stops the story. Write the
question into the spec folder and hand it to the person who owns the product.

**Done when** no cell is open.

## 3. Book delta

Write the story's claims into each service's book as intent:

- Rewrite each book element the story changes to the new behaviour. A note beside the old
  text leaves the book wrong.
- Turn every decided cell into a claim a run can judge. The empty value, the bound and the
  refusal each get their own claim.
- Write each decision the story settles under the book's `decisions/`, naming the story.
- Name an endpoint by the method and path the epic or the book's conventions give it.
- Keep a claim no call can observe in the model and out of the book.

Do not run the app or play the book. The new claims fail against the current app until the
build. Edit only under the books and the spec folder. Run
`ostler book check <module> --app <repo root>` for each service until it exits 0.

**Done when** `ostler book check` exits 0 for every touched book.

## 4. Review

Dispatch one reviewer with none of this session's context, on a strong model. Give it the
story path, the epic path, `model.md` and the book paths you touched. It changes nothing
and answers two questions:

1. Which acceptance criterion or journey step has no cell in the model, and which bound or
   refusal the story implies has no input class?
2. Which decided cell has no claim a run can judge, and which claim would pass on the
   unchanged system?

Answer each real gap in the model and the book, then run step 3's check again. List a gap
the story and the epic do not support in your report, with the reason.

**Done when** every gap is answered or listed, and `ostler book check` exits 0. Commit the
model and the book by path with the `Epic:` and `Story:` trailers, then run the coder-dev
command on `$ARGUMENTS`.
