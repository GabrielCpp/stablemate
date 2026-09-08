---
type: concept
slug: workflow-type-badge-style-rules
title: Workflow type badge style rules
---
# Workflow type badge style rules

Workflow type badges present a workflow kind supplied with the fleet row or repository-menu
data. The [fleet view's type-hue method](../runs-fleet-view.md#method-type-hue) supplies a
stable `0`--`359` hue for any kind without requiring a palette entry. The [badge renderer](#typebadge)
applies that hue as a CSS custom property; these rules give it its appearance and reserve fixed
colours for the established `coder` and `author` kinds.

The renderer is shared by fleet rows, selected-run headers, and repository-menu options. It emits
only the badge for a non-empty type, so an unknown or missing workflow kind does not leave an empty
chip in any of those surfaces. The type is text content and the same value is copied to
`data-type`, while the projected hue is passed through as `--type-hue`; CSS is responsible for
the visual treatment.

Every badge uses the dashboard's monospaced face at 10px, uppercase text with 0.04em letter
spacing, 1px by 5px padding, a 3px corner radius, weight 600, and the shared near-black
`--on-accent` ink. A generic kind's background is `hsl(var(--type-hue, 210), 45%, 58%)`, falling
back to hue 210 if the renderer did not supply one. The explicit selectors take precedence over that
fallback: `coder` is teal `#2f9e8f` and `author` is purple `#8a6ff0`. New non-empty kinds retain
the generic treatment, while the [workflow type field](workflow-container.md#field-workflow-type)
documents why an empty kind renders no badge at all.

- code: `groom/groom/assets/dashboard.css::.badge`
- code: `groom/groom/assets/dashboard.css::.badge[data-type="coder"]`
- code: `groom/groom/assets/dashboard.css::.badge[data-type="author"]`

## Methods

### TypeBadge

- sig: `TypeBadge({ type, hue }) -> badge element | null`
- does: returns no element when `type` is empty or otherwise falsey
- verify: absent(subject="workflow type badge for an empty type")
- does: renders a `span` with class `badge` when `type` is non-empty
- verify: visible(locator=".badge[data-type='coder']", text="coder")
- does: uses the type value as both the badge text and its `data-type` value
- verify: visible(locator=".badge[data-type='coder']", text="coder")
- does: passes the projected hue through as the `--type-hue` inline custom property
- verify: visible(locator=".badge[data-type='coder'][style*='--type-hue']", text="coder")
- code: `groom/groom/assets/dashboard.js::TypeBadge`
