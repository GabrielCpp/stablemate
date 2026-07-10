---
name: stablemate-accessibility
description: "The universal accessibility contract for any UI, framework-neutral — every interactive element carries a role, an accessible name, and keyboard operability; focus is always deliberate; state is perceivable without sight; contrast meets WCAG AA. Load for any screen/GUI work; a framework skill (react-router-a11y, htmx-accessibility, flutter-ui) supplies the concrete mechanics. Applies to **/*.tsx,**/*.jsx,**/*.dart,**/*.html,**/templates/**,**/assets/**/*.js."
metadata:
  generated_by: farrier
  source: library/skills/accessibility/accessibility/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-accessibility/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# The Accessibility Contract

This is the framework-neutral definition of what "accessible" means. It states the *contract*;
the concrete mechanics of meeting it are framework-specific — pair this with the matching framework
skill for the stack you're in:

- HTMX / server-rendered HTML / vanilla JS → [`../stablemate-htmx-accessibility/SKILL.md`](../stablemate-htmx-accessibility/SKILL.md)
- React Router + MUI → the `react-router-a11y` skill
- Flutter → the `flutter-ui` skill

Accessibility is the actual goal — screen-reader users, keyboard-only users, and low-vision users
must be able to operate the thing. **Machine-legibility is a free consequence, not the reason.** A
control that a screen reader can name and operate is exactly a control that a deterministic tool can
find and drive: a `getByRole(role, {name})` locator, an axe scan, and the OKF `role:`/`name:`/
`keyboard:` bullets an `ostler graph` node carries all read the *same* DOM signals. A control with
no role or accessible name is simultaneously an a11y failure and a documentation gap — the two are
the same fact. Do it because it's right; the tooling falls out for free.

## The five obligations

Every piece of UI you touch owes all five. None is optional, none substitutes for another.

### 1. Role — every meaningful element announces what it *is*

- Prefer a **native semantic element** (`<button>`, `<a>`, `<nav>`, `<table>`/`<tr>`/`<td>`,
  `<ul>/<li>`, `<label>`, `<h1>`…`<h6>`, `<main>`/`<header>`/`<footer>`) — it carries its role for
  free. Reach for an explicit `role="…"` only when no native element fits, and then give the
  matching role for the *structure* (`role="list"`/`"listitem"`, `role="table"`/`"row"`/`"cell"`).
- **Never leave a functionally interactive element role-less.** A clickable `<div>`/`<span>`
  (a bare `div` + click handler) is invisible to a screen reader and to keyboard navigation — it
  does not exist for those users. Use a real `<button>`/`<a>`, or `role="button"` + keyboard
  handling if a native element genuinely can't be used.

### 2. Name — every interactive element has an accessible name

- Icon-only controls need an explicit accessible name (`aria-label` / `aria-labelledby`) — there is
  no visible text to read. A purely decorative icon next to visible text should be hidden
  (`aria-hidden`) instead, not named twice.
- Every input needs a programmatically associated `<label>` (or `aria-label` as a fallback). **A
  placeholder is not a label** — it vanishes on input and most screen readers don't announce it.
- This is the cheapest, highest-value fix: without a name a screen reader announces a bare
  "button" / "textbox" with no purpose. It's the most common a11y failure in the wild and the
  easiest to prevent at write time.

### 3. Keyboard — everything mouse-operable is keyboard-operable

- Everything reachable/operable with a mouse must be reachable and operable with the keyboard
  alone. Tab order follows visual/reading order. A custom clickable element needs `tabindex="0"` +
  Enter/Space handling — or, better, *is* a real `<button>`, which gets this for free.
- **No keyboard traps:** the user can always Tab or Escape out of any widget that is not an
  intentional modal focus trap.
- Motor-impaired users, screen-reader users, and many power users never touch a mouse.

### 4. Focus — focus is always somewhere deliberate

- **Never suppress the focus outline** (`outline: none`) without an equally visible replacement.
- **Modals/dialogs/drawers:** on open move focus in; trap Tab/Shift+Tab while open; on close return
  focus to the element that triggered it — never drop it to `<body>`.
- **After a context change** the DOM doesn't reload (SPA route change, an async swap, a completed
  save): move focus to the new main heading/landmark or the result message, so assistive tech knows
  the user is now somewhere else. A sighted user gets an unmistakable visual cue; a screen-reader
  user's entire "where am I" model is wherever focus sits — if focus doesn't move, the transition
  didn't happen for them, even though the page rendered perfectly.

### 5. Perceivable state — meaning never lives in a single channel

- **Never convey state through color alone** (error, required, success, disabled). Pair color with
  an icon, text, or an ARIA attribute (`aria-invalid`, `aria-required`, `aria-disabled`,
  `aria-describedby`) so a color-blind or non-visual user gets the same information.
- **Async and pushed state must be announced, not just shown.** Loading, an arriving error, a
  background update pushed from the server — put the text in an `aria-live` region
  (`polite` for status, `assertive` for errors needing immediate attention), not a spinner or a
  toast only a sighted user can see.
- **Contrast:** text meets WCAG AA (4.5:1 body, 3:1 large text / UI affordances). Prefer palette
  tokens tuned for AA over inventing custom colors; when you must add a custom color, check its
  contrast against the background it's actually used on before committing.

## Done means

- Every element that carries meaning has a **role** and an **accessible name** a screen reader (or a
  test's `getByRole`, or an `ostler graph` node's `role:`/`name:` bullet) can discover.
- The touched surface is **fully operable with the keyboard alone**, and every control's purpose is
  clear from focus alone.
- **Focus is always deliberate** — never dropped to `<body>`; moved on modal open/close, context
  change, and async completion.
- **No information is color-only**, async/pushed state is announced via `aria-live`, and text meets
  WCAG AA contrast.
- Correct visual rendering proves **none** of the above — verify each independently.

## Verification

- **Automated (cheap, mechanical):** run an accessibility scan on the touched surface as part of QA
  — axe (`@axe-core/playwright`, `jest-axe`), `pa11y`, or a static HTML linter with a11y rules
  (`html-validate`). This catches missing names/roles and contrast without a human. This is what the
  coder-workflow lint/QA gate runs; see the framework skill for the exact command.
- **Manual smoke:** Tab through the touched surface with the mouse untouched — confirm every control
  is reachable, operable, and its purpose is announced by focus alone.
