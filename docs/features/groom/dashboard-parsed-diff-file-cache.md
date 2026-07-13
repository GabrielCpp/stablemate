---
type: format
slug: dashboard-parsed-diff-file-cache
title: Dashboard parsed diff file cache
---
# Dashboard parsed diff file cache

Dashboard parsed diff file cache is the browser-local parsed changed-file array created by [select activity diff mode](gui/screens/groom-dashboard.md#select-activity-diff-mode) and [select repository menu option](gui/screens/groom-dashboard.md#select-repository-menu-option) when the Diff pane loads non-empty [workspace diff data](workspace-diff-data.md). It feeds the [dashboard diff file tree builder](concepts/dashboard-diff-file-tree-builder.md), [diff file row](gui/screens/groom-dashboard.md#diff-file-row), and [select diff file row](gui/screens/groom-dashboard.md#select-diff-file-row) so the dashboard can render a changed-file tree first and later render one selected file's diff without another HTTP request.

- file: not an on-disk artifact; this is a transient browser property on the `#diff-tree` element.
- code: groom/groom/templates/dashboard.html::loadDiff

## Contract

- producer: the Diff pane loader creates this cache only after `GET /diff/{container_id}?repo={repo}` returns non-whitespace text and the third-party Diff2Html parser returns at least one parsed file entry.
- parser input: the producer parses the raw [workspace diff data](workspace-diff-data.md) response body exactly as returned by the endpoint; it does not pre-split, filter, normalize paths, redact content, or check the HTTP status before parsing fulfilled responses.
- storage: the producer assigns the parsed array directly to the `#diff-tree` DOM element as property `_files`; the cache is not serialized into markup, browser storage, URL state, server state, or websocket state.
- consumer: the [dashboard diff file tree builder](concepts/dashboard-diff-file-tree-builder.md) reads the parsed entries to create [dashboard diff file tree](dashboard-diff-file-tree.md) directory nodes and changed-file leaves; the diff-file-row interaction later reads one cached entry by array index and passes that full entry to Diff2Html's HTML renderer.
- scope: one loaded dashboard page and one currently rendered `#diff-tree`; reloading the Diff pane for the same or another selected repository replaces the cache when parsing succeeds.
- absent states: no cache is created for no selected repository, whitespace-only diff text, parser output with zero file entries, fetch rejection, or response-body read rejection.
- stale-property rule: an empty, zero-entry, or failed reload replaces the visible diff tree with a prompt but does not explicitly delete a prior `_files` property; with no generated `.tree-file[data-file-idx]` rows remaining, ordinary row activation has no usable index into that stale array.
- ordering: array indexes are assigned by the Diff2Html parser order and preserved in generated `data-file-idx` row attributes even though sibling rows are visually sorted by directory and basename.
- selection invariant: every selectable diff-file row must carry a `data-file-idx` value that points to the same parsed array instance currently stored on `#diff-tree._files`; selecting a row renders only that one cached parsed file entry and never performs another diff fetch.
- third-party boundary: the dashboard treats each parsed file entry as an opaque Diff2Html payload for final HTML rendering, while directly consuming only path and line-count members for the tree labels.

## Fields

### field-cache-property

- type: `Array<Diff2HtmlParsedFile>` stored as `#diff-tree._files`
- default: absent
- required: true after a successful non-empty Diff pane load; initially absent, and not assigned by no-selected-repository, empty-diff, zero-entry, or failed loads.
- meaning: ordered parsed-file array for the currently loaded repository diff; generated diff-file rows point back into this array by zero-based index.
- write rule: assigned exactly once per successful Diff pane load, before the diff tree HTML is generated for that same parsed array.
- mutation rule: first-party dashboard code does not mutate the parsed array or its entries after storing it; later rendering reads entries by index.

### field-entry-count

- type: `int`
- default: `0` when parsing yields no entries; otherwise parser supplied through `Array.length`.
- required: true for producer branching.
- meaning: number of parsed changed-file entries returned from Diff2Html parsing; the cache is assigned only when this value is greater than zero.

### field-file-index

- type: `int`
- default: none
- required: true for every generated diff-file row backed by this cache.
- meaning: zero-based position of one parsed file entry in `#diff-tree._files`; serialized onto the generated row as `data-file-idx` and converted back to a number when a changed file is selected.
- source: original array position before directory and filename sorting are applied to the rendered tree.
- failure behavior: no bounds check is performed by the row-selection interaction; correctness depends on generated rows preserving indexes from the same cached array.

### field-entry

- type: `Diff2HtmlParsedFile`
- default: parser supplied
- required: true for every item in `#diff-tree._files`.
- meaning: one parser-produced changed-file payload representing a single file-level diff; first-party code reads the fields documented below for tree construction and retains the full object for selected-file rendering.

### field-new-name

- type: `str | null`
- default: parser supplied
- required: false
- meaning: changed file path after the diff when the parsed entry has a new path; the dashboard uses it as the display/grouping path unless it is `/dev/null`.
- fallback rule: a falsey value or the literal `/dev/null` makes the dashboard use `oldName` as the grouping/display path.

### field-old-name

- type: `str | null`
- default: parser supplied
- required: false
- meaning: changed file path before the diff; the dashboard uses it as the display/grouping path when `newName` is missing or equals `/dev/null`.
- fallback rule: when this field is used, it is string-coerced before slash splitting; the builder does not reject missing, empty, duplicate, or traversal-looking values.

### field-added-lines

- type: `int`
- default: parser supplied
- required: true for rendered diff-file rows.
- meaning: added-line count displayed in the generated row as `+{addedLines}`.
- consumer field: copied into the [dashboard diff file tree](dashboard-diff-file-tree.md) file leaf as `add` before rendering.

### field-deleted-lines

- type: `int`
- default: parser supplied
- required: true for rendered diff-file rows.
- meaning: deleted-line count displayed in the generated row as `-{deletedLines}`.
- consumer field: copied into the [dashboard diff file tree](dashboard-diff-file-tree.md) file leaf as `del` before rendering.

### field-render-payload

- type: `Diff2HtmlParsedFile`
- default: parser supplied
- required: true for selecting a diff-file row.
- meaning: the complete parsed file object retained from the parser result; it is passed as the single element of an array to the Diff2Html HTML renderer for the selected-file diff view.
- render options: selected-file rendering uses `drawFileList: false`, `matching: "lines"`, `outputFormat: "line-by-line"`, and `colorScheme: "dark"`.
