---
type: concept
slug: command-palette-result-presentation
title: Command palette result presentation
---
# Command palette result presentation

The command palette exposes three distinct surfaces around one result set. Use the input
component for the focused combobox and its keyboard-owned active-result pointer, the listbox
component for the container that presents all matching workers, and the result component for
each selectable worker option. They are complementary parts of the same presentation rather
than alternative implementations.

`PaletteResults` derives matching runs, keeps the input's `aria-activedescendant` synchronized
with the active option, and renders each result option. The static dashboard shell supplies the
input and listbox elements that this function connects to those options.

- code: groom/groom/assets/dashboard.js::PaletteResults
- rule: document the command-palette surface by its responsibility: focused combobox input, results container, or individual result option
