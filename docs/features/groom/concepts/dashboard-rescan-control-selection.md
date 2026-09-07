---
type: concept
slug: dashboard-rescan-control-selection
title: Dashboard rescan control selection
---
# Dashboard rescan control selection

The Settings and status-bar controls are two current entry points to the same container rescan.
Use [the Settings control](../gui/screens/groom-dashboard.md#settings-rescan-button) while
working in Settings, where it accompanies the discovery explanation; use [the status-bar
control](../gui/screens/groom-dashboard.md#statusbar-refresh-button) from the fleet view for a
quick rescan. Neither control supersedes the other.

Both ids are delegated to `doRefresh`, which posts the rescan request and marks only the clicked
control busy until that request settles. The distinct accessible names let both controls remain
distinguishable if Settings is open while the status bar is visible.

- code: groom/groom/assets/dashboard.js::doRefresh
- rule: use the Settings control for the settings-pane discovery context and the status-bar control for a quick fleet-view rescan; neither is preferred globally.
