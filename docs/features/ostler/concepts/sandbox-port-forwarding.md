---
type: concept
slug: sandbox-port-forwarding
title: Sandbox port forwarding
---
# Sandbox port forwarding

The sandbox image that runs an ostler QA harness exposes a loopback port for each upstream a
scenario needs to reach (a browser target, a daemon under test) without binding the sandbox's
network namespace directly to the host. `forwarder.py` runs as its own process inside the
container, reads the `OSTLER_SANDBOX_FORWARD` environment variable as a JSON object mapping each
local port to a `host:port` upstream, and opens one listening socket per entry. Each accepted
connection gets its own pair of relay threads, one per direction, so one slow or stuck peer never
blocks another connection on the same port. A connection idle for 900 seconds on either side is
dropped. When the caller passes a ready-file path as its first argument, the forwarder writes the
number of ports it bound to that file once every listener is up, so the process that started it
can wait for the forwarder to be ready instead of polling the ports.

- code: ostler/docker/sandbox/forwarder.py::main@1a617ef8e11b
- code: ostler/docker/sandbox/forwarder.py::_relay@1a617ef8e11b
- code: ostler/docker/sandbox/forwarder.py::_serve@1a617ef8e11b
- code: ostler/docker/sandbox/forwarder.py::_pump@1a617ef8e11b

## Contract

- mapping: `OSTLER_SANDBOX_FORWARD` is a JSON object of `{"<local-port>": "<host>:<port>"}`
  entries; a value with no `host` before the last `:` is rejected and the forwarder exits 2
  without binding any port.
- readiness: given a ready-file path as `argv[0]`, the forwarder writes the count of bound
  listeners to that file after every listener in the mapping is bound, and before it blocks.
- idle timeout: a relayed connection with no traffic for 900 seconds on either side is closed.
