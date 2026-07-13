---
name: stablemate-python-htmx-accessibility
description: "Accessibility for an HTMX + server-rendered HTML + vanilla-JS app (no SPA framework, no bundler) — semantic templates, ARIA on hand-authored HTML, focus management across hx-swap, aria-live for websocket/out-of-band pushes, accessible command palettes and keyboard nav, and keeping sanitized markdown perceivable. The concrete mechanics behind the universal contract for this stack. Applies to **/templates/**/*.html,**/assets/**/*.js."
metadata:
  generated_by: farrier
  source: library/skills/stacks/python/python-htmx-accessibility/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-python-htmx-accessibility/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Accessibility in an HTMX + Server-Rendered HTML App

The universal obligations — role, name, keyboard, focus, perceivable state — are defined once in
[`../stablemate-ui-accessibility/SKILL.md`](../stablemate-ui-accessibility/SKILL.md). **Read that
first.** This skill is the concrete *how* for a stack that is hand-authored HTML templates + HTMX
(`hx-*` attributes, `hx-swap`, `hx-ext="ws"`) + vanilla JS, with **no JSX, no component framework,
and no build step** — so there is no `eslint-plugin-jsx-a11y` to catch anything; the roles and
names are whatever you literally type into the template, and the a11y burden lands on three
HTMX-specific mechanics that don't exist in an SPA: **partial swaps, out-of-band pushes, and
hand-rolled keyboard widgets.**

## Semantic HTML is the whole game here — there is no component to hide behind

In a JSX app a `<Button>` at least tends to render a real `<button>`. Here, what you type is what
ships. So:

- **Interactive means a real `<button>` or `<a>`, never a `<div>`/`<span>` + JS click.** HTMX will
  happily put `hx-get`/`hx-post`/`ws-send` on a `<div>` — don't. Put HTMX attributes on a real
  `<button>` (in-page action) or `<a href>` (navigation): you get role, focusability, Enter/Space
  activation, and the disabled/`aria-pressed` vocabulary for free. A `<div hx-post>` is invisible to
  keyboard and screen reader and is an `ostler graph` doc-gap too.
- **Structure uses the structural element.** A list of workers is `<ul>`/`<li>` (or `role="list"`);
  a data grid is a real `<table>`/`<tr>`/`<td>`; page regions are `<nav>`/`<main>`/`<header>` with
  one `<h1>` and a sane heading order. A screen-reader user navigates by these landmarks and
  headings — a `<div>`-soup dashboard is one undifferentiated wall of text to them.
- **Inputs get a real `<label>`.** A `placeholder="Filter…"` is **not** a label — associate a
  `<label for>` (visually hide it with an `.sr-only`/`.visually-hidden` class if the design wants no
  visible label), or `aria-label` as the fallback. This is the single most common gap in
  hand-authored templates.

## Focus management across `hx-swap` — the #1 HTMX-specific failure

An `hx-swap` replaces a chunk of the DOM **without a document reload**, so if the element that had
focus was inside the swapped region, focus silently falls back to `<body>` — the screen-reader user
is dumped to the top of the page with no announcement. Handle every swap that could hold focus:

- **Preserve focus that should survive a swap** with `hx-preserve` on the element (e.g. the filter
  input that triggered the swap), or re-focus deliberately after it.
- **Move focus into new content that demands attention** (a gate answer form that just appeared, an
  expanded detail panel): give the swapped-in container `tabindex="-1"` and focus it in an
  `htmx:afterSwap` / `htmx:afterSettle` handler, or use `autofocus` on the primary control of the
  new fragment.
- **One global safety net**, since there is no framework doing it for you:
  ```js
  document.body.addEventListener("htmx:afterSwap", (e) => {
    const t = e.detail.target;
    if (t.matches("[data-autofocus]")) (t.querySelector("[autofocus],a,button,input") || t).focus();
  });
  ```

## `aria-live` for websocket / out-of-band pushes — the server speaks, the SR must hear it

