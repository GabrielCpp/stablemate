### `static-template` — a repeated node's name discriminates no instance

The node declares `one-per:`, so it stands for a whole class of generated controls at once — but
its `name:` template has no bindable hole rooted at the iteration variable: it is all literal
text, or all opaque expressions like `{t("row_edit")}`. Every instance renders the same
accessible name (or one no consumer can predict), so nothing — not a QA plan, not a screen
reader user — can say *which* row it addressed, and in strict mode the locator matches them all.

Repair from the rendered name in the source, not from the bullet:

- If the render **does** interpolate a per-instance datum, write it into the template:
  `` name: `{stage.name} stage row` ``. A hole that is a plain dot-path rooted at the
  `one-per:` variable is bindable; any other expression is kept verbatim and matched as a
  wildcard — never evaluated — so it contributes no discrimination.
- If the render genuinely carries no per-instance datum, that is an accessibility defect in the
  app — N identical controls announced identically. Record what you saw in prose and leave the
  finding standing; a human decides between an app fix (interpolate a datum, or an `aria-label`)
  and a waiver. **Do not invent a datum the render does not contain.**
