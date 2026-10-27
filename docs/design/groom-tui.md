# groom in the terminal

## 1. Problem

The operator answers gates and watches runs from groom's browser dashboard. The dashboard
needs a browser open all day for one tab, and the browser costs far more memory than the
tab. The operator already lives in a terminal beside their runs, where `groom wait` and
`workhorse control` run.

**Done**, as the operator sees it: they run `groom tui` in a terminal pane. They see every
run with its liveness and its current node. When a run blocks, the terminal rings and a toast
names the run. They open the run, read the gate question as formatted Markdown, type an
answer and send it. The run wakes. They can read the run's trail and transcript, its
working-tree diff and its files, and drive the attendant and the dispatch queues, without a
browser. Idle with a full fleet, the process stays under 80 MB resident.

## 2. Decisions

- **The TUI is a second client of the unchanged server.** It speaks the protocol a browser
  tab speaks: `WS /ws` for `state`, `run`, `detail`, `notify` and `answered` frames down and
  `watch` and `answer` commands up, and the same HTTP reads for per-selection panels. The
  server gains no route and no frame type. If a slice finds it needs one, that is a design
  gap to bring back, not a quiet addition.
- **The browser dashboard stays.** Retiring it is a separate decision, taken after the TUI
  has carried real use. See section 7.
- **Textual is the framework.** It gives widgets, a stylesheet, mouse support, a Markdown
  widget on markdown-it-py (already a groom dependency), a built-in command palette, toasts
  and a headless test pilot. It is pure Python, which keeps groom's Python-only constraint.
- **Textual is a core dependency of groom, not an extra.** `groom tui` then works from any
  install, with no import that fails at runtime. The cost is a few MB of pure Python in the
  container image that also carries `groom-sidecar`. An optional extra would save that and
  buy a command that exists but cannot start.
- **One sanitizer guards the terminal.** Rich passes escape sequences through: a gate
  question holding `ESC ] 52` writes the operator's clipboard, and `ESC [ 2J` clears the
  screen. Every agent-authored string (gate questions, trail lines, transcripts, diffs, file
  contents, attendant records) passes one function that strips C0 and C1 control characters
  except newline and tab, before it reaches any widget. It is the terminal's DOMPurify, and
  its test is the twin of `tests/test_dashboard_client.py`.
- **Connection state comes from message recency,** as in the browser: `live`, `stale`,
  `reconnecting`, `offline`, with `GET /api/state` resync whenever the phase is not `live`.
  The Python state machine uses the same thresholds as `dashboard.js`, and a test reads both
  so they cannot drift apart.
- **Paging stays where it is.** The TUI rings the terminal bell and raises a toast on a
  `notify` frame. Away-from-keyboard paging remains ntfy and the webhook, which work with no
  client open.

## 3. Screen

One screen, two columns, a status line and a footer of key bindings.

| Region      | Holds                                                                                    |
| ----------- | ---------------------------------------------------------------------------------------- |
| status line | connection phase as a word with its dot, fleet counts, discovery state                    |
| left        | the run list: liveness word, name, activity, `silent 4m` / `in node 12m`, a gate marker   |
| right       | the selected run, as tabs: Gate, Trail, Diff, Files                                       |
| footer      | the bindings that apply to the focused region                                            |

The browser's global Files and Diff modes become tabs of the selected run, with the
repository picker kept inside each tab and defaulting to the run's own container. Opening a
run is how the operator reaches its files today anyway. The attendant, dispatch and settings
panes become their own screens, reached by key.

| Key             | Action                                       |
| --------------- | -------------------------------------------- |
| `j` / `k`       | move through the run list                    |
| `enter`         | open the run                                 |
| `a`             | focus the answer box on the Gate tab         |
| `ctrl+s`        | send the answer                              |
| `g` `t` `d` `f` | Gate, Trail, Diff, Files tab                 |
| `/`             | filter the run list                          |
| `ctrl+p`        | command palette over the fleet               |
| `A` `D` `S`     | attendant, dispatch, settings screens        |
| `r`             | rescan containers (`POST /refresh`)          |
| `q`             | quit                                         |