The defining feature of this stack is the server pushing `hx-swap-oob` fragments over a websocket
(`hx-ext="ws"`) — a worker goes blocked, a status flips, a log line arrives — with **no user action
and no focus change**. A sighted user sees the card update; a screen-reader user gets *nothing*
unless the target is a live region.

- Give any region that receives pushed updates `aria-live="polite"` (status/progress) or
  `aria-live="assertive"` (a new blocked gate that needs the operator now), plus an appropriate
  `role` (`role="status"` / `role="log"` for an append-only feed / `role="alert"` for the urgent
  case). The OOB swap into that region is then announced automatically.
- Keep the live region **present in the initial HTML and stable** — screen readers only announce
  changes to a live region that already existed. Swap *content into* it; don't swap the live region
  itself in and out.
- A pushed browser `Notification` (permission-gated) is a nice-to-have on top, **not a substitute** —
  it's dismissible, easily denied, and invisible to a user watching the tab.

## Hand-rolled keyboard widgets: command palettes, `j/k` lists, shortcuts

Vanilla-JS keyboard widgets (a `⌘K` palette, arrow/`j`-`k` list nav) carry the **full** ARIA
authoring burden — nothing wires it for you. A command palette is a **modal combobox/listbox** and
owes the complete pattern:

- The overlay is `role="dialog"` + `aria-modal="true"` + `aria-label`; opening it **moves focus to
  the input and traps Tab/Shift+Tab** inside; **Escape closes and returns focus to the trigger**
  (never to `<body>`).
- The input is `role="combobox"` with `aria-expanded`, `aria-controls` → the results list; the
  results are `role="listbox"` with `role="option"` children; arrow / `j`-`k` movement updates
  `aria-activedescendant` on the input to point at the active option (don't move DOM focus per-row —
  keep it on the input and let `aria-activedescendant` do the announcing), and Enter activates it.
- A visible shortcut hint (`⌘K`) is decorative — the real requirement is the `keydown` handler plus
  the ARIA above. If a shortcut is the *only* way to reach an action, that action fails keyboard
  users who don't know it; give it a visible, focusable control too.

## Sanitized/agent-authored markdown must stay perceivable

Content rendered client-side from untrusted text (`marked` + DOMPurify) still owes a11y: keep real
headings/lists/`<pre>` in the sanitizer allow-list so the structure survives, ensure any rendered
`<img>` keeps its `alt`, and render it **into** a labeled, live region (see above) rather than a
bare `<div>`. XSS-safety and a11y are independent requirements — passing the sanitizer test proves
nothing about the reading experience.

## Linting and testing this stack — what the gate runs

There is no JSX linter here, so a11y is enforced by a **static HTML linter** plus a **runtime scan**:

- **Static (fast, no server): `html-validate`** on the templates directory, with its WCAG/ARIA rules
  on (`wcag/*`, `require-sr-only-*`, `input-missing-label`, `no-implicit-button-type`, roles-valid).
  This lints hand-authored HTML directly and is the natural per-service `lint` command in
  `agents.yml` (e.g. `html-validate <service>/templates/`). It catches missing labels, invalid
  roles, and bad heading order at write time — exactly the gaps this stack is prone to.
- **Runtime (needs the app up): `pa11y` or `@axe-core/*`** against the served page — this is the
  only way to check the *composed, post-swap* DOM and the live regions actually announcing. Run it
  in the QA phase on the live harness, after a swap/push has occurred, not just against the static
  first paint.
- **Manual smoke:** open the palette and drive the whole dashboard — open a gate, answer it, dismiss
  the palette — with the mouse untouched; confirm focus is always somewhere sensible and pushed
  updates are announced.

## Done means

Everything in the universal contract's "Done means", plus, specific to this stack: no `hx-*`/`ws-*`
attribute sits on a non-interactive element; every focus-holding `hx-swap` restores or re-homes
focus; every push target is a stable `aria-live` region; every hand-rolled keyboard widget
implements its full ARIA pattern with a real focus trap and Escape-restores-focus; and
`html-validate` on the templates is clean.
