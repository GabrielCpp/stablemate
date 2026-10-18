# widgets

The regions of the terminal client's screen, one module per region. Every server string passes `clean()` before it reaches a widget.

## Map

- `detail.py`: the open run's pane: the run head, the Gate and Trail tabs, and which tab is shown.
- `fleet.py`: the status line and the run list's row text.
- `gate.py`: a run's gates: the question as Markdown, the answer box and the send button.
- `lines.py`: the trail's line widgets: a telemetry line, a collapsible turn and its transcript entries.
- `reconcile.py`: the keyed diff that mounts, updates, moves and removes a container's children without a remount.
- `trail.py`: the run head text, the metrics, the view and kind bar, and the trail's reconcile.
