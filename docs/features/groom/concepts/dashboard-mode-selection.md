---
type: concept
slug: dashboard-mode-selection
title: Dashboard mode selection
---
# Dashboard mode selection

The dashboard's activity controls select one of five parallel views rather than competing
implementations of one operation. Runs shows the fleet, Files browses workspace files, Diff
inspects working-tree changes, Telemetry queries run spans, and Settings exposes dashboard
controls. Selecting Files, Diff, or Telemetry invokes only that mode's loader; selecting Runs or
Settings has no loader branch. Every selection closes the repository menu and updates the shared
active-mode presentation.

The `j`/`k` run-row navigation and command-palette result selection first choose Runs because the
run they select must be visible in that pane. That forced choice is contextual, not a preference
over the other modes: an operator chooses the activity mode that matches the information or
control they need.

- code: groom/groom/assets/dashboard.js::setMode
- rule: use Runs for fleet and selected-run activity, Files for workspace-file browsing, Diff for working-tree changes, Telemetry for run spans, and Settings for dashboard controls; keyboard or palette run selection switches to Runs only to reveal the selected row, and no mode supersedes another
