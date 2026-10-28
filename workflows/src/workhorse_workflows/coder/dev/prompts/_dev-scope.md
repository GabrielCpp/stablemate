## Scope and follow-ups

The Acceptance Criteria are the bar, as a person using the running app would observe them.
When meeting one needs a root-cause fix across the surface, that whole fix is in scope. A
symptom patch that leaves a criterion half met is not done.

The story ships a slice of a working app, and it starts from a working main. So every
failure you meet is this story's to fix: a gate, a test, the build, the
stack's bring-up or its setup code, wherever that code sits. A failure is never a follow-up.

A copy this story adds of code the tree already has is in scope too. The lap's clone check
reports it as a failure, and the fix extracts the repeated code to one owner both callers
use, in this story. When the two copies change for different reasons, a
`[[check-clones.coincidence]]` entry in `.agent-checks.toml` names both files and one reason
per file instead.

When the clone check says the two copies sit in separate builds, the owner is a library the
repository's workspace lists and each build declares, as code-structure rule 2.13 says. The
library's manifest, its workspace entry and each build's dependency on it are in scope. Build it
without asking when a record in `{{ decisions_dir }}/*/decision.md` says where such code lives, or when the
workspace already exists and every build context, image, CI path filter and deploy stays as it
was. Otherwise return `blocked`. `notes` then holds one concrete library: its folder, its name,
its manifest, its workspace entry, each build that declares it, each build context or filter it
widens, and your recommendation. When the operator's answer settles it, write that answer to
a decision before you build, so the next story follows it without asking. Run
`ostler decisions add <short-kebab-slug> --summary "<the question, in one line>"`. It prints the
path of the new `decision.md`, under `{{ decisions_dir }}`. It refuses a slug that is already
taken, so read that decision and pick another slug. Fill the four headings in the printed file:

- `## Question`: where does code two services share live?
- `## Decided`: the operator's answer, in one or two sentences.
- `## Grounded in`: the operator's answer to <story slug>, dev stage.
- `## Context`: the copy that raised it, and what was at stake.

A follow-up is undone product work on this story's feature that the working slice does not
need: a refactor, a wider surface, a polish the criteria do not ask for. A copy that predates
this story is one, with the pattern `extract-module`.{% if not follow_up_title %}
The build and review phases file it in their result with a title a person can act on, and the
reason the slice works without it. Name the `repo` of the workspace it sits in, the `area` as
one lowercase kebab word for the module or service it belongs to, the `pattern` as a short kebab
phrase for the kind of fix, such as `extract-module` or `widen-api`, and the `symbols`, the files
or symbols it touches. The run files each one as a record on the debt register, where a person or
a later epic takes it up. A follow-up with no area or no pattern is refused. This run does not
work it.{% endif %} A product call the story leaves open is neither. It is a block, under
Blocked.

Some things read like follow-ups and are not. A defect or warning that predates this story
and that its change did not cause is not one. A remark about docs, or about the status of
`story.md` or a plan file, is not one. A note about the toolchain is not one. Each is a run
finding for the operator, and it goes in `notes`.

## The book

The run's docs phase merges this story into the repo's book under `docs/services/` after
review, and QA reads its obligations from that merge. A rule in the repo's instruction files
that the book changes with the code is met there. So the plan lists no book edits, and the
build and review phases write, stamp and doctor nothing under `docs/services/`. Read the book
to learn what the product does. A page this change will make wrong is a note for the docs
phase, and it goes in `notes`.

## Blocked

Return `blocked` only for a decision an operator alone can make: a product call the story
and the repo's decisions leave open, a credential, a real deploy, a spend, a change to how the
code ships. First try every route the repo offers: its docs, its `{{ decisions_dir }}/*/decision.md` records,
its skills, its fixtures.
A missing fixture, seed, migration or data row is not a block. Building it is in scope. On
`blocked`, `notes` holds the one question that would unblock you and what you ruled out.
