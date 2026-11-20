# Flow tab: where a run is in its machine

Disclosure: a first build of this feature drew the whole registry with Graphviz on groom's
host and inserted the resulting SVG into the page. The operator rejected it. The picture
must be drawn in the browser, and only the flow the run is in is shown. That build's
telemetry findings are kept below as claims.

## 1. Problem

An operator watching a run in groom sees the node it is in and for how long. They cannot see
which flow that node belongs to, where it sits in that flow, or where the run can go next.

Done looks like this. The operator opens a run's Flow tab and sees one flow: the one the run
is in now. The current state is outlined, the arrows it can take next are highlighted, and
the states it already went through are shaded. Above the chart, a trail names every flow the
run is nested in, such as `author › story-author › draft`. Each crumb opens that flow at the
state the run is in there. When the run moves or hands off to another flow, the view follows
within one heartbeat (about 10 seconds), with no reload. Groom needs nothing installed beyond
itself.

Out of scope: steering a run from the chart, a chart for a run that started before this
change, and drawing more than one flow at once.

## 1b. Claims

1. The run tags each state span with `workhorse.flow` and `workhorse.state`. The flow is the
   snake-case id of the handed-off class, and empty for the flow the run started in.
2. Spans export only when they end, so live position needs a gauge.
3. Groom identifies a gauge series by all of its attributes, so the existing node gauges
   must not gain a changing attribute.
4. Groom vendors every browser library and loads nothing at runtime from the network.
5. A flow holds at most about 15 states. The author's largest, epic-edit, has 10 states and
   21 arrows.

## 2. Parts and concepts

Level 1:

- **The machine**, owned by the run. It describes each flow it can enter as data: states,
  what each state runs, and where each state can go. It never knows where the run is, or how
  anything is drawn.
- **The position**, owned by the run. It reports the stack of open state visits, outermost
  first. It never knows the machine's shape.
- **Delivery**, from the run to the dashboard. It carries the machine once per process start
  through the run's telemetry, and keeps the latest one per run.
- **The drawing**, in the browser. It lays out one flow and draws it. It never knows where
  the run is.
- **The view**, in the browser. It picks the flow to show, marks the position, the next
  arrows and the visited states, and offers the trail.

Flow: at process start the run sends its machine. While it runs, every heartbeat carries the
open state visits. The Flow tab fetches the machine and the visited states once per run and
again when the position moves. It lays out the flow the position names, draws it, and marks
it.

| Part | Concept | Owns | Never knows |
|---|---|---|---|
| Machine | Flow description | one flow's states, steps and grouped arrows, as JSON | layout, position |
| Machine | Flow id | the name a run reports a flow by | the drawing |
| Position | Open visit | one state visit the run has open, with its depth | the machine |
| Delivery | Machine record | the latest machine a run sent | its contents |
| Drawing | Layout | rank and order of states and the route of each arrow, for one flow | position, other flows |
| Drawing | Picture | SVG elements drawn from a layout | how the layout was made |
| View | Trail | the open visits, outermost first, as flow and state | layout |
| View | Marks | which states and arrows to outline, highlight or shade | layout |

The flow id is a shared value type. The run's telemetry and the machine both produce it, and
the view reads it.

## 3. Invariants

1. Every flow id a run reports names a flow in the machine it sent. Owner: the machine
   description, which builds a flow id with the same function the engine uses for a
   handoff. A test renders a registry and checks it.
2. The layout is deterministic: the same flow always draws the same picture. Owner: the
   layout. A test lays out one flow twice.
3. A run with no machine, or a position whose flow is missing from it, shows one line saying
   so, never an error. Owner: the view.

## 4. Forces and patterns

- The operator sees one small flow at a time (claim 5). A simple layered layout is enough:
  ranks by longest path from the start over the forward arrows, order within a rank by the
  mean position of the predecessors, arrows that go back routed down the right side. No
  library and no binary is needed. Pattern: a plain function from a flow to a layout.
- The layout must stay apart from marking, so a position change marks without a new layout.
  Pattern: the view memoizes the layout per flow and machine.
- The machine changes when the run reloads new code. The run re-sends it at every process
  start, and groom keeps the latest.
- Labels come from workflow code and prompt titles. The browser builds the picture as
  elements with text nodes, never as an HTML string, so nothing needs sanitising.

Claims 1 to 4 are kept. Claim 5 is what makes the layered layout enough.

## 5. Mapping

- Machine: new `workhorse/pyflow/chart.py`, with `machine(graphs, root)` returning the JSON.
  The arrow grouping moves from `dot.py` into `StateNode.arrows()`, so DOT and the machine
  group the same way. The flow id function moves to `names.py` and `engine.py` uses it.
- Position: `workhorse/otel.py` gains a `workhorse.state.active` gauge. A state visit sets it
  to 1 with fixed `flow`, `state` and `depth` attributes, and sets it to 0 when the visit
  leaves the stack, including on unwind. The heartbeat repeats the open visits.
- Delivery: `pyflow/run.py` logs one `flow machine` record on logger `workhorse.chart` with a
  `workhorse.machine` attribute after telemetry starts. Groom stores log attributes in full,
  and the Activity raw view does not show them.
- Groom: `alerts.py` keeps the open visits per run. `projection.run_detail` gains `trail`,
  the open visits ordered by depth. `GET /api/run/{run_id}/flow` returns the machine and the
  visited states. Groom runs no subprocess for it.
- Browser: `assets/flowchart.js` holds the layout and the drawing as plain functions.
  `dashboard.js` gains the Flow tab, the trail and the marks.
- Books: groom's http book gains the route, and its web book gains the tab, its trail and
  its line.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| Operator answering a gate | a wait series closes on answer | groom alert tests | wait gauges carry node and labels | wait and node gauges unchanged |
| Docs diagram readers | `author.dot` matches the code | `test_dot_matches_registry` | current DOT | byte-identical DOT |
| Run start | telemetry starts without reading the code | nothing | 0 s | machine built under 1 s for author |
| Groom host | no extra binary needed | nothing | none | still none |

## 6. Slices

1. A running run's Flow tab draws the flow it is in, with the current state outlined and its
   next arrows highlighted. Done when a live demo run in a scratch groom shows it in the
   browser.
2. Visited states are shaded, the trail names every nested flow, and a crumb opens its
   flow. Done when the view follows the demo run into a handed-off flow and back.

## 7. Assumptions

1. A layered layout reads well for flows up to about 15 states. Basis: claim 5. If wrong,
   vendor a layout library, which needs a download.
2. A machine of about 40 KB travels as one log attribute intact. Basis: no attribute length
   limit is configured. If wrong, send one record per flow.
3. Building the author machine takes under 1 s. Basis: the dry run builds the same graphs.
   If wrong, build it on a background thread.
