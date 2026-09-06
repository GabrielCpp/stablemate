"""Read-only CLI adapter for deterministic behavior review preparation."""
from __future__ import annotations

import argparse
import sys

from ostler.behavior import build_audit_packets, extract_claims, extract_evidence
from ostler.model import Graph


def run(graph: Graph, args: argparse.Namespace) -> int:
    try:
        result = build_audit_packets(extract_evidence(graph.root, args.paths), extract_claims(graph),
                                     max_items=args.max_items, max_chars=args.max_chars)
    except (ValueError, OSError) as exc:
        print(f"ostler audit: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        print(f"Prepared {len(result.packets)} packets: {result.selected_candidates} candidates, "
              f"{result.selected_claims} claims. No semantic verdicts inferred.")
        for file in result.inventory.files:
            print(f"{file.path}: {file.status}" + (f" ({file.message})" if file.message else ""))
        for limitation in result.inventory.limitations:
            print(f"Limit: {limitation}")
        print("Use --json for evidence, claims, packet digests, and exact scope counts.")
    return 0
