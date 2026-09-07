---
type: concept
slug: files-and-diff-mode-selection
title: Files and Diff mode selection
---
# Files and Diff mode selection

Files and Diff are parallel dashboard modes, not alternative implementations of one
journey. The activity-bar mode switch records the selected mode, closes the shared
repository picker, then invokes the loader for that mode. Files loads a workspace
file list and opens selected file content; Diff loads a working-tree diff and opens
selected changed files from its parsed cache.

Choose Files when the operator needs to browse or read a workspace file. Choose Diff
when the operator needs to inspect working-tree changes. Both paths are current: the
mode switch has no legacy branch, deprecation marker, or preference between them.

- code: groom/groom/assets/dashboard.js::setMode
- rule: use Files to browse workspace files and Diff to inspect working-tree changes; neither mode supersedes the other
