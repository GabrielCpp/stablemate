"""Orchestrate one `ostler vet` invocation: one screenshot + one manifest + one CDP session
(or one regions replay) = one UI state.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..model import Graph
from . import cdp, crop as crop_mod
from . import manifest as manifest_mod
from . import report as report_mod
from .regions import RegionList, merge
from .register import match


class VetOutcome(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    report: report_mod.VetReport | None = None
    error: str = ""


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _crop_stem(name: str, i: int) -> str:
    """A filename-safe stem for a matched component's crop; positional fallback when the
    manifest entry carries no `name`."""
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
    return stem or f"component-{i}"


def run_vet(graph: Graph, screenshot: Path, manifest: Path, slug: str, *,
            cdp_url: str | None = None, regions_file: Path | None = None,
            state: str = "default", iou_threshold: float = 0.5,
            ) -> tuple[VetOutcome, report_mod.VetPlan]:
    """Exactly one of *cdp_url*/*regions_file* is set (enforced by the CLI's mutually
    exclusive group). The `--cdp-url` path connects, scans, and merges regions itself,
    persisting the classification to `docs/specs/<slug>/vet/<state>-regions.json` as part of
    the returned (dry-run-safe) plan; the `--regions` path replays a previously-written one."""
    spec_dir = graph.doc_roots["specs"] / slug
    vet_dir = spec_dir / "vet"
    writes: list[report_mod.VetFileWrite] = []

    if cdp_url is not None:
        try:
            elements = cdp.connect_and_scan(cdp_url)
        except Exception as exc:  # noqa: BLE001 — any CDP/playwright failure is a run error
            return VetOutcome(error=f"CDP scan of '{cdp_url}' failed: {exc}"), report_mod.VetPlan([])
        regions = merge(elements)
        regions_path = vet_dir / f"{state}-regions.json"
        writes.append(report_mod.VetFileWrite(
            regions_path, RegionList.dump_json(regions, indent=2).decode("utf-8") + "\n"))
        regions_rel = _relative(regions_path, graph.root)
    else:
        assert regions_file is not None
        if not regions_file.is_file():
            return (VetOutcome(error=f"regions file '{regions_file}' does not exist"),
                    report_mod.VetPlan([]))
        regions = RegionList.validate_json(regions_file.read_bytes())
        regions_rel = _relative(regions_file, graph.root)

    manifest_result = manifest_mod.load_manifest(manifest)
    match_result = match(manifest_result.elements, regions, iou_threshold=iou_threshold)

    crops = crop_mod.maybe_crop(screenshot, match_result.unlabeled)
    for i, data in crops.items():
        name = f"{state}-residual-{i}.png"
        match_result.unlabeled[i].crop = f"vet/{name}"
        writes.append(report_mod.VetFileWrite(vet_dir / name, data))

    # Every matched documented component also gets its own visual snippet, cut from the
    # rendered region (not the manifest's expected bbox).
    component_crops = crop_mod.maybe_crop(
        screenshot, [pair.region for pair in match_result.matched])
    for i, data in component_crops.items():
        pair = match_result.matched[i]
        name = f"{state}-{_crop_stem(pair.dom.name, i)}.png"
        pair.crop = f"vet/{name}"
        writes.append(report_mod.VetFileWrite(vet_dir / name, data))

    vet_report = report_mod.build_report(
        slug=slug, state=state,
        screenshot=_relative(screenshot, graph.root), manifest=_relative(manifest, graph.root),
        regions=regions_rel, cdp_url=cdp_url, manifest_errors=manifest_result.errors,
        iou_threshold=iou_threshold, match_result=match_result,
    )

    writes.append(report_mod.VetFileWrite(
        vet_dir / f"{state}-report.json", vet_report.model_dump_json(by_alias=True, indent=2) + "\n"))

    concept_path = spec_dir / "vet.md"
    existing = concept_path.read_text(encoding="utf-8") if concept_path.is_file() else None
    writes.append(report_mod.VetFileWrite(
        concept_path, report_mod.build_vet_concept(existing, vet_report)))

    return VetOutcome(report=vet_report), report_mod.VetPlan(writes)
