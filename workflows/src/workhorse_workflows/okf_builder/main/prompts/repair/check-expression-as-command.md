### `check-expression-as-command` — a step's `run:`/`health:` holds a check call

A runbook step's `run:` and `health:` are handed to `bash -c` verbatim at bring-up time.
This one holds a value that parses in the book's **check** vocabulary — `http_status(...)`,
`visible(...)`, `json_path(...)`. Shelled, it does not probe anything; it dies with a bash
syntax error, and the stack reports "failed to come up" for a reason that has nothing to do
with the product.

**A check expression is not a command.** A command is something the machine runs; a check is
something the book claims about what the product did. They are written in different
languages because they are answered by different things — one by a shell exit code, the
other by a driver observing a live surface.

To repair each one, decide which of the two the author meant:

1. **They meant a probe.** Write the shell command that performs it and exits non-zero on
   failure — `curl -fsS http://localhost:8080/healthz`, `pg_isready -h localhost`,
   `port-bound`, `log:<pattern>`. Derive the URL and port from the step's own service and
   the environment node, never invent them. A `health:` that cannot fail is worse than none:
   it reports ready while the backend is down.
2. **They meant a claim about the product.** Then it does not belong on a step at all. Move
   it to the `verify:` of the node that makes the claim — the `endpoint`, `interaction` or
   `component` whose contract that observation is about. A step's own `verify:` is a link
   saying how to tell *the step* ran, not an observation about the product, and it mints no
   obligation.

If neither reading is settled by the source, leave the bullet off and say so in
`doc_status`. A step with no `health:` is an honest gap; a step whose `health:` cannot run
is a bring-up that fails for the wrong reason.
