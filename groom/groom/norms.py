from __future__ import annotations

import logging
from typing import Any

from groom import pools, store

logger = logging.getLogger("groom.norms")

MIN_RUNS = store.MIN_NORM_RUNS

CACHE: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
_NODE_OF_RUN: dict[str, tuple[str, str]] = {}
_COMPUTING: set[tuple[str, str]] = set()
_REVISION = [0]
KINDS = {"agent": "turn", "step": "step"}


def revision() -> int:
    """How many cached norms changed after their first read, so a pane knows its comparison is stale."""
    return _REVISION[0]


def cached(workflow: str, node: str) -> dict[str, dict[str, Any]] | None:
    """The cached norms for one node, or None before the first read returns. Never touches the store."""
    return CACHE.get((workflow, node))


def reading(norm: dict[str, Any] | None) -> dict[str, Any] | None:
    """One cached kind as the strip shows it: the median once enough runs back it, else only the run count."""
    if norm is None:
        return None
    runs = int(norm["runs"])
    enough = runs >= MIN_RUNS and norm["median_s"] is not None
    return {"median_s": norm["median_s"] if enough else None, "runs": runs}


def needs_read(run_id: str, workflow: str, node: str) -> bool:
    """True when this render should queue a read: the node is not cached, or the run just moved to it."""
    if not workflow or not node:
        return False
    key = (workflow, node)
    moved = _NODE_OF_RUN.get(run_id) != key
    _NODE_OF_RUN[run_id] = key
    return key not in _COMPUTING and (key not in CACHE or moved)


async def refresh(workflow: str, node: str) -> bool:
    """Read one node's norms through the query pool into the cache. Returns whether the cache changed."""
    key = (workflow, node)
    if key in _COMPUTING:
        return False
    _COMPUTING.add(key)
    try:
        computed = await pools.QUERY.run(store.node_norms, workflow, node)
    except Exception:
        logger.warning("norms for %s/%s could not be read", workflow, node, exc_info=True)
        return False
    finally:
        _COMPUTING.discard(key)
    changed = CACHE.get(key) != computed
    if changed and key in CACHE:
        _REVISION[0] += 1
    CACHE[key] = computed
    return changed


def for_nodes(workflow: str, nodes: dict[str, str]) -> dict[str, dict[str, Any] | None]:
    """The strip's reading for each node, filling the cache for the ones never read. Runs on the query pool, so it may read the store."""
    found: dict[str, dict[str, Any] | None] = {}
    for node, kind in nodes.items():
        key = (workflow, node)
        if not workflow or not node:
            found[node] = None
            continue
        if key not in CACHE:
            CACHE[key] = store.node_norms(workflow, node)
        found[node] = reading(CACHE[key][KINDS[kind]])
    return found


def reset() -> None:
    CACHE.clear()
    _NODE_OF_RUN.clear()
    _COMPUTING.clear()
    _REVISION[0] = 0
