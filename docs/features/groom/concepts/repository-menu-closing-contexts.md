---
type: concept
slug: repository-menu-closing-contexts
title: Repository menu closing contexts
---
# Repository menu closing contexts

`closeRepoMenu` is the shared dismissal operation for an open repository menu:
it removes the open state, marks the search input collapsed, clears its active
option reference, and restores focus to the invoking picker only when focus is
still inside the menu.

The three callers serve distinct current contexts rather than competing
implementations. Switching to Runs dismisses any open menu before showing that
pane. Activating the Files picker when its menu is already open uses the same
operation to complete the picker toggle without fetching repositories.
Selecting a menu option records the chosen repository and dispatches the active
pane before dismissing the menu. No context is preferred or deprecated: use the
caller matching the event that is occurring.

- code: groom/groom/assets/dashboard.js::closeRepoMenu
- rule: dismiss an open repository menu when switching to Runs, toggling an already-open Files picker, or completing a repository selection; no ranking exists because each caller handles a distinct event
