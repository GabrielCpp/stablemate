---
agent: agent
---

# okf-builder — adjudicate one blocked finding: which side is wrong?

A repair turn was handed this doctor finding {{ workhorse_var('item_target') }} three times
and it came back standing every time. The repair turn only ever edits the book, and this
finding is a claim about the **correspondence** of two representations — the book and the
code — so a reader of one of them cannot say which is wrong. You read both, against the
story that states the intent, and you name the side. Nothing here is excused: the finding
stays in doctor's report until the side you name is repaired.

Load the method: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}
The finding codes and what each one claims: `{{ skill_path_ref("ostler-okf", "references/doctor-codes.md") }}`
The chain you must write, and its shape tests: {{ skill_load_ref("root-cause", skill_dir() + "/root-cause/SKILL.md") }}

## The finding

- code: `{{ workhorse_var('item_code') }}`
- target: `{{ workhorse_var('item_target') }}` ({{ workhorse_var('item_kind') }})
- what the last repair turn said: {{ workhorse_var('blocked_reason') }}
- the book node(s) it is raised on: `{{ workhorse_var('nodes') }}`
- doctor's findings, verbatim:

```json
{{ workhorse_var('item_findings') }}
```

- service: `{{ workhorse_var('service') }}` — features root: `{{ workhorse_var('features_root') }}`
- repo root: `{{ workhorse_var('repo_root') }}`
- source root: `{{ workhorse_var('source_root') }}`

## The other side

The `code:` targets under those nodes — the source you must open, every one of them,
before you decide anything:

```json
{{ workhorse_var('code_refs') }}
```

{% if workhorse_var('story') %}
The story the code under those nodes was last committed to (the `Story:` trailer on the
most recent commit over those targets, via `ostler query story-for-node`):

```json
{{ workhorse_var('story') }}
```

{% if workhorse_var('story_resolved') == 'true' %}
Its text — the acceptance criteria in it are the intent both book and code answer to:

```markdown
{{ workhorse_var('story_text') }}
```
{% else %}
The trailer names a story the planning graph does not hold. Treat it as **no story**: the
code is the intent by construction. Say so in the chain.
{% endif %}
{% else %}
**No story covers these nodes.** No commit over their `code:` targets carries a `Story:`
trailer, so the code is the intent by construction: the book yields, unless the source
itself violates a repo-wide invariant.
{% endif %}

{% if workhorse_var('warnings') and workhorse_var('warnings') != '[]' %}
Warnings from the join (a citation that resolves to nothing, a node with no `code:`):

```json
{{ workhorse_var('warnings') }}
```
{% endif %}

## How to decide

The story is the spec. Each of book and code is judged by whether it matches the story.

1. **Read the source** at every code ref. For a locator finding (`ambiguous-locator`,
   `unnamed-interactive`, `duplicate-bullet`) that means the rendered element: its role, its
   accessible name (`aria-label`, label text, visible text), and whether two controls really
   share both. For a citation finding (`missing-code-symbol`, a drifted `code:`) that means
   whether the symbol exists under any name, or is gone.
2. **Read the book node(s)** and the finding against what you saw. The finding is a claim
   that book and code disagree; now you know how.
3. **Name the side.**
   - `book` — the source, read against the story, is right, and the book misdescribes it:
     a duplicated `name:` bullet where the source carries one `aria-label`; a `role:` the
     element does not have; a citation to a symbol that was renamed. The row returns to
     the drain with your chain as its context, and the next repair turn edits the book
     with the fact you found.
   - `code` — the source is wrong. Either it contradicts an acceptance criterion in the
     story, or it violates a **repo-wide invariant** that holds with no story stating
     it — the accessibility rules first among them: two interactive controls with one
     role and one accessible name, an interactive control with no accessible name. A
     seed is filed in the story's epic (else the invariant epic) and a `known-defect:`
     bullet naming it goes on each node the finding is raised on, which doctor takes
     back the moment the seed closes or the finding stops firing.
   - `story` — two acceptance criteria in the story conflict, and no reading of the
     source satisfies both, or the story requires what an invariant forbids. Rewriting
     intent is not yours to do: the conflict is recorded on the story and the run parks
     on the operator gate with your chain as the question.

   With **no story**, the only `code` verdict is an invariant violation. Everything else
   is `book`.

4. **Write the chain**, numbered, as the root-cause skill describes: why a fix is needed,
   what decision caused it, what prevents it, until the answer is about the correspondence
   rather than this repo. Quote what you read in the source — the line, the attribute —
   because the chain is the observation a `code` verdict rests on, and the seed carries it.

Do not edit the book, the source, or the planning graph. The routing writes the seed and
the bullet; your output is the verdict and the chain.

## Output

- `verdict`: one of `book`, `code`, `story`.
- `chain`: the numbered why-chain, with the source evidence quoted in it.
- `seed_summary`: on `code` only — one line stating the defect in the source as an
  engineer will read it on the seed (element, file, what is wrong). Empty otherwise.
