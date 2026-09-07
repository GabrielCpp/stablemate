---
type: concept
slug: command-palette-opening
title: Command palette opening
---
# Command palette opening

The command-palette opener and dialog are complementary surfaces of the same
operation, not alternative implementations. Use the opener to make the command
palette available from the status bar and to preserve the invoking control; use
the dialog to describe the modal surface that becomes visible and receives focus.

`openPalette` records its explicit invoker, or the current active element when
the keyboard shortcut invokes it, then opens the dialog, resets its query state,
and focuses its input. Neither surface supersedes the other: both are current
parts of opening the palette.

- code: `groom/groom/assets/dashboard.js::openPalette`
- rule: use the open button for the invocation control and the dialog for the modal surface opened and focused by the same operation
