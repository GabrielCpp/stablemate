"""No `load_graph` call in `ostler.qa.drivers` resolves the book unframed.

`self.root` is the checkout, not the book a compiled plan speaks about — that book can
live anywhere else in the tree, named only by the QA context packet's `featuresRoot`.
`e9e1d153` framed one of two `load_graph` call sites through `_packet_features_root()`
and left the other one reading `self.root`'s own book, which silently passed for the
checkout's own (fixture-less) book and only broke on a book that lived elsewhere.

Checked structurally, over the module's own AST, rather than by grepping source text for
a string: a *third* `load_graph` call added next month fails this test on the day it is
written, whether or not its author remembers this story.
"""

from __future__ import annotations

import ast
import inspect

from ostler.qa import drivers


def _load_graph_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "load_graph"
    ]


def test_every_load_graph_call_carries_root_overrides() -> None:
    source = inspect.getsource(drivers)
    tree = ast.parse(source, filename=drivers.__file__ or "drivers.py")
    calls = _load_graph_calls(tree)

    assert calls, "expected at least one `load_graph` call in ostler.qa.drivers"

    unframed = [
        call
        for call in calls
        if not any(keyword.arg == "root_overrides" for keyword in call.keywords)
    ]
    assert not unframed, (
        "found a `load_graph` call at "
        f"{drivers.__file__}:{unframed[0].lineno} with no `root_overrides` keyword — "
        "`self.root` is the checkout, not the book a compiled plan speaks about; frame "
        "the call through `_packet_features_root()`, the way every other `load_graph` "
        "call in this module already is, rather than reading the checkout's own book"
    )
