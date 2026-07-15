---
agent: agent
---

# Triage {{ repo.name | title }} QA Failures

QA failed for one story. Before any fix is attempted, **triage** the findings: decide, per
finding, whether the work belongs **inside this story** (and grow the story to cover it) or is
the existing **in-AC** kind of fix, or is **genuinely separate scope** for the backlog. This is
a routing-and-bookkeeping stage — **you do not change product code here.**

The point of this stage is to **stop deferring real defects**. A failure on a surface this story
touched is the responsibility of this story, even when it sits just outside the literal wording of
an acceptance criterion. Deferring such defects to a backlog lets breakage compound. So the
default for a real, related defect is: **scope it into the story** (amend the ACs) and send it back
to implementation — where it gets built *and* re-validated by QA — not file it away.

## Inputs (authoritative — do not rediscover)

The workflow supplies these. Use them exactly as given:

- Story path: `{{ workhorse_var('story_path') }}`
- Spec artifact directory: `{{ workhorse_var('spec_dir') }}`
- QA evidence directory: `{{ workhorse_var('qa_dir') }}`

Triage **only** the story at the story path above. Do NOT search the repo, git history, or branch
state to guess a different story. If the story path is blank or missing, stop and report that the
workflow did not provide a usable story path — do not pick a story yourself.

If `{{ workhorse_var('spec_dir') }}` is blank, derive `<story-name>` from the story folder name in
the story path. The QA report is `{{ workhorse_var('spec_dir') }}/qa.md` (machine verdict in
`qa.json`); the evidence is in the `qa/` directory beside `story.md`.

### Rescope budget (read this — it changes your decision)

- Rescopes already spent on this story: **{{ workhorse_var('triage_scope_count') }}**
- Maximum rescopes allowed: **{{ workhorse_var('max_triage_scopes') }}**

If spent **>=** maximum, you have **no rescope budget left**: you must NOT choose `rescope`. File
any still-unaddressed adjacent/hardening items to the backlog and route the in-AC failures to the
fix loop (`qa_fix`). The story will either pass on the in-AC fixes or be flagged for a human — it
will not loop forever. (A deterministic guard enforces this too, but decide honestly.)

### Prior QA Notes

{{ workhorse_var('qa_notes') }}

## Required Context

Read:

- `AGENTS.md`
- `{{ instruction_ref("developer") }}`
- the story file (especially its `## Acceptance Criteria`)
- the parent `epic.md` (to judge what is *this* story vs a sibling/other epic)
- `qa.md` / `qa.json` and the captured evidence under the `qa/` directory
- plan artifacts under `docs/specs/<story-name>/` (to see the intended surface/scope)

## Classify every QA `Fail` finding

For each failure documented in `qa.md` (use its per-criterion findings as the worklist), put it in
exactly one bucket:

