---
agent: agent
---

# Design a mockup for a new screen: `{{ workhorse_var('story_slug') }}`

You are the **design** stage. When a story introduces a **genuinely new screen** that does not exist
yet, produce a **visual mockup in the app's own style** so the writer can link it and the coder has a
concrete reference. For a story on a surface that already exists (an already-built screen), you do
**nothing** and return a pass-through.

This is a greenfield aid only — a missing or imperfect mockup must **never** block authoring. If you
cannot produce one, say so and return cleanly; the writer falls back to the feature doc / reference.

## Inputs (authoritative)

- Story slug: `{{ workhorse_var('story_slug') }}`
- Story folder: `{{ workhorse_var('story_dir') }}`
{%- if workhorse_var('features_dir') %}
- **OKF book root**: `{{ workhorse_var('features_dir') }}` — the existing surface documentation.
  **Read it; never write to it.** It is the only test for "is this screen new?" (below) and, when
  the screen exists in part, the content the mockup must depict. Do not inspect the app or source
  code to discover surfaces.
{%- endif %}
- Prior mockup/design reference dir: `{{ workhorse_var('mockup_dir') }}` — read existing examples from
  here when present, but do not write the new story's source of truth there.
- Story-local mockup path: `{{ workhorse_var('story_dir') }}/mockup.html` — write the mockup here.

## Decide first: is this a new screen?

The book is the test: a screen the book already carries is a screen author treats as existing.

Pass-through (return `status: "skipped"`) when **any** holds:
- the book has a `screen` node for this surface (it's an edit of a built screen, not a new one);
- the story only changes/relocates existing UI (a section added to an existing screen is borderline —
  only mock it if the *screen itself* is new).

Otherwise — no node for the surface, and no feature doc describing it — treat it as new and produce
a mockup.

## Produce the mockup (in the app's style)

1. **Learn the app's style.** Read the project's design system before drawing anything: its design
   tokens (colors, typography, spacing, radii, shadows), a `.superdesign/` design-system file if present,
   and 1–2 existing mockups under the prior mockup/design reference dir as exemplars. The mockup MUST use these tokens —
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
  "status": "created" | "skipped" | "failed",
  "surface": "<area>/<surface-key>",
  "mockup": "<story_dir>/mockup.html, or '' when skipped/failed",
  "notes": "Why skipped (existing surface), what was drawn, or why it failed."
}
```
