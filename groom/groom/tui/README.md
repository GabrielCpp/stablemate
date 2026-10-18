# tui

The terminal client behind `groom tui`. It is a second client of the unchanged groom server: it reads the same `/ws` frames the browser reads and sends the same `watch` and `answer` commands.

## Map

- `app.py`: the Textual app: its key bindings, the connection loop and the handling of each frame.
- `clean.py`: the sanitizer every server-authored string passes before it reaches a widget.
- `connection.py`: the four-phase connection machine and the reconnect backoff, with the thresholds `dashboard.js` uses.
- `link.py`: the port the app talks through: a stream of frames, `send`, and HTTP `get` and `post`.
- `link_ws.py`: the adapter over `websockets` and HTTP.
- `store.py`: the client's state as plain data, the pure functions that apply each frame to it and the trail's view and kind filter.
- `widgets/`: the regions of the screen: the run list, the open run's head, gates and trail. Its own README has the map.
