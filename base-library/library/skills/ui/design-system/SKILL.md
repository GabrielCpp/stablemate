---
name: design-system
description: "How to create (bootstrap) a design system from a reference design — palette, typography, spacing, radii, shadows, and motion captured as named, traceable tokens and wired into the app theme. Applies to **/*theme*.ts,**/*theme*.tsx,**/*theme*.dart,**/theme/**,**/design_system.dart,**/root.tsx."
applyTo: "**/*theme*.ts,**/*theme*.tsx,**/*theme*.dart,**/theme/**,**/design_system.dart,**/root.tsx"
tags: [standards]
---

# Creating a Design System

Use this when a UI surface has **no design system yet**, or has one that new work
keeps bypassing with inline magic values (`#f8f8f8`, `1px solid #e7e7e7`, `10px`).
A design system is not a style guide document — it is a **single, centralized set
of named tokens** that every component references, plus the theme object that
binds them to the UI kit. Build it once; reference it everywhere.

The framework styling skills tell you to *use* tokens and *extend* the theme
rather than inline literals. This skill tells you how to **stand the system up in
the first place** so there is a token to use. The worked examples below are drawn
from three stacks this has been done in: Flutter (token classes under
`lib/core/config/theme/`), React Native + Material Design 3 (palette derived from
mockups), and MUI on the web.

## When to create one vs. extend one

- **Extend** (add a token to an existing theme) when the central theme already
  exists and you only need a new value. That is the common case — see the
  framework styling skill.
- **Create** when there is no central theme, or the existing one covers only a
  fraction of the surface and components have started forking it with inline
  literals. Creating means establishing the token taxonomy below and the wiring,
  not just dropping one more constant.

Do not create a *second* system next to an existing one. If a theme exists,
extend it.

## The principle: every value is a named, traceable token

1. **Single source of truth.** All color, typography, spacing, radius, shadow,
   border, and motion values live in the theme/token layer — never inline in a
   component. A component reads tokens; it never defines design values.
2. **Named by role, not by value.** Tokens are named for what they *do*
   (`background.paper`, `text.secondary`, `neutral.border`, `spacing.md`), not
   for what they *are* (`grey7`, `tenPx`). Roles survive a rebrand; raw values
   don't.
3. **Traceable to a source.** Every token records where its value came from — a
   mockup, a reference/legacy screen, a brand spec, a Material baseline. Annotate
   it in a comment — a Flutter token class citing the mockup it was read off, a
   palette token citing the legacy `Layout.html.twig` lines it was sampled from. A
   token with no provenance is a guess, and guesses drift.
4. **One scale per concern.** Spacing is a single scale on a grid (4 or 8px), not
   ad-hoc numbers. Same for radii, type sizes, elevation. Scales make "looks
   consistent" automatic instead of a per-component judgment call.

## Step 1 — Derive the tokens from the reference

Work from whatever grounds the design: mockups, a running legacy/reference site,
a brand palette, or the UI kit's baseline. Extract, don't invent:

- **Palette** — brand/primary, secondary, semantic (success/warning/error/info),
  and a **neutral ramp** (the greys for surfaces, borders, dividers, disabled).
  Most inline-hex defects are missing neutrals — capture the full ramp up front.
  Record each with its source. (A mobile app can start from exactly this: a
  5-color palette pulled off the mockups — a brand base, a surface tint, plus
  secondaries.)
- **Typography** — font family/families, the weight set actually used, and a
  type scale (display → headline → title → body → label) with size/line-height.
- **Spacing** — one numeric scale on a 4px or 8px base (`xxs…xxl` or `1,2,3…`).
- **Radius** — a small named set (`sm/md/lg/pill`) mapped to component roles
  (input, card, chip).
- **Elevation / shadow** — a named set, not per-component box-shadows.
- **Motion** — standard durations and easings if the app animates.

Capture light **and** dark values for theme-variant tokens from the start if the
app supports dark mode; retrofitting dark mode onto value-named tokens is painful.

## Step 2 — Structure the token layer

Centralize tokens in one place, split by concern, with a single import surface:

- **One file (or class) per concern**, then a barrel that re-exports them. In
  Flutter that looks like `app_colors.dart`, `app_typography.dart`, `app_spacing.dart`,
  `app_radius.dart`, `app_shadows.dart`, `app_durations.dart`, all re-exported by
  `design_system.dart` so consumers write one import.
- **Separate raw tokens from theme-aware tokens.** Brand colors are constant
  across light/dark; surface/text/border colors flip. Keep the constant ones as
  plain tokens and route the variant ones through the theme's color scheme so they
  respond to mode.
- **Name the scale steps semantically** even when backed by numbers, so call
  sites read as intent (`AppSpacing.md`, not `12.0`).

## Step 3 — Bind tokens to the UI kit's theme

Tokens are inert until the theme object consumes them. Build the theme **from**
the tokens and configure component defaults centrally so components inherit the
look without per-instance overrides:

- **MUI (React Router / web).** Build `createTheme({ palette, typography, shape,
  components })` from the tokens. For roles the kit doesn't ship (custom neutrals,
  footer colors), add **typed custom palette keys via module augmentation** (a
  `theme-augmentation.d.ts` declaring the new `Palette`/`PaletteOptions` groups) —
  that is how you add groups like `neutral`/`footer`. Set recurring component looks in
  `theme.components.MuiX.styleOverrides` once (e.g. the outlined `Paper` "box"
  look) instead of repeating `sx` on every instance. See the React Router styling
  rules in the architecture skill for how components then consume it.
- **Flutter.** Build `ThemeData` in an `AppTheme.light()/dark()` from the
  token classes, set `useMaterial3: true`, and configure component themes
  centrally in one `_buildTheme`. Widgets read `Theme.of(context).colorScheme` for
  variant colors and the token classes for constant brand values.
- **React Native + Paper.** Build the MD3 theme from the palette and feed
  it to `PaperProvider`; read it through `useTheme()` and the theme spacing scale.

## Step 4 — Enforce it

- **Wire light/dark and verify both** if the app is themed.
- **Sweep the surface for existing inline literals** (`#`, `rgb(`, `"<n>px"`,
  hardcoded `Color(0x…)`) and migrate them to tokens as you stand the system up —
  otherwise the new theme and the old literals coexist and the system is fiction.
- **Leave the door open for extension, not duplication.** Document (in the token
  files) that new values are added as tokens here, never inlined — so the system
  grows by extension. The framework styling skills carry the "extend, don't
  inline" rule for day-to-day work; this skill is what makes that rule actionable.

## Definition of done

A reviewer can open any component and see only token references; can find every
design value in the token layer; can trace each token to its source; and can flip
light/dark without touching a component. If any of those fail, the system isn't
done — it's a partial theme components are still working around.