## 4. Code

A package under groom, a sibling of `assets/`, listed in groom's map.

| Module          | Owns                                                                                    |
| --------------- | --------------------------------------------------------------------------------------- |
| `tui/link.py`   | the port: an async stream of frames, `send(command)`, and `get(path)` for HTTP reads     |
| `tui/link_ws.py`| the adapter over `websockets` and HTTP, honouring `GROOM_URL` as `groom status` does     |
| `tui/connection.py` | the pure four-phase state machine and the backoff delay                             |
| `tui/store.py`  | client state: runs, selection, detail, per-pane loading; `apply_state`, `apply_run`, `apply_detail` as pure functions |
| `tui/clean.py`  | the sanitizer                                                                           |
| `tui/app.py`    | the Textual app, its screens and bindings                                               |
| `tui/widgets/`  | one module per region: fleet, gate, trail, diff, files, attendant, dispatch, settings    |

`cli.py` gains `groom tui [--url]`. The store's appliers mirror `applyState` and `applyRun` in
`dashboard.js`, so a frame means the same thing to both clients.

Diffs render as coloured unified diffs through Rich's diff lexer. Files render through Rich
`Syntax`. Neither has the browser's side-by-side view, by choice.

## 5. Tests

- **The store and the state machine** are pure and tested with frames built by
  `projection.state_message`, `run_message` and `detail_message` from real models, never
  hand-written JSON. A projection change then breaks the TUI's tests too.
- **The app** runs under Textual's `run_test` pilot against a fake link fed those same
  frames: select a run, read the gate, type, send, assert the `answer` command went up.
- **One composed test** boots a real groom, as `test_a11y_dynamic.py` does, connects the
  real adapter and answers a gate end to end.
- **The sanitizer** is tested with the payloads that pass Rich today: an OSC 52 clipboard
  write, a screen clear, a C1 CSI. Each must arrive at the widget without its control bytes.
- **Memory** is measured, not asserted in the suite: RSS of an idle `groom tui` against a
  fleet of 20 runs, recorded in the slice that claims the bar.

## 6. Slices

Each slice ships a TUI an operator can use for something.

1. **Answer a gate.** `groom tui` connects, shows the fleet with liveness, the connection
   phase and its resync, rings and toasts on a block, opens a run's gate as Markdown, and
   sends an answer. The sanitizer and its test land here, because the gate question is
   agent-authored. The memory measurement lands here.
2. **Read a run.** The Trail tab: the watch subscription, `detail` frames, the run head,
   metrics, and the trail with its everything / transcript / telemetry filter.
3. **See what it changed.** The Diff and Files tabs with the repository picker.
4. **Find a run.** The list filter and the command palette over the fleet.
5. **Attendant and settings.** The attendant screen, its sessions and stop, and the attend
   setting.
6. **Dispatch.** The queues, their items, enqueue, cancel and stop.

Each slice adds its part of the book under `docs/features/groom/` in the same change.

## 7. Open

- **Retiring the browser dashboard.** Two clients mean every new pane is built twice. The
  recommendation is to decide after slice 6 has carried a week of real use. Retiring it
  deletes `assets/`, the shell template, the Playwright accessibility suite and the screen
  page of the book.
- **How the book verifies a terminal screen.** ostler's QA drives web screens through a
  browser. A TUI screen has no locator it can drive. Slice 1 has to settle whether the TUI
  is a `cli` node with invocations, or a `screen` with a terminal driver ostler does not
  have yet.
- **Screen readers.** Terminal UIs are weak under a screen reader, where the browser shell
  meets the accessibility contract. Keyboard operation is complete by design. While the
  browser stays, it remains the accessible client.
- **The browser book is stale.** The screen page still lists a telemetry mode the dashboard
  no longer has, and omits the attendant and dispatch modes. That is a fix of its own,
  independent of the TUI.

