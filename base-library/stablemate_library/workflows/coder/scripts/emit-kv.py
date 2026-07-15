#!/usr/bin/env python3
"""Emit a constant key/value map as JSON — a flow-status marker.

A `flows:` sub-graph can only signal an outcome back to its caller through its
terminal *context* (the FlowNode lifts declared `outputs` by key). Branch nodes
can't set context and terminals carry no payload, so when several terminal paths
must be told apart (a QA flow that ends `passed` vs `exhausted` vs `replan`), a
tiny script node on each path stamps a distinguishing key the parent branches on.

Usage (workflow node):

    - id: mark_qa_passed
      type: script
      script: scripts/emit-kv.py
      args: ["qa_status=passed"]
      outputs: [{ key: qa_status }]
      next: qa_done

Each argv item is a single ``key=value`` pair; everything after the first ``=``
is the (string) value. Prints a JSON object of all pairs to stdout, which
workhorse parses and from which it extracts the node's declared ``outputs``.
Deterministic and side-effect-free.
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    out: dict[str, str] = {}
    for arg in sys.argv[1:]:
        key, sep, value = arg.partition("=")
        if not sep or not key:
            print(f"emit-kv: argument must be key=value (got {arg!r})", file=sys.stderr)
            return 1
        out[key] = value
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
