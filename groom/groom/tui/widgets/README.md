# widgets

The regions of the terminal client's screen, one module per region. Every server string passes `clean()` before it reaches a widget.

## Map

- `code.py`: the scrolling code viewer that renders only the visible lines, and the background highlighter that feeds it.
- `detail.py`: the open run's pane: the run head, the Gate, Trail, Diff and Files tabs, and which tab is shown.
- `diff.py`: the Diff tab: the changed files with their counts and the highlighted file's diff in a code viewer.
- `files.py`: the Files tab: the file tree and the code viewer for the selected file.
- `fleet.py`: the status line, with the filter count, and the run list's row text.
- `gate.py`: a run's gates: the question as Markdown, the answer box and the send button.
- `lines.py`: the trail's line widgets: a telemetry line, a collapsible turn and its transcript entries.
- `options.py`: the keyed sync of an option list, which keeps the highlight by key when rows change and appends rows that extend the list without rebuilding it.
- `palette.py`: the command palette's provider: every run, found by the list filter's haystack, and the tab and rescan commands.
- `reconcile.py`: the keyed diff that mounts, updates, moves and removes a container's children without a remount.
- `repo.py`: the repository picker and the base of the two tabs that share the chosen repository.
- `runfilter.py`: the input above the run list that filters it as the operator types.
- `trail.py`: the run head text, the metrics, the view and kind bar, and the trail's reconcile.
