---
type: concept
slug: vetting-a-rendered-screen
title: Vetting a rendered screen
---
# Vetting a rendered screen

`ostler vet` checks a book's claims about a UI screen — which components render,
where, and under what accessible name — against what a real browser actually shows. The caller
supplies a screenshot and a manifest of the elements a QA script found on the page (or, for a
replay, an already-scanned regions file), and the command registers each documented component
against the nearest matching element by rectangle overlap, then reports what matched, what the
book expected but the page never rendered, and what the page rendered that the book never
documented.

A manifest entry is parsed by `manifest.py`, carrying a `BBox` (`geometry.py`) rect, a CSS
selector, and the accessible name and role a QA scan recorded for it. `cdp.py` is the other
source of truth: given a live Chrome DevTools Protocol URL instead of a manifest, it connects
with Playwright, walks every frame of every page, and returns the same shape of element.
`regions.py` merges elements sharing a near-identical rect into one region, since a styled
wrapper and its single child often occupy the same pixels and should count as one registrable
target; `register.py` then runs a greedy, deterministic IoU match between the book's documented
components and the merged regions, sorted by score so the best overlaps claim their region
first. `placement.py` turns a component's declared `placement:` bands (`key min-max%` of the
viewport, one key per axis) into pass/fail against the matched region's measured rect, and
`_name_disagreement` compares the book's declared accessible name — template holes and all —
against the name the scan actually recorded.

`crop.py` optionally slices small PNGs out of the screenshot: one per unlabeled residual region
for a downstream visual review, one per matched component as a visual reference, skipped
silently when Pillow is not installed or the screenshot is missing. `writes.py` collects every
file the run wants to produce as a dry-run-by-default diff; nothing touches disk until
`--write` applies it. `report.py` builds the run's `VetReport` and folds it into the story's
`vet.md` concept page, keyed by `--state` so a second run of the same state replaces its section
instead of appending a duplicate. `run.py` orchestrates one `ostler vet` invocation
end to end, and `__init__.py` re-exports the two names (`VetOutcome`, `run_vet`) the CLI calls.

- code: ostler/ostler/vet/__init__.py@2e20aecf0259
- code: ostler/ostler/vet/run.py::run_vet@43917e56aea7
- code: ostler/ostler/vet/run.py::VetOutcome@43917e56aea7
- code: ostler/ostler/vet/geometry.py::BBox@a6d2ef1e40b6
- code: ostler/ostler/vet/geometry.py::iou@a6d2ef1e40b6
- code: ostler/ostler/vet/cdp.py::connect_and_scan@77027b587d70
- code: ostler/ostler/vet/crop.py::maybe_crop@116a8b739a47
- code: ostler/ostler/vet/manifest.py::load_manifest@4b54d3b4e9ea
- code: ostler/ostler/vet/manifest.py::DomElement@4b54d3b4e9ea
- code: ostler/ostler/vet/regions.py::merge@94a27f0a4ad7
- code: ostler/ostler/vet/regions.py::RegionBox@94a27f0a4ad7
- code: ostler/ostler/vet/register.py::match@4813a8dbde2b
- code: ostler/ostler/vet/writes.py::VetFileWrite@d000fa666d75
- code: ostler/ostler/vet/writes.py::VetPlan@d000fa666d75
- code: ostler/ostler/vet/placement.py::parse_placement@7d128ab112d9
- code: ostler/ostler/vet/placement.py::check@7d128ab112d9
- code: ostler/ostler/vet/placement.py::screen_components@7d128ab112d9
- code: ostler/ostler/vet/report.py::build_report@30d577ca0ec9
- code: ostler/ostler/vet/report.py::build_vet_concept@30d577ca0ec9
- detail: [ostler](../cli.md)

## Contract

- exclusivity: exactly one of a CDP URL or a regions file drives a run; the CLI enforces this
  as a mutually exclusive group before `run_vet` is ever called.
- matching: a documented component and a scanned region match only above `--iou-threshold`
  (default 0.5), chosen greedily best-score-first so no region or component is claimed twice; a
  component below threshold for every region reports as `missing`, a region no component claims
  reports as `unexpected` (it has an accessibility role) or `unlabeled` (it does not).
- placement: a `placement:` band is a percentage of the viewport on one axis (`x`, `y`, `width`
  or `height`); a value with an empty part, an unknown key, a key named twice, bounds that run
  backwards, or a bound over 100% is rejected as a whole, never partially parsed.
- conditional components: a component whose book entry (or any node it `same-as:` links to)
  declares a `states:` or `exclusive-with:` other than "none" is exempt from a `missing` verdict,
  since the book itself says it is not always on screen.
- writes: every file the run produces — region dumps, crops, the JSON report, the updated
  `vet.md` section — is a diff until `--write` is passed; `VetPlan.apply` is the only thing that
  touches disk.
