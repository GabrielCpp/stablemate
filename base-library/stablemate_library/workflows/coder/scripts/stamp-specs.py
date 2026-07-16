#!/usr/bin/env python3
"""Stamp an OKF `type` onto every spec doc in a story's spec dir.

The coder's process artifacts (plan.md, qa.md, review.md, executive.md, …) are written as
free-form markdown by agents, so their frontmatter is only as reliable as the model's memory.
The prompts ask for `ostler create spec` up front; this is the backstop that makes the guarantee
model-independent. `ostler create spec` is idempotent — an already-typed doc is left untouched
and a typed body is never rewritten — so running this after every writer phase is free.

Only `<spec_dir>/*.md` is stamped: the spec EntityType's glob is `*/*.md`, one level deep, so a
doc nested any deeper is not a Concept and must not be given a type.

Args: <docs_path> <story_slug>
Outputs JSON: {"stamped": "<n>", "specs_typed": "yes"}
"""
from __future__ import annotations

import json
import logging
import sys

from ostler import Ostler, markdown, registry
from workhorse.scriptutil import find_docs_root

logger = logging.getLogger(__name__)


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[stamp-specs] %(message)s")

    docs_path_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    slug = sys.argv[2] if len(sys.argv) > 2 else ""
    if not slug:
        logger.info("no story slug — nothing to stamp")
        print(json.dumps({"stamped": "0", "specs_typed": "yes"}))
        return 0

    docs_root = find_docs_root(docs_path_arg)
    okf = Ostler(docs_root)

    # Resolve through ostler so a repo with a custom specs doc_root still works.
    try:
        spec_dir_rel = okf.spec_path(slug)
    except (OSError, ValueError, RuntimeError):
        spec_dir_rel = ""
    spec_dir = docs_root / (spec_dir_rel or f"docs/specs/{slug}")

    if not spec_dir.is_dir():
        # Nothing written yet (an early phase, or a mode with no spec dir) is not a failure.
        logger.info("no spec dir at %s — nothing to stamp", spec_dir)
        print(json.dumps({"stamped": "0", "specs_typed": "yes"}))
        return 0

    stamped = 0
    for path in sorted(spec_dir.glob("*.md")):
        res = okf.create_spec(slug, path.name)
        if not res.ok:
            logger.info("skipped %s: %s", path.name, res.message)
            continue
        if res.message.startswith("stamped"):
            logger.info("%s", res.message)
            stamped += 1

    # The gate: every spec doc is typed by the time this node exits, or the run stops here.
    # Nothing downstream can silently accumulate okf-missing-type the way 347 docs once did.
    untyped = [p.name for p in sorted(spec_dir.glob("*.md"))
               if p.name not in registry.RESERVED_FILES
               and not registry.type_of(markdown.split(p.read_text(encoding="utf-8")).frontmatter)]
    if untyped:
        logger.error("still untyped after stamping: %s", ", ".join(untyped))
        return 1

    logger.info("stamped %d doc(s) in %s", stamped, slug)
    print(json.dumps({"stamped": str(stamped), "specs_typed": "yes"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
