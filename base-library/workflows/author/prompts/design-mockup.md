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
- Knowledge record: `{{ workhorse_var('knowledge_record') }}` — read it; its `gaps[]` / `new[]` tell you
  whether this surface is new (a `missing`/`unreachable` screen with no built `new[]` component) and
  what the screen must contain.
{%- if workhorse_var('features_dir') %}
- Feature-doc root: `{{ workhorse_var('features_dir') }}` — this surface's feature doc / journeys are
  the content the mockup must depict.
{%- endif %}
{%- if workhorse_var('surface_manifest') %}
- Surface manifest: `{{ workhorse_var('surface_manifest') }}` — set this surface's `mockup` field to the
  file you produce, so the writer resolves it.
{%- endif %}
- Mockup dir: `{{ workhorse_var('mockup_dir') }}` — write the mockup under `<mockup_dir>/local/`.

## Decide first: is this a new screen?

Pass-through (return `status: "skipped"`) when **any** holds:
- the record's `new[]` already has a built component for this screen (it's an edit, not a new screen);
- the story only changes/relocates existing UI (a section added to an existing screen is borderline —
  only mock it if the *screen itself* is new).

Otherwise treat it as a new screen and produce a mockup.

## Produce the mockup (in the app's style)

1. **Learn the app's style.** Read the project's design system before drawing anything: its design
   tokens (colors, typography, spacing, radii, shadows), a `.superdesign/` design-system file if present,
   and 1–2 existing mockups under `<mockup_dir>/local/` as exemplars. The mockup MUST use these tokens —
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
3. **Depict the real screen, all states.** Cover the documented user journey(s) and the states the goal
   implies — happy path **plus** empty / loading / error — using the content from the feature doc and the
   record's gaps, not lorem-ipsum.
4. **Write and register it.**
   - Save to `<mockup_dir>/local/<surface-key>.html` (derive `<surface-key>` from the record's `surface`).
   - If an `index.html` / `README.md` mockup gallery exists in that dir, add an entry for the new file.
   - If a `surface_manifest` is configured, set this surface's `mockup` field to the new file's repo path
     (create the surface entry if absent), so `write_story` links it.

{% block repo_design_rules %}{% endblock %}

## Final response (REQUIRED, exact shape)

```json
{
  "mockup_result": {
    "status": "created" | "skipped" | "failed",
    "surface": "<area>/<surface-key>",
    "mockup": "<mockup_dir>/local/<surface-key>.html, or '' when skipped/failed",
    "notes": "Why skipped (existing surface), what was drawn, or why it failed."
  }
}
```
