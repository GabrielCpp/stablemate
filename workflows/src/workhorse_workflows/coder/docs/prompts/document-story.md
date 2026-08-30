---
agent: agent
---

# Document the story (OKF UI profile)

The implementation just passed review and is about to enter QA context generation. Your
job is to **merge everything this story changed into the current OKF book** so new services,
screens, components, commands, endpoints, interactions, concepts, formats, and flows are
documented before QA derives obligations. This is an incremental one-story update, not a
changelog or a bulk build.

Load the skill and follow it: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}
It carries the full loop (scaffold → author → fmt → doctor) and links the written model, which
is the authority for everything below: `references/node-types/<type>.md` for the type you are
about to write (its keys, required sections, relationships, doctor codes),
`references/bullet-grammar.md` for what a normative bullet owes and which claim a `verify:` or a
`fixture:` attaches to, `references/check-vocabulary.md` for the checks and their signatures, and
`references/defect-kinds.md` for what the reviewer after you rejects on. Read the type reference
before authoring a type you have not authored this run.

## Inputs

- Story path: `{{ workhorse_var('story_path') }}`
- Spec dir: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_path') }}`
- OKF features root: `{{ workhorse_var('features_root') }}`
- Parent epic with authoritative user journeys: `{{ workhorse_var('epic_path') }}`
- Context mode: `{{ workhorse_var('context_mode') }}`
- Context notes: `{{ workhorse_var('context_notes') }}`
- Previous deterministic gate notes: `{{ workhorse_var('gate_notes') }}`
- Previous semantic review notes: `{{ workhorse_var('review_notes') }}`

{% if workhorse_var('obligations') %}
## Grounding worklist — already computed, do not re-derive it

The same deterministic mapper the gate uses has already joined this story's diff against the
book. These are the changed production references no node's `code:` bullet owns yet, spelled
the way the source inventory spells them:

{% for ref in workhorse_var('obligations') %}
- `{{ ref }}`
{% endfor %}

This list **is** step 3's worklist. Do not reconstruct it by hand — do not grep the book for
each changed symbol, and do not list a repo's files to work out what changed. That join is
arithmetic the tooling already did, it is slower and less accurate done with shell commands,
and a reference you re-spell yourself grounds nothing. Copy each entry verbatim into the
`code:` bullet of the node that documents that behavior.

An empty list where you expected entries means the mapper had nothing to map, not that you
should go compute one yourself.
{% endif %}

{% if workhorse_var('gate_notes') or workhorse_var('review_notes') %}
## Repair pass contract

This is a repair pass. Do **not** re-document the whole graph or rewrite unrelated prose.
Treat unresolved findings in the previous notes above as the complete worklist for this pass,
and edit only the files/anchors needed to close them plus any deterministic `ostler fmt`
reshaping. A deterministic note beginning `conformant;` is successful gate evidence and context,
not a grounding repair item.

Before editing, retain the stable `D1`, `D2`, `D3`, ... IDs on semantic review findings and
normalize only unresolved deterministic grounding failures as `G1`, `G2`, .... For each item:

- identify the exact file/anchor it names;
- inspect the implementation symbol or cited test before writing prose;
- either make the smallest documentation edit that the evidence supports, or weaken an
  overclaim to the exact behavior the evidence proves;
- if no implementation or test proves a claim, omit the claim or state the limitation rather
  than inventing support.

Your final `notes` must include a compact checklist summary in this form:
`D1 resolved: <file#anchor> — <evidence>; D2 resolved: ...`. If an item cannot be resolved
without a product or author decision, return `blocked` and name that item.
{% endif %}

## Steps

1. **Scope what changed.** Read the story's acceptance criteria, its parent epic's `## User
   Journeys`, and the story's `spec_dir`. Inspect both the working tree and commits made on
   the current story/epic branch since its base, including QA, regression, CI, and merge
   remediation. The services/repos the story touched:
{% if plan_services %}
{{ plan_services }}
{% endif %}
   From that complete implementation delta,
   identify what *user-facing surface, element, behavior, concept, or format* the story
   added or changed — a screen/component/interaction (GUI), a cli/command (CLI), a
   server/endpoint/invocation (HTTP/WS), a domain or code `concept`, a `flow`, or a
   `format`.
2. **If the story touched no documentable contract** (pure internal refactor, test-only,
   or configuration with no externally observable contract), there is no new prose to write.
   Do **not** invent nodes. New source files or symbols are not automatically internal:
   represent a new service, surface, element, behavior, domain/code concept, or format unless
   the diff proves otherwise. **Grounding is still owed** — go to step 3.
