---
type: screen
slug: widget-list
title: Widget directory
---
# Widget directory

The landing screen mobile-app opens on. It reads the whole widget directory from
[api-service](../../../api-service/http/api-service.md) over a plain `fetch` the screen makes
itself, straight from the device's own network — the same origin
[web-app](../../../web-app/gui/screens/widget-list.md) reads from a browser, so the two clients
make the same claims against one API. `mobile-app` never talks to `web-app`; both are
independent clients of `api-service`.

- route: /
- requires:
- params:
- entry: app launch (`WidgetList` is the navigator's `initialRouteName`), or returning from
  [new-widget](new-widget.md) after a successful submission
- detail:

## Components

### widget-table
- selector: testID=widget-table
- role: list
- one-per:
- variants:
- name: none
- unique-by:
- placement:
- keyboard: none
- extends:
- parent: [widget-list-screen](#widget-list-screen)
- exclusive-with: [empty-notice](#empty-notice), [widgets-alert](#widgets-alert)
- states: populated — visible, one row per widget, `name` and `quantity` in each row
- verify: visible(locator="#widget-table")
- fixture: widgets-on-hand — the directory holds at least one widget
- states: loading — not yet drawn while the fetch is pending
- fixture:
- code: `app/mobile-app/src/screens/WidgetListScreen.tsx::WidgetListScreen` @b9711279c5dc
- detail: which of the three the screen shows is recorded once, as `exclusive-with:`, and each
  of the three states what it looks like when it is the one shown — the same split
  [widget-list](../../../web-app/gui/screens/widget-list.md#widget-table) draws, since
  `loadWidgets` classifies the response into the same three-way `ListState` app.js's own
  `renderWidgetTable` switches on. `role:` is `list` and `name:` is `none` because the source
  sets no `accessibilityLabel` on the `FlatList` — the accessible name a screen reader would
  announce for this control simply does not exist in the current code, and stating `none` says
  that honestly rather than inventing one. Every component on this screen carries a `selector: testID=<value>` bullet: React Native
  addresses controls by `testID`, not `#id`, `tag.class` or `[role="..."]` web-DOM syntax, and
  this self-identifying `scheme=value` spelling names that grammar in the string itself rather
  than fabricating a CSS selector the render census would read as false. No driver in this tree
  compiles a `testID=` selector yet, so a `verify:` against one gaps rather than runs; `verify:`'s
  `locator=` still resolves against this book's own anchors regardless. `parent:` is
  [widget-list-screen](#widget-list-screen): the `FlatList` is a direct child of that root
  `View` in the populated branch of the same `WidgetListScreen` function it cites — a region
  of that one render, not an alternative to `new-widget-link` which sits beside it.
- tests:

### empty-notice
- selector: testID=empty-notice
- role: status
- one-per:
- variants:
- name: none
- unique-by:
- placement:
- keyboard: none
- extends:
- parent:
- exclusive-with: [widget-table](#widget-table), [widgets-alert](#widgets-alert)
- states: shown — visible whenever the directory read succeeds and returns no widgets
- verify: visible(locator="#empty-notice", text="No widgets are on file yet.")
- fixture: empty-directory — the directory holds no widgets
- code: `app/mobile-app/src/screens/WidgetListScreen.tsx::renderEmptyNotice` @b9711279c5dc
- detail: `status` is set explicitly on the `Text` node in source (`role="status"`); `name:` is
  `none` because `status` is not a name-from-content role and no `accessibilityLabel` is set —
  the wording is asserted instead through `verify:`'s `text=`, the same split
  [web-app](../../../web-app/gui/screens/widget-list.md#empty-notice) makes for its own
  `p.empty-notice`.
- tests:

### widgets-alert
- selector: testID=widgets-alert
- role: alert
- one-per:
- variants:
- name: none
- unique-by:
- placement:
- keyboard: none
- extends:
- parent:
- exclusive-with: [widget-table](#widget-table), [empty-notice](#empty-notice)
- states: shown — visible whenever the directory read itself fails, carrying the reason rather
  than an empty table that would read as a directory with nothing in it
- verify: visible(locator="#widgets-alert", text="Could not read the widget directory.")
- fixture: api-service-unavailable — the directory read fails
- code: `app/mobile-app/src/screens/WidgetListScreen.tsx::renderErrorAlert` @b9711279c5dc
- detail: `role="alert"` is set explicitly in source, mirroring
  [web-app](../../../web-app/gui/screens/widget-list.md#load-alert)'s `p[role="alert"]`; `name:`
  is `none` for the same reason as `empty-notice` above.
- tests:

### new-widget-link
- selector: testID=new-widget-link
- role: button
- one-per:
- variants:
- name: Add a widget
- unique-by:
- placement:
- keyboard: none
- extends:
- parent: [widget-list-screen](#widget-list-screen)
- exclusive-with:
- states:
- verify: visible(locator="#new-widget-link")
- fixture:
- code: `app/mobile-app/src/screens/WidgetListScreen.tsx::WidgetListScreen` @b9711279c5dc
- detail: the source sets `role="button"` explicitly on this `Pressable`, so `button` is an
  observation of that prop rather than a computed-role inference — unlike
  [web-app](../../../web-app/gui/screens/widget-list.md#new-widget-link), whose counterpart is a
  real `<a>` element. `button` is a name-from-content role, so `name:` is the control's own
  text. `keyboard:` is `none`: mobile-app is a touch surface and nothing in the source or the
  Maestro flow drives this control any other way. `parent:` is
  [widget-list-screen](#widget-list-screen) for the same reason as `widget-table`: this
  `Pressable` is a sibling child of that root `View` in the same `WidgetListScreen` render, not
  a rival implementation of it.
- tests:

### widget-list-screen
- selector: testID=widget-list-screen
- role: none
- one-per:
- variants:
- name: none
- unique-by:
- placement:
- keyboard:
- extends:
- parent:
- exclusive-with:
- states:
- verify: visible(locator="#widget-list-screen")
- fixture:
- code: `app/mobile-app/src/screens/WidgetListScreen.tsx::WidgetListScreen` @b9711279c5dc
- detail: the root view the table and the link sit in, the same job
  [new-widget](new-widget.md#new-widget-screen)'s `new-widget-screen` does for its own
  screen. `role:` is `none` because it is a plain structural container with no interactive
  semantics of its own. `widget-table` and `new-widget-link` cite the same `WidgetListScreen`
  symbol this component does because the source never pulls either out into its own function
  the way it does for `renderEmptyNotice`/`renderErrorAlert` — both are regions of this one
  render, declared as its `parent:` children rather than as rival implementations of it.
- tests:

## Interactions

### open-new-widget
- on: [new-widget-link](#new-widget-link)
- trigger: tap
- role: button
- one-per:
- variants:
- name: Add a widget
- unique-by:
- keyboard: none
- when:
- exclusive-with:
- extends:
- does:
  - navigation: navigates to [new-widget](new-widget.md)
- verify: visible(locator="new-widget.md#new-widget-screen")
- fixture:
- arrange:
- capture:
- code: `app/mobile-app/src/screens/WidgetListScreen.tsx::WidgetListScreen` @b9711279c5dc
- detail:
- tests:
