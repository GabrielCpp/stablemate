"""Shared plumbing for a test suite that gates its own inline book fixtures on `unknown-bullet`.

A `UINode` a test builds is a book nothing else in the pipeline reads for grammar the way a real
book is read by `doctor` — so a fixture written against a grammar its own node type stopped
declaring can sit there for years with no witness (the class of defect fixed at `894d2d0f`,
generalized here at `9d6fcf63`/`07ab6d23`). This module is the reusable half of that witness: the
recorder that observes every `UINode` a process constructs, and the function that turns a slice of
them into the violations `doctor`'s `unknown-bullet` check would raise on a real run. A caller
wires its own autouse fixture and its own allow-set (for fixtures that deliberately exercise an
undeclared key) around these — see `ostler/tests/conftest.py` for the shape.

One reconciliation worth stating here because the next person to run a raw probe over the tree
will ask: a plain grep for bullets under a key a node's type doesn't declare turns up far more
hits (699 bullets, 27 distinct `(type, key)` pairs, at the time `9d6fcf63` was written) than this
gate ever reports. The gate applies the same real filter `doctor` itself applies —
`registry.unknown_bullet_keys`, which only flags a key that is both undeclared *and*
load-bearing — so a key that is merely undeclared-and-decorative (an author's own vocabulary,
left alone by design) never shows up here. The two counts are not in tension; they are two
different questions.
"""

from __future__ import annotations

from typing import Any

from ostler import model, registry

#: Every `model.UINode` constructed during the current pytest process, appended in construction
#: order by the patched `__init__` below. `meta` is a dict the loader mutates in place after
#: `__init__` returns, so a node recorded here by reference carries its final bullets by the time
#: a test that built it is done — nothing here needs to re-parse anything.
CONSTRUCTED_UI_NODES: list[model.UINode] = []

_original_uinode_init = model.UINode.__init__


def _recording_uinode_init(self: model.UINode, *args: Any, **kwargs: Any) -> None:
    _original_uinode_init(self, *args, **kwargs)
    CONSTRUCTED_UI_NODES.append(self)


# Installed once, at import time, in every process that imports this module (the main process for
# a serial run, each xdist worker for a parallel one) — a patch applied *after* the session starts
# would miss an xdist worker's own copy of `model`, since a worker never inherits a running
# process' monkeypatches, only its own fresh import of the module.
model.UINode.__init__ = _recording_uinode_init


def unknown_bullet_violations(nodes: list[model.UINode]) -> list[str]:
    """Every `(type, key)` violation `doctor`'s `unknown-bullet` check would raise on *nodes*."""
    return [
        f"{node.type}.{key} ({node.id or node.path})"
        for node in nodes
        for key in registry.unknown_bullet_keys(node.type, node.meta)
    ]
