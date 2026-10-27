## Scope and follow-ups

The Acceptance Criteria are the bar, as a person using the running app would observe them.
When meeting one needs a root-cause fix across the surface, that whole fix is in scope. A
symptom patch that leaves a criterion half met is not done.

The story ships a slice of a working app, and it starts from a working main. So every
failure you meet is this story's to fix: a gate, a test, the build, the
stack's bring-up or its setup code, wherever that code sits. A failure is never a follow-up.

A follow-up is undone product work on this story's feature that the working slice does not
need: a refactor, a wider surface, a polish the criteria do not ask for.{% if not follow_up_title %}
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

## Blocked

Return `blocked` only for a decision an operator alone can make: a product call the story
and the repo's decisions leave open, a credential, a real deploy, a spend. First try every
route the repo offers: its docs, its `docs/decisions/` records, its skills, its fixtures.
A missing fixture, seed, migration or data row is not a block. Building it is in scope. On
`blocked`, `notes` holds the one question that would unblock you and what you ruled out.
