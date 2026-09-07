---
type: concept
slug: repository-picker-item-projection
title: Repository picker item projection
---
# Repository picker item projection

`repoItems` is the picker-only projection of repository menu data. It walks the
server's grouped container/checkouts, filters entries whose labels do not contain
the case-insensitive search query, and returns flat rows carrying the container,
checkout directory, label, state, type, and type hue. `RepoMenu` renders those
rows and selection stores the chosen row's container, directory, and label for
the files and diff panes.

The projection and the selected repository state are not alternative
implementations. Use repository menu data to describe the `GET /repos` response;
use dashboard selected repository state to describe the browser-local choice made
from a projected row. Neither supersedes the other: both are required while the
picker is open or a repository-scoped pane is active.

- code: groom/groom/assets/dashboard.js::repoItems
- rule: use repository menu data for the grouped server response and dashboard selected repository state for the selected browser-local row; no ranking exists because `repoItems` connects the two representations rather than replacing either one
