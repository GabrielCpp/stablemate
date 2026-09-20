---
type: story
id: WDGT-01M2ZA8VB7JS6Q8MECCXHPAG7Z
slug: mobile-widget-directory
status: Not started
---
# Story: Read and add to the directory from the device

## Dependencies

- Blocked by: add-widget

## Fixtures

(none)

## Context

mobile-app is a second, independent client of the same api-service — it never talks to
web-app, and it makes the same claims against the same directory from a device instead of a
browser. [The mobile widget-list screen](../../../../features/mobile-app/gui/screens/widget-list.md)
and [the mobile new-widget screen](../../../../features/mobile-app/gui/screens/new-widget.md)
are that client's two screens, and [browse-and-add-widget](../../../../features/mobile-app/flows/browse-and-add-widget.md)
is the one journey that crosses between them — the same "user crossing" shape web-app's own
flow walks, driven from a device instead.

The three-state read (populated, empty, error) and the per-field refusal on write are not
new rules here: they are the same rules `widget-list` and `add-widget` already state, proven
a second time against a different render surface. What is new to this story is only that the
surface is React Native, not the DOM — components addressed by `testID` rather than `#id`,
and accessibility names read from explicit props rather than inferred from visible text.

## Acceptance Criteria

- The mobile widget-list screen renders one row per widget on a successful read, an
  empty-directory notice when the store holds none, and an alert when the read fails.
- The mobile new-widget screen accepts `name` and `quantity`, and on refusal renders each
  field's error inline, distinguishable by its own `"<Field>: <message>"` label.
- A successful submission on the mobile new-widget screen navigates back to the mobile
  widget-list screen, which shows the created widget.
- The mobile app never calls web-app, only api-service, and either app running alone still
  serves a correct directory to its own client.

## Non-Functional Acceptance Criteria

(none)

## Technical Notes

- `app/mobile-app/src/screens/WidgetListScreen.tsx::loadWidgets` is the device's own fetch
  against api-service, classifying the response into the same `ListState` shape
  `app.js::loadWidgets` switches on for the browser.
- `app/mobile-app/src/screens/WidgetListScreen.tsx::renderEmptyNotice` and
  `app/mobile-app/src/screens/WidgetListScreen.tsx::renderErrorAlert` are the empty and error
  branches; `app/mobile-app/src/screens/WidgetListScreen.tsx::WidgetListScreen` is the
  populated branch and the screen's root component.
- `app/mobile-app/src/screens/NewWidgetScreen.tsx::submitNewWidget` is the device's own POST
  to `api/widgets`, and `app/mobile-app/src/screens/NewWidgetScreen.tsx::renderFieldError` is
  the shared helper both field alerts call, each with its own `fieldLabel`.
- Both screens land on `app/api-service/service.go::Server.handleList` and
  `app/api-service/service.go::Server.handleCreate` — the same store and the same handlers
  `widget-list` and `add-widget` already cite; nothing about the server changes for this
  client.

## Implementation Status

- **Status**: Not started
