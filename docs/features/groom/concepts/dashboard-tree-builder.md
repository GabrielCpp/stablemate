---
type: concept
slug: dashboard-tree-builder
title: Dashboard tree builder
---
# Dashboard tree builder

Dashboard tree builder is the browser-side function that turns a flat list of
path-carrying entries into the nested [dashboard path tree](../dashboard-path-tree.md)
the Files and Diff panes render. Both panes go through it: the Files pane feeds it
[workspace file list data](../workspace-file-list-data.md) paths, and the Diff pane
feeds it one entry per file in the [dashboard parsed diff file cache](../dashboard-parsed-diff-file-cache.md).
Its output is walked by the shared tree renderer, which emits a
[files directory toggle](../gui/screens/groom-dashboard.md#files-directory-toggle)
or [diff directory toggle](../gui/screens/groom-dashboard.md#diff-directory-toggle)
per directory node and a [files file row](../gui/screens/groom-dashboard.md#files-file-row)
or [diff file row](../gui/screens/groom-dashboard.md#diff-file-row) per leaf.

There is one function here where the htmx-era dashboard had two — a path builder
for the Files pane and a separate file builder for the Diff pane, each with its own
copy of the split-and-nest loop and its own idea of what a leaf carries. They
differed only in what the leaf had to remember, so the builder now stores the
caller's whole entry object on the leaf and stops caring: the Diff pane's entry
carries a parsed-array index and line counts, the Files pane's carries nothing but
the path, and neither shape is named here.

Nesting is computed in the browser rather than sent by the server. The server's two
producers are a `git ls-files` reader and a unified-diff parser, and neither of them
should have to agree on a node shape for the other's sake; a tree is also a display
decision, since which directories start open and how siblings sort are questions the
renderer answers. Flat paths are the narrow contract between them.

- code: groom/groom/assets/dashboard.js::buildTree
- verify: groom/tests/test_tree_builder.py::test_flat_paths_become_directory_nodes_and_file_leaves
- verify: groom/tests/test_tree_builder.py::test_paths_sharing_a_prefix_reuse_one_directory_node
- verify: groom/tests/test_tree_builder.py::test_the_whole_entry_rides_along_on_the_leaf

## Contract

- purpose: group a flat entry list into directory nodes and file leaves for the shared tree renderer.
- input: an array of objects each carrying a `path` member. The Files pane maps its plain path strings into that shape; the Diff pane maps each parsed file into that shape plus `idx`, `add`, and `del`. No other member is read.
- output: one fresh [dashboard path tree](../dashboard-path-tree.md) root node with `dirs` and `files`. A new root and new child nodes are created per call; the caller's entry objects are neither copied nor mutated.
- path source: the builder reads `entry.path` only. Choosing that path — `newName` unless it is missing or `/dev/null`, otherwise `oldName` — is the Diff pane's decision, made before the entry reaches here.
- path coercion: the value is converted with JavaScript `String(...)` before splitting, so a missing or null path becomes the literal string `undefined` or `null` and is grouped and displayed as such. A deleted file whose entry has no usable name stays visible and labelled rather than throwing partway through the list and losing every entry after it.
- path interpretation: `/` separates segments; every segment before the last is a directory name under the current parent, and the last is the leaf's displayed name.
- directory merging: repeated segments under the same parent reuse the same node object, so entries sharing a prefix appear under one branch.
- leaf shape: each entry produces exactly one leaf holding `name` — the final segment — and `entry`, the caller's object by reference.
- duplicate handling: identical paths append independent leaves to the same node. Nothing is deduplicated, overwritten, or merged; a rename legitimately puts the same name on the wire twice.
- ordering: insertion order is preserved inside each node's `files` array and in directory-key insertion order. Sorting is the renderer's, applied per level to a copy at render time.
- escaping: none, and none is needed. Every name and path this function returns is written to the document as a Preact text child, never as a markup string.
- validation: repeated slashes, dot segments, traversal-looking names, empty segments, and duplicate paths are all accepted as ordinary strings. The builder is not a path sanitizer; the server-side readers guard the filesystem.
- failure boundary: `entries` must be array-like enough to provide `forEach`. Invalid caller input raises an ordinary JavaScript error rather than being reported through any domain-specific channel.

## Methods

### method-build-tree

- sig: `buildTree(entries: Array<{path: any}>) -> PathTreeNode`
- returns: the root [dashboard path tree](../dashboard-path-tree.md) node.
- raises: ordinary JavaScript runtime errors when `entries` is not iterable with `forEach`.
- code: groom/groom/assets/dashboard.js::buildTree
- verify: groom/tests/test_tree_builder.py::test_an_empty_entry_list_yields_an_empty_root
- verify: groom/tests/test_tree_builder.py::test_insertion_order_is_preserved_and_nothing_is_deduplicated
- verify: groom/tests/test_tree_builder.py::test_a_non_string_path_is_coerced_rather_than_rejected

Creates an empty root, then for each entry coerces `entry.path` to a string, splits
it on `/`, walks or creates a directory node per leading segment, and appends one
`{name, entry}` leaf to the terminal node under the final segment.

Does not sort, deduplicate, normalize paths, escape text, read the DOM, touch the
client store, fetch anything, or retain state between calls.

## Algorithms

### algorithm-one-builder-two-panes

The Files and Diff panes hold different data and want the same picture. Files has
strings; Diff has parsed diff2html objects it must be able to address by index when
a row is clicked. The builder reconciles them by narrowing what it reads to one
member and widening what it carries to the whole object.

That is why the leaf is `{name, entry}` rather than a flattened record. A leaf with
named members — `path`, `idx`, `add`, `del` — would have to grow a member every time
one pane needed something the other did not, and every unused member would be
present-and-meaningless in the other pane's leaves. Carrying the caller's object by
reference means each pane's leaf renderer reads exactly the entry it built, and the
builder stays ignorant of both.
