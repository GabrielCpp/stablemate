---
agent: agent
---

# Document the story (OKF UI profile)

The implementation just passed review and is about to enter QA context generation. Your
job is to **merge everything this story changed into the current OKF book** so new services,
screens, components, commands, endpoints, interactions, concepts, formats, and flows are
documented before QA derives obligations. This is an incremental one-story update, not a
changelog or a bulk build.

Load the skill and follow it: {{ skill_load_ref("ostler-documentation", skill_dir() + "/ostler-documentation/SKILL.md") }}
It carries the full loop (scaffold → author → fmt → doctor), the node-type vocabulary, and
the linter rules; obey it. The reference for the type table and bullets is the
`ostler` skill it links to.

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
   Journeys`, and the story's `spec_dir` (`plan-context.json` lists the services/repos it
   touched). Inspect both the working tree and commits made on the current story/epic branch
   since its base, including QA, regression, CI, and merge remediation. From that complete
   implementation delta,
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
   exist), and `verify:` to the observation that proves the node — a call from ostler's check
   vocabulary, e.g. `http_status(409, title="Conflict")`, never a test name. Run `ostler checks`
   for the signatures before writing a call you have not written before — the arguments are not
   uniform (`absent` takes `subject`, `visible` takes `locator`), and a guessed one is a blocking
   `unparsed-check` and a wasted gate lap. Keep every path link resolving.
   Never weaken an invariant, journey completion condition, persistence rule, event
   contract, or concurrency requirement merely to match the implementation. Such drift
   is a product/author decision, not a grounding edit.
   **One provable claim per normative bullet.** Each value of `does:`, `when:`, `returns:`,
   `raises:`, `status:`, `error:`, `auth:`, `persistence:`, `emits:`, `consumes:`,
   `concurrency:`, `idempotency:`, `required:`, `default:` or `semantics:` becomes one QA
   obligation, proved by one scenario. Merging this story's delta into a sentence that already
   holds three requirements makes a bullet where the scenario proves whichever clause the
   planner read and the rest ships claimed-as-covered — the story passes QA over behavior
   nobody tested. Split on the real seams (the success effect, each error case, what is
   persisted, what is emitted) by repeating the key; `doctor` errors past 700 characters of
   prose in one bullet.
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

## Output

Output JSON only:

```json
{"status": "documented", "nodes": ["docs/features/acme/gui/screens/example.md#example-panel"], "notes": "Updated the current OKF contracts and grounding for the reviewed implementation."}
```

`status` is one of `documented`, `not_required`, or `blocked`.
`documented` means the full current contracts are updated and `doctor` has no error finding in
the affected nodes. Report unrelated pre-existing findings but do not rewrite unrelated books.
`not_required` requires both a precise explanation of why no observable contract changed **and**
that every changed production file was already directly grounded — see step 3; a grounding
bullet you had to add makes the answer `documented`.
For `documented`, `nodes` must list every affected OKF node by exact graph identity, preserving
section anchors. For `not_required`, return an empty `nodes` list.
