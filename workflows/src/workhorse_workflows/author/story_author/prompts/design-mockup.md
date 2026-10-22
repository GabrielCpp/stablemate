---
agent: agent
---

# Design a mockup for a new screen: `{{ workhorse_var('story_slug') }}`

Change only the artifacts named by this task. Leave them uncommitted: do not install dependencies,
run repository-wide checks, stage, commit, push, or alter branches/remotes; Author validates and
delivers after all authoring turns finish.

Browser inspection is ephemeral. Do not save screenshots, evidence, or rendered exports in the
repository; the story-local `mockup.html` is this turn's only output.

You are the **design** stage. Produce a **visual mockup in the app's own style** so the writer can
link it and the coder has a concrete reference.

**The decision to design has already been made.** The workflow reached you only because this story
lists a service whose book is a web or mobile app; any other story never gets here. So do
not re-litigate whether a mockup is warranted, and do not go looking for evidence that the surface
already exists — depict the surface this story delivers, whether it is new or a change to a built
screen. Your job is to draw it, not to decide whether to.

The story cannot be written without a mockup. If you genuinely cannot produce one, return
`failed` with the reason in `notes`. The story is then blocked and the reason reaches the operator.

## Inputs (authoritative)

- Story slug: `{{ workhorse_var('story_slug') }}`
- Story folder: `{{ workhorse_var('story_dir') }}`
{%- if workhorse_var('services_dir') %}
- **OKF book root**: `{{ workhorse_var('services_dir') }}` — the existing surface documentation.
  **Read it; never write to it.** Where it already describes this surface in part, it is the content
  the mockup must depict. Do not inspect the app or source code to discover surfaces.
{%- endif %}
{%- if workhorse_var('milestone_mockups_dir') %}
- **Milestone mockups**: `{{ workhorse_var('milestone_mockups_dir') }}` — the approved milestone's
  mockups, one per journey. Read the one this story belongs to. The story mockup must agree with it
  on layout, components and wording, and may refine it for this story's scope.
{%- endif %}
- Prior mockups: `mockup.html` beside earlier stories under `{{ workhorse_var('epics_dir') }}` —
  read one or two as exemplars when they exist. There is no gallery directory to write into; a
  mockup belongs to the story that needed it.
- Story-local mockup path: `{{ workhorse_var('story_dir') }}/mockup.html` — write the mockup here.

## Produce the mockup (in the app's style)

1. **Learn the app's style.** Read the project's design system before drawing anything: its design
   tokens (colors, typography, spacing, radii, shadows), a `.superdesign/` design-system file if present,
   and 1–2 prior story mockups as exemplars. The mockup MUST use these tokens —
   never invent a new palette, type scale, or component language.
2. **Generate with superdesign when available.** Prefer the **superdesign** design skill if it is
   installed — it analyses the repo's design tokens and produces mockups in the app's style. The
   official skill drives the SuperDesign CLI, which needs `npm install -g @superdesign/cli` and a
   one-time `superdesign login` (browser OAuth); the skill installs the CLI and verifies login itself.
   Use this path when the CLI is installed and already authenticated on this machine, and take its
   output as the mockup.
   - **Fallback (skill absent, or not authenticated — e.g. a headless run with no login):** hand-write
     a single self-contained HTML file (inline `<style>`, no external assets) that renders the screen
     in the app's style, grounded in the design tokens and exemplars above. This path needs no network,
     login, or API key — use it whenever the CLI path is unavailable rather than blocking.
3. **Depict the real screen, all states.** Cover the documented user journey(s) — the book's `flow`
   nodes this screen takes part in — and the states the goal implies (happy path **plus** empty /
   loading / error), using the content from the book and the story's seeds, not lorem-ipsum.
4. **Write it inside the story.**
   - Save to `{{ workhorse_var('story_dir') }}/mockup.html`. The story owns the mockup; do not put the
      new source of truth under a global `docs/design/local/` gallery.
   - Do not create or update any inventory, manifest, or OKF book file. Return the story-local path in
     `mockup`; the workflow passes it directly to `write_story`.

{% block repo_design_rules %}{% endblock %}

## Final response (REQUIRED, exact shape)

```json
{
  "status": "created" | "failed",
  "surface": "<area>/<surface-key>",
  "mockup": "<story_dir>/mockup.html, or '' when it failed",
  "notes": "What was drawn, or why it could not be."
}
```
