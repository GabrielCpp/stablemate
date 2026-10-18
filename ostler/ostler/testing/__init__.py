"""Shared plumbing for a test suite that gates its own inline book fixtures on `unknown-bullet`."""

from __future__ import annotations

from typing import Any

from ostler import model, registry

CONSTRUCTED_UI_NODES: list[model.UINode] = []

_original_uinode_init = model.UINode.__init__


def _recording_uinode_init(self: model.UINode, *args: Any, **kwargs: Any) -> None:
    _original_uinode_init(self, *args, **kwargs)
    CONSTRUCTED_UI_NODES.append(self)


model.UINode.__init__ = _recording_uinode_init


def unknown_bullet_violations(nodes: list[model.UINode]) -> list[str]:
    """Every `(type, key)` violation `doctor`'s `unknown-bullet` check would raise on *nodes*."""
    return [
        f"{node.type}.{key} ({node.id or node.path})"
        for node in nodes
        for key in registry.unknown_bullet_keys(node.type, node.meta)
    ]