3. **Ground every changed production file, whatever you concluded in step 2.** A
   deterministic gate runs after you and maps the diff onto the graph: each changed
   production unit must be owned *directly* — **every** one of its changed symbols named as
   `path::symbol` in some node's `code:` bullet, or, for a file with no symbols the
   inventory can see (a config or manifest), the file path itself. A node that describes the
   behavior in prose but does not name the file does not own it; that is the "broad surface
   ownership" the gate refuses, and it is the one thing this gate exists to catch.

   The grounding worklist above is that gate's own arithmetic, run before you: work it
   directly instead of deriving your own. If a previous pass's gate notes are above, they
   list the still-ungrounded references individually. **Copy each one verbatim** — the spelling is the inventory's, not yours,
   and a symbol renamed on the way into a bullet grounds nothing. A Go method, for example,
   is `path.go::(*Type).Method`, not `path.go::Type.Method`. Grounding a file the notes
   never mentioned, or half its symbols, spends a rework pass and changes nothing.

   **A symbol or file this story deleted needs no `code:` citation at all.** The gate
   exempts a deletion on its own — do not add a bullet pointing at something that no longer
   exists to satisfy it. `ostler doctor` rejects every `code:` target that isn't there, with
   no exception, so the correct response to a deletion is to remove any bullet that now cites
   it (if the node it lived in still documents live behavior) or remove the node entirely (if
   the node described only what was deleted) — never to invent a citation for something gone.
   So a config-only story is normal work, not a no-op: find the node that already describes
   that behavior — the gate notes above name the unowned path — and add the `code:` bullet
   pointing at it. That is a documentation change, so it returns `documented` and lists that
   node. `not_required` is only correct when every changed production file is *already*
   directly owned and no contract moved; if a previous pass's gate notes name an unowned
   path, `not_required` is the one answer that cannot be right, and repeating it just spends
   the rework budget and fails the flow.
4. **When a contract did move, apply the skill's loop from existing code (Playbook B):** `ostler search`
   / `ostler list` for the node if it exists; `ostler scaffold` it if not; author the
   as-built prose and structured bullets; set `code:` / `tests:` to the **real**
   `path::symbol` you just wrote (omit `tests:` rather than invent a test that doesn't
   exist), and `verify:` to the observation that proves the node — a call from the check
   vocabulary, e.g. `http_status(409, title="Conflict")`, never a test name. Run `ostler checks`
   for the signatures before writing a call you have not written before — the arguments are not
   uniform (`absent` takes `subject`, `visible` takes `locator`), and a guessed one is a blocking
   `unparsed-check` and a wasted gate lap. Keep every path link resolving.
   Never weaken an invariant, journey completion condition, persistence rule, event
   contract, or concurrency requirement merely to match the implementation. Such drift
   is a product/author decision, not a grounding edit.

   Four rules decide whether the review after you approves. Each is written out in the skill's
   references; what follows is what they cost you if you skip them.

   - **One provable claim per normative bullet** (`references/bullet-grammar.md`, and which keys
     are normative is in the type's own reference). Merging this story's delta into a sentence
     that already holds three requirements makes a bullet where the scenario proves whichever
     clause the planner read and the rest ships claimed-as-covered. Split on the real seams by
     repeating the key; `doctor` errors past 700 characters.
   - **A check goes under the claim it observes.** Document order is the binding: a `verify:` is
     attributed to the nearest normative bullet **above** it, and one written before any of them
     belongs to the node's whole contract. A check placed above its claim is credited to the
     claim before it — the observation of a refusal filed as the observation of the success case.
   - **Every node that mints an obligation declares at least one observation.** A node whose
     `does:`/`raises:`/`states:` bullets carry no `verify:` reaches QA where any assertion
     satisfies it; `doctor` warns `undeclared-obligation` and the review rejects it.
   - **A check earns its place only if it can go red on the defect the claim forbids**
     (`references/defect-kinds.md`, `verify-overclaim`). Name the subject concretely, assert the
     before-state rather than assuming it, and discriminate the claim from its nearest plausible
     defect. Splitting a bullet does **not** by itself owe a new check per fragment: a `verify:`
     above a group of normative bullets binds to the node's contract and covers them all.

   **Fill the whole contract, not a stub.** The type's reference lists what its bullets are for;
   the bar is fields with `type`/`required`/`default`, every flag and argument item by item,
   `does:` as ordered effects, errors/exit/status codes, and for UI the
   `role:`/`name:`/`placement:`/`keyboard:`/`states:` contract.
   Prefer narrow, evidence-backed prose over broad claims: write "click controls reorder tabs"
   instead of "keyboard reordering works" unless a keyboard test proves it; write "new nested
   insertion is blocked" instead of "containers can never nest" when loaded legacy nested
   containers are preserved or degraded; and name focus/key behavior exactly as implemented.
5. **Materialize implemented greenfield journeys as OKF flows.** The author journey plan is
   planning prose, not the feature book. If the current story implements a journey slice named
   there and the book has no matching `flow` node yet, create one with `ostler scaffold flow
   <journey-slug> --service <service> --title "<Journey title>"`, then fill its `start:`, linked
   `steps:`, `end:`, and `verify:` bullets from the as-built surfaces. A greenfield
   journey is not complete until the book contains the surfaced nodes it traverses and the `flow`
   links those steps. If this story only implements an internal prerequisite for a later journey,
   say that precisely and document the prerequisite contract instead; do not invent a flow before
   a user can traverse it.
6. **Converge:** run `ostler fmt <the docs you touched>` then `ostler doctor` (from the
   docs root, `-C` if needed). Fix any error by its named remedy until `doctor` is green
   for the nodes you touched. In `semantic` multi-repo mode, repository-local doctor cannot
   resolve service-repo `code:` paths beneath the separate docs root: report its
   `dangling-code-ref` / `missing-code-symbol` findings for independent review, but do not return
   `blocked` for those two grounding codes alone. Every structural, relation, schema, and local
   grounding error remains blocking. Never silence a finding by deleting a meaningful bullet.

This is a hard gate. If the graph cannot be updated without changing an author-owned
normative decision, return `blocked`; never claim success or remove requirements to pass.

## Commit Identity

Every commit subject ends with `[{{ workhorse_var('story_id') }}]`, after its description.
Every commit also carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_id') }}` as trailers, spelled exactly so — the run record
ties a commit back to its story through them.

## Output

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