1. **in-AC** — the story's own code is wrong against an acceptance criterion the story already
   states (the AC is right, the implementation doesn't meet it). → handled by the QA-fix loop.
2. **adjacent defect** — a real, user-visible failure on a surface **this story touches or
   introduced**, just outside the literal AC wording (e.g. the route this story added renders a
   blank hydration frame; a 5xx on a path this story's change reaches). This is *not* separate
   scope — it is this story's surface failing. → scope it IN.
3. **hardening** — a non-functional weakness this failure exposed on this story's surface
   (a missing loading/empty/error state, an unguarded error path, a flaky precondition the QA run
   hit). Improving it makes the next story start from firmer ground. → scope it IN.
4. **orthogonal / large** — a failure on a *different* surface, another epic's concern, or work
   too large to absorb (a multi-day refactor, a cross-cutting redesign). → backlog, do not grow
   this story.

Be honest about bucket 2 vs 4: the test is **"did this story touch or cause this surface?"**, not
"is it mentioned in an AC". A blank frame on the route this story added is **adjacent (scope in)**,
not orthogonal. A transient environment artifact that QA mis-attributed (a flake, not a code
defect) is neither — note it and do not scope it.

## Decide the action and do the bookkeeping

**Choose `rescope`** when there is at least one bucket-2 or bucket-3 item **and** you have rescope
budget left. Then, editing only docs (no product code):

- **Amend the story's acceptance criteria.** Under the story's `## Acceptance Criteria` heading,
  append new criteria covering the scoped-in defects and hardening, matching the existing list's
  style (plain bullets or `**ACn**` numbering — continue the sequence if numbered). Group them
  under a sub-line so the provenance is clear, e.g.:

  ```markdown
  <!-- triaged from QA (story <slug>, <today's date>) -->
  - The `/projects/:id` route renders no blank/loading-only frame at first paint (HydrateFallback skeleton). [triaged: adjacent]
  - The reports route returns no 5xx for an authorized user on the happy path. [triaged: hardening]
  ```

  Each new AC must be **observable and testable** the same way the originals are — it is about to
  be implemented and QA'd. Do not restate an existing AC.
- **Log the hardening ratchet.** Append an entry to `docs/qa/hardening-log.md` (create it with a
  `# Hardening Log` header if absent): the story slug, the date, and one line per scoped-in item
  with its bucket. This is the record that the process got stronger this story.
- **File orthogonal items** (bucket 4) to `{{ workhorse_var('spec_dir') }}/backlog-items.json` (see
  format below) so they are captured without bloating this story.
- Do **not** touch product source, tests, `qa.md`'s verdict, or the story `## Implementation
  Status`. Implementation happens when the story re-enters dev.

**Choose `qa_fix`** when every finding is bucket 1 (pure in-AC), **or** when you are out of rescope
budget. Still file any bucket-4 items to the backlog; if out of budget, also file the unaddressed
bucket-2/3 items to the backlog so they are not lost. Do not amend ACs on this path.

### Backlog item format

`{{ workhorse_var('spec_dir') }}/backlog-items.json` is a JSON array; append (don't overwrite)
objects shaped like:

```json
{ "id": "kebab-case-handle", "description": "One self-contained line describing the work.", "section": "## <Domain>" }
```

`section` is optional. A deterministic node drains this file into the repo backlog.

## Structured Output Requirement

Return this exact JSON object in your **final response**, after a short markdown summary of how you
classified the findings and what you changed:

```json
{
  "triage_action": "rescope" | "qa_fix",
  "qa_failure_class": "code" | "evidence" | "environment"
}
```

- `triage_action` must be exactly `"rescope"` or `"qa_fix"` (lowercase).
- Use `"rescope"` **only** if you amended the ACs and have budget left; otherwise `"qa_fix"`.
- `qa_failure_class` classifies WHAT the remaining failure needs (lowercase, exactly one of):
  - `"code"` — a product code/test change is still required to satisfy an AC.
  - `"evidence"` — the product code is already correct and all build/test gates are green; what
    remains is ONLY evidence work: capturing/refreshing screenshots or outputs, widening sweep
    coverage, re-running a driver to completion, or fixing an evidence-artifact schema/shape.
    Be strict: if ANY finding needs a code change, the class is `"code"`.
  - `"environment"` — the dev stack/fixtures/emulator must be repaired or seeded before any
    verdict is possible.
  The workflow uses this to grant one extra verification-only pass instead of giving up when the
  budget is exhausted but the only remaining work is `"evidence"` — classify honestly; a wrong
  `"evidence"` label wastes the bonus pass, a wrong `"code"` label sends a finished story to
  manual review.

Example final response (after the markdown summary):

```json
{
  "triage_action": "qa_fix",
  "qa_failure_class": "evidence"
}
```

## Stop / safety rules

- Never set the story status to `QA passed` — QA reruns and decides that.
- Never edit product code, tests, or `qa.md`'s verdict here.
- If the QA "failure" is clearly a transient environment artifact or a QA-driver bug (the evidence
  shows the behavior actually working), say so in your summary and route `qa_fix` (the fix loop /
  setup-fix handles environment issues) — do not invent ACs for a non-defect.
- If you cannot tell whether a finding is adjacent or orthogonal, prefer scoping it **in** (bucket
  2) when this story touched the surface — fixing forward is the goal — but never grow the story
  past your rescope budget.
