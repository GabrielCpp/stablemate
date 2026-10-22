---
type: concept
slug: repository-menu-composition
title: Repository menu composition
---
# Repository menu composition

The repository menu is one composite picker, rendered by `RepoMenu` into the static
shell around the search input. Its search input is the combobox that owns focus and
publishes the active option; its listbox is the region that receives the rendered
rows; each option is one filtered container/checkout entry that can be selected.

These are not alternative implementations. `RepoMenu` renders the listbox and every
option while the static shell supplies the search input, and the input's
`aria-activedescendant` points to the active rendered option. There is no preferred
or deprecated member: use the component that describes the reader's concern rather
than substituting one for another.

- code: groom/groom/assets/dashboard.js::RepoMenu
- rule: use the search input for filtering and keyboard focus, the listbox for the option region, and an option for one selectable container/checkout entry; no ranking exists because all three are required parts of the same picker.
