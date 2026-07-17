#!/usr/bin/env python3
"""``make okf-verify`` — the predicate a stop condition can be held to.

Every book under ``docs/features/`` is inventoried from its source and joined against its
``code:`` citations (``ostler coverage``). An incomplete book exits non-zero.

**Why this exists as a target rather than a report.** A goal phrased as prose — *"the OKF books
are complete and accurate"* — is judged by the same self-assessment the builder's gate was built
to remove, now sitting at the outermost loop where nothing checks it. Phrased as ``make
okf-verify exits 0`` it is something a run can be refused by. That is what the coverage
instrument is ultimately for: not a number for a report, but a predicate that can say no.

The bar grows one assertion per stage: coverage per book today; screens-confirmed-vs-documented
and walk-armed-rather-than-skipped once the walk is declared rather than detected.

Service → source root comes from ``workflow.okfBuilder.services`` in ``agents.yml`` when it is
configured, else a book named ``<x>`` is assumed to document the ``<x>/`` subtree — which is the
one-repo/one-book convention the builder already defaults to.
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "base-library" / "workflows" / "okf-builder" / "scripts" / "inventory-source.py"


def load_inventory_module():
    """Import the builder's inventory front end as a library.

    It is loaded by path because its filename is hyphenated (it is a workflow script node
    first), not because it is a subprocess — verify must see its errors as exceptions, not
    scrape them out of stdout.
    """
    spec = importlib.util.spec_from_file_location("okf_inventory_source", INVENTORY)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the source inventory front end at {INVENTORY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    features = ROOT / "docs" / "features"
    if not features.is_dir():
        return []
    return sorted(d.name for d in features.iterdir() if d.is_dir())


def verify(book: str, services: dict, inv_mod, tmp: Path) -> tuple[bool, str]:
    from ostler import Ostler
    from ostler.coverage import is_complete, render

    conf = services.get(book) or {}
    source = ROOT / (conf.get("source") or book)
    if not source.is_dir():
        return False, f"{book}: no source tree at {source} — the book documents nothing checkable"

    excludes = conf.get("excludes") or []
    if isinstance(excludes, str):
        excludes = [p.strip() for p in excludes.split(",") if p.strip()]

    out = tmp / f"{book}.inventory.json"
    argv = [str(INVENTORY), str(source), str(out), ",".join(excludes), str(ROOT)]
    saved, sys.argv = sys.argv, argv
    try:
        inv_mod.main()
    except SystemExit:
        pass  # the script node emits its summary and exits 0; the artifact is what we want
    finally:
        sys.argv = saved

    try:
        result = Ostler(ROOT).coverage(
            inventory=out, surface=book,
            waivers=ROOT / "docs" / "features" / book / "coverage-waivers.json")
    except (OSError, ValueError, RuntimeError) as exc:
        return False, f"{book}: coverage could not be computed: {exc}"
    return is_complete(result), render(result)


def main() -> int:
    inv_mod = load_inventory_module()
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
            ok, summary = verify(book, services, inv_mod, tmp)
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
