#!/usr/bin/env python3
"""Deterministic site-surface coverage / grounding gate — ostler-backed.

The author workflow proves seed items map to stories *within* an epic
(``validate-epic-coverage.py``), but nothing relates the authored work to the **feature set**.
This gate does, in one of **two modes** — because the backlog is not always a full rewrite, so
"cover every screen" is the wrong default:

* **grounding** (default, always-on): every surface the authored work *claims to touch* — each
  seed item's ``legacySurface`` and each knowledge record's ``surface``/``route`` — must resolve
  to a surface that exists in the feature set. Catches **phantom scope** without ever flagging an
  untouched screen, so an incremental backlog is not forced to re-cover the whole app.

* **full** (opt-in per run, ``coverage_mode=full``): the migration / greenfield-buildout
  assertion — every feature-set surface must be covered by *some* backlog bullet, epic, story, or
  knowledge record. An uncovered surface is reported so the operator adds it (or removes the
  feature Concept).

Source of truth: **two producers, one contract**. The feature set is the set of typed
``feature`` Concepts ostler reads from ``docs/features`` (``Ostler.list("feature")``) —
there is no derived feature ``inventory.json`` anymore. Additionally (opt-in by presence),
a **survey-produced unit manifest** (``cfg.surface_manifest``, emitted by the surveyor
workflow) supplies unit-level surfaces: each entry carries the generated-backlog bullet ids
that cover it, so ``full`` mode can assert the migration/buildout claim over a
code-derived inventory — the use the ``coverage_mode: "full"`` design always anticipated.
A unit with no ``bullets`` (a ``clean`` or accepted-``blocked`` unit) carries no work and
demands no coverage.

The claims/coverage haystack is read from ostler through the in-process API: seeds and the
story DAG fold into each ``epic.md`` (``okf.list("seed")`` / ``okf.list("story")``), knowledge
records are markdown Concepts (``okf.list("knowledge")``), and the backlog is ostler-managed
markdown (``okf.backlog()``); the raw backlog file is folded in as well so a generated survey
section still covers even if the graph does not parse it as a bullet.

Opt-in by presence: with no feature Concepts AND no unit manifest on disk the gate is a
clean **skip** (a greenfield repo that has not authored its feature set yet is unaffected).
Coverage is intentionally **generous** (substring match against a normalized haystack): a
false "covered" only misses one surface, whereas a false "uncovered" would block authoring.

Reads the OKF graph in-process via ``ostler``'s Python API (``from ostler import Ostler``).

Args:
    argv[1]  manifest       : survey-produced unit manifest (opt-in by presence)
    argv[2]  epics_dir      : repo-relative epics root (informational)
    argv[3]  backlog        : repo-relative backlog markdown (folded into the haystack)
    argv[4]  knowledge_dir  : repo-relative knowledge root (informational)
    argv[5]  mode           : "grounding" (default) | "full"

Outputs JSON: {"surface_coverage_ok": "yes"|"no"|"skip", "surface_coverage_errors": "<lines>"}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(ok: str, errors: list[str] | str = "") -> NoReturn:
    msg = errors if isinstance(errors, str) else "\n".join(errors)
    print(json.dumps({"surface_coverage_ok": ok, "surface_coverage_errors": msg}))
    sys.exit(0)


def norm(s: object) -> str:
    """Lowercase, route-aware token: strip slashes, params (:id / {id}) → 'id', non-alnum → '-'."""
    text = str(s or "").strip().strip("/")
    text = re.sub(r"[:{]\w+\}?", "id", text)  # :id  /  {id}
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _arg(idx: int, default: str) -> str:
    return (sys.argv[idx].strip() if len(sys.argv) > idx and sys.argv[idx] else "") or default


def surface_id(f: dict) -> str:
    """Human-facing id for error messages: area/slug, else slug, else route, else title."""
    area, slug = str(f.get("area", "")).strip(), str(f.get("slug", "")).strip()
    if area and slug:
        return f"{area}/{slug}"
    return slug or str(f.get("route", "")).strip() or str(f.get("title", "")).strip() or "?"


def surface_needles(f: dict) -> list[str]:
    """Normalized tokens that, if found in the covering haystack, mean this surface is covered."""
    area, slug = str(f.get("area", "")).strip(), str(f.get("slug", "")).strip()
    needles: list[str] = []
    if area and slug:
        needles.append(norm(f"{area}/{slug}"))
    if slug:
        needles.append(norm(slug))
    if str(f.get("route", "")).strip():
        needles.append(norm(f["route"]))
    # Keep only tokens long enough to be meaningful (≥3 chars) so a 1-char slug can't match noise.
    return sorted({n for n in needles if len(n) >= 3})


def load_unit_manifest(root: Path, manifest_rel: str) -> list[dict] | None:
    """The survey-produced unit manifest's entries, or None when absent/unreadable.

    Opt-in by presence (the same discipline as every other gate input): a missing or
    unparseable file simply means no unit-level surfaces — never a block.
    """
    if not manifest_rel:
        return None
    path = root / manifest_rel
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    units = data.get("units") if isinstance(data, dict) else None
    if not isinstance(units, list):
        return None
    return [u for u in units if isinstance(u, dict) and str(u.get("id") or "").strip()]


def unit_needles(u: dict) -> list[str]:
    """Normalized tokens that mean a manifest unit is covered: its covering bullet ids
    (the surveyor writes those bullets into the backlog; once author consumes a bullet,
    the same id survives as a seed's ``sourceBullet``) plus the unit path itself."""
    needles = [norm(b) for b in (u.get("bullets") or [])]
    needles.append(norm(u.get("path") or u.get("id")))
    return sorted({n for n in needles if len(n) >= 3})


def build_haystack(okf: Ostler, root: Path, backlog_rel: str = "") -> str:
    """Concatenate a normalized blob of every place a surface could be 'covered'."""
    parts: list[str] = []
    # The raw backlog file, line by line — same content `okf.backlog()` reads, kept as a
    # direct fold-in so a generated survey section covers even if the graph does not parse
    # it as a bullet.
    if backlog_rel and (root / backlog_rel).is_file():
        try:
            for line in (root / backlog_rel).read_text(encoding="utf-8").splitlines():
                parts.append(norm(line))
        except OSError:
            pass
    for s in okf.list("seed"):
        for fld in ("id", "summary", "sourceBullet", "currentState", "legacySurface"):
            parts.append(norm(s.get(fld)))
    for st in okf.list("story"):
        parts.append(norm(st.get("slug")))
        parts.append(norm(st.get("title")))
        for sid in st.get("covers") or []:
            parts.append(norm(sid))
    for rec in okf.list("knowledge"):
        parts.append(norm(rec.get("surface")))
        parts.append(norm(rec.get("route")))
    for item in okf.backlog():
        parts.append(norm(item.get("id")))
        parts.append(norm(item.get("text")))
    return " | ".join(p for p in parts if p)


def collect_claims(okf: Ostler) -> list[tuple[str, str]]:
    """Surfaces the authored work *claims to touch*: (normalized token, human label).

    A claim is a seed item's ``legacySurface`` or a knowledge record's ``surface``/``route`` —
    where authoring asserts "this work is about screen X". (Story slugs are deliberately excluded:
    a slug is a story name, not a surface assertion.)
    """
    claims: list[tuple[str, str]] = []
    for s in okf.list("seed"):
        ls = str(s.get("legacySurface", "")).strip()
        if ls:
            claims.append((norm(ls), f"seed '{s.get('id', '?')}' legacySurface '{ls}'"))
    for rec in okf.list("knowledge"):
        for field in ("surface", "route"):
            val = str(rec.get(field, "")).strip()
            if val:
                claims.append((norm(val), f"knowledge {field} '{val}' ({rec.get('path', '?')})"))
    return claims


def main() -> None:
    manifest_rel = _arg(1, "")
    backlog_rel = _arg(3, "")
    mode = _arg(5, "grounding").lower()
    root = find_repo_root()
    okf = Ostler(root)

    try:
        features: list[dict] | None = okf.list("feature")
    except (OSError, ValueError, RuntimeError):
        features = None
    units = load_unit_manifest(root, manifest_rel)
    if features is None and units is None:
        emit("skip", "OKF graph unreadable and no unit manifest — surface-coverage gate skipped")
    features = features or []
    units = units or []
    if not features and not units:
        emit("skip", "no feature Concepts and no unit manifest — surface-coverage gate skipped")

    if mode == "full":
        # Migration / greenfield-buildout: every feature-set surface AND every surveyed
        # unit that carries work must be covered.
        haystack = build_haystack(okf, root, backlog_rel)
        uncovered: list[str] = []
        for f in features:
            needles = surface_needles(f)
            if not needles:
                continue  # nothing checkable — don't block on it
            if not any(n in haystack for n in needles):
                uncovered.append(surface_id(f))
        for u in units:
            if not (u.get("bullets") or []):
                continue  # clean / accepted-blocked unit — no work, no coverage demanded
            if not any(n in haystack for n in unit_needles(u)):
                uncovered.append(f"unit {u.get('id')}")
        if uncovered:
            emit(
                "no",
                [
                    "surfaces with no covering backlog item / epic / story / knowledge "
                    "record (add a backlog bullet for each, or remove the feature Concept "
                    "/ re-survey the unit):",
                    *(f"  - {sid}" for sid in sorted(uncovered)),
                ],
            )
        emit("yes", "[full] all feature-set surfaces and surveyed units are covered")

    # grounding (default): every claimed surface must resolve to a feature-set surface
    # (or, on a survey-driven repo, to a surveyed unit).
    inv_needles: set[str] = set()
    for f in features:
        inv_needles.update(surface_needles(f))
    for u in units:
        for token in (norm(u.get("path") or u.get("id")), norm(u.get("id"))):
            if len(token) >= 3:
                inv_needles.add(token)

    ungrounded: list[str] = []
    for token, label in collect_claims(okf):
        if len(token) < 3:
            continue  # too short to match meaningfully — don't block on it
        if not any(token in n or n in token for n in inv_needles):
            ungrounded.append(label)

    if ungrounded:
        emit(
            "no",
            [
                "authored work references surfaces that are NOT in the feature set "
                "(add the surface as a feature Concept under docs/features, or fix the reference):",
                *(f"  - {lbl}" for lbl in sorted(set(ungrounded))),
            ],
        )

    emit("yes", "[grounding] all claimed surfaces are grounded in the feature set")


if __name__ == "__main__":
    main()
