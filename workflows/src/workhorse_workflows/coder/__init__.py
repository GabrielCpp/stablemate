"""The coder workflow as a Python state machine.

The port of `base-library/workflows/coder/workflow.yaml` — 4,366 lines of YAML, 308
nodes across nine graphs, and the largest thing in the base library by a wide margin. It
builds an epic: it walks the epic queue, and for each story plans, implements, reviews,
documents and QAs it, then commits, opens one PR per epic, holds it against CI, and
merges.

The package is the same shape `research`, `author` and `okf-builder` established:

* `workflow.py` — the `Coder` class, and only that class
* `nodes/` — the deterministic work, grouped by subject, one `@node` per YAML `script:`
* `flows/` — one `Workflow` subclass per YAML `flows:` entry, reached by `handoff`
* `schemas/` — agent reply models and node return models
* `paths.py` — the derivations the scripts each carried a private copy of
* `prompts/` — the agent turns, verbatim from the YAML workflow

The YAML's name is `epic-coder`; the entry point and the console script are both
`coder`, matching the directory the library resolves it by today.
"""
