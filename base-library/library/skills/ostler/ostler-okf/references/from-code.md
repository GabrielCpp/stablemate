# Playbook B steps — modeling from existing code

The step-by-step for [bulk-build.md](bulk-build.md)'s from-code playbook. Reached when you are
recovering the graph an app *already* implements — reading a running codebase and grounding
every node to the real `path::symbol`. The shared method (the six layers, the order, the
convergence gate) is in [bulk-build.md](bulk-build.md); this is only the loop you run.

1. **Discover surfaces from entry points.**
   - **GUI** — templates/render functions and their top-level containers → `screen`s; repeated
     rendered fragments (rows, panels, badges) → `component`s.
   - **CLI** — the argparse/click/typer tree: the app → a `cli`; each subparser → a `command`.
     Document each flag and positional as its **own nested bullet** under `flags:` / `args:` —
     what it does, the context it applies in, and a link to the `concept`/`format` it drives (a
     `--cli` flag → the backend abstraction; a `--params` flag → the format's `vars` field). A
     bare token list is not enough.
   - **HTTP/WS** — the route table (decorators, a router include, a `create_app`) → a `server`; each
     route/WS channel → an `endpoint`.
2. **Recover behaviors from handlers.** Each event handler / click wiring → an `interaction`; each
   request handler, command body, or WS message case → an `invocation`. Read the handler to fill
   `does:` (the state/dom/net/emit effects it actually performs) and `when:` (its guards).
3. **Recover concepts from the type/domain layer.** Domain models, core nouns in names and docstrings
   → domain `concept`s. Key functions/classes/modules the surfaces depend on → **code** `concept`s
   (`code: path::symbol`). An ABC with a registry/factory and concrete subclasses → the base +
   `extends:` fan + a `refs:` from the selector (profile §7.11 — the `--cli` backend pattern).
4. **Ground every node to code as you go.**
   - `code:` = the `path::symbol` that renders/handles it (a template region is a `file` ref).
   - `tests:` = the existing test that proves it (`tests/…::test_…`). If none exists, omit rather
     than invent — a missing `tests:` is fine; a wrong one is a lie.
   - `verify:` = the observation, in the check vocabulary (see the skill body) — and reading the
     code is what tells you which one and with which arguments. The handler that returns 409 on a
     stale write declares `http_status(409, …)`; the one that writes through a store before
     answering declares `persists(subject=…)`. Omitting it is not neutral: it is the one bullet
     nobody downstream can supply for you.
5. **Scaffold, author, converge** — same loop as Playbook A, but the prose is *as-built* (describe
   what the code does, not what you wish it did) and `code:`/`tests:` are real.
