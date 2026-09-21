#!/usr/bin/env python3
"""``make okf-verify`` — the predicate a stop condition can be held to."""
from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

from ostler import Ostler, path as okf_path
from workhorse_workflows.okf_builder.main.nodes.coverage import inventory_source

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("okf-verify")


def service_config() -> dict[str, dict]:
    """Per-book ``source``/``excludes``, when the repo configures them."""
    cfg = ROOT / "agents.yml"
    if not cfg.exists():
        return {}
    try:
        import yaml
    except ImportError:
        return {}
    data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    services = (data.get("workflow") or {}).get("okfBuilder", {}).get("services") or {}
    return services if isinstance(services, dict) else {}


def books() -> list[str]:
    features = okf_path.features_root_in(ROOT)
    if not features.is_dir():
        return []
    return sorted(d.name for d in features.iterdir() if d.is_dir())


def verify(book: str, services: dict, tmp: Path) -> tuple[bool, str]:
    conf = services.get(book) or {}
    source = ROOT / (conf.get("source") or book)
    if not source.is_dir():
        return False, f"{book}: no source tree at {source} — the book documents nothing checkable"

    excludes = conf.get("excludes") or []
    if isinstance(excludes, str):
        excludes = [p.strip() for p in excludes.split(",") if p.strip()]

    out = tmp / f"{book}.inventory.json"
    inventory_source(
        LOG,
        source_root=str(source),
        output_path=str(out),
        source_excludes=",".join(excludes),
        repo_root=str(ROOT),
    )

    outcome = Ostler(ROOT).coverage(
        inventory=out, surface=book,
        waivers=okf_path.waivers_path_in(ROOT, book))
    if outcome.status == "invalid":
        return False, f"{book}: coverage could not be computed: {outcome.message}"
    return outcome.ok, outcome.message


def main() -> int:
    services = service_config()
    found = books()
    if not found:
        print("okf-verify: no books under docs/features — nothing to verify, which is not a pass",
              file=sys.stderr)
        return 1

    failures = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for book in found:
            ok, summary = verify(book, services, tmp)
            print(summary)
            if not ok:
                failures.append(book)

    if failures:
        print(f"\nokf-verify: {len(failures)} of {len(found)} books incomplete: "
              f"{', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"\nokf-verify: {len(found)} books complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
