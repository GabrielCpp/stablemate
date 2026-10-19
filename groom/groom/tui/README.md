# tui

The terminal client behind `groom tui`. It is a second client of the unchanged groom server: it reads the same `/ws` frames the browser reads and sends the same `watch` and `answer` commands.

## Map

- `app.py`: the Textual app: its key bindings, the connection loop and the handling of each frame.
- `attend.py`: the pure text of the attendant screen: the row, the detail header, the elapsed time and the attendant line on a run.
- `base.py`: the app's answer handling and the main screen accessor, which the app inherits.
- `clean.py`: the sanitizer every server-authored string passes before it reaches a widget.
- `changes.py`: the pure logic of the Diff and Files tabs: the repository items, the unified-diff splitter, the file tree and the line cap.
- `connection.py`: the four-phase connection machine and the reconnect backoff, with the thresholds `dashboard.js` uses.
- `dispatch.py`: the pure text of the dispatch screen: the queue and item rows, the item detail, the enqueue form's fields and the required-field check.
- `link.py`: the port the app talks through: a stream of frames, `send`, and HTTP `get`, `get_list`, `post` and `delete`. `post` takes an optional JSON body, and a refusal carries the server's error text.
- `link_ws.py`: the adapter over `websockets` and HTTP.
- `route.py`: the URL helper that quotes a container, a repository and a path.
- `screens/`: the screens above the run list: the attendant screen with its stop confirmation, the dispatch screen with its enqueue form and yes-or-no confirmation, and the settings screen.
- `store.py`: the client's state as plain data, the pure functions that apply each frame to it and the trail's view and kind filter, the chosen repository, and the run list's filter query with the haystack it searches.
- `styles.py`: the app's stylesheet.
- `widgets/`: the regions of the screen: the run list, the open run's head, gates, trail, diff and files. Its own README has the map.
