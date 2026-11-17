story: none
date: 2026-11-17
elements: ReadFleet, ReadWorker, PushProgress, PushBlocked, PushExited
sources: groom/groom/app.py::create_app, groom/groom/app.py::dashboard_ws, groom/groom/app.py::feed_ws, groom/groom/app.py::dashboard_sidecar, groom/groom/app.py::otlp_traces

This pass books the surfaces named for groom: its HTTP routes and its dashboard page. The command line (cli.py and what
it reads), the terminal dashboard (tui/), the three websockets (/ws, /feed, /sidecar) and the OTLP receivers
(/v1/traces, /v1/metrics, /v1/logs) are not played by it, and their files sit under the http book's ignore patterns.
The websockets carry what the HTTP reads of the fleet already say. The OTLP receivers take protobuf, which the book
has no shape to send. A later pass that books one of these surfaces takes its files off the ignore list.
