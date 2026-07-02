# `ostler vet` — deterministic visual-fidelity check

## Why this exists

The coder/QA workflow proves "the story is done" by artifact existence (`evidence/*.png`
present) and JSON-pointer assertions (`qa/observations.json`), gated fail-closed by
`edit.py::settle_review`. None of that actually looks at whether the UI *renders* as intended.
That gap has been filled ad hoc by asking a VLM to judge a whole screenshot — non-deterministic,
expensive, and prone to hallucinated findings.

`ostler vet` replaces whole-page VLM judgment with a deterministic cross-check between two
independently-derived views of the same rendered page:

1. **The expected manifest** (`--manifest`) — a curated, test-authored list of elements a QA
   script believes should be visible: selector, role, bbox, visibility, state.
2. **An automatic DOM scan** — every rendered element on the page, dumped mechanically with no
   curation, which `ostler vet` reduces to a labeled region map.

Drift between the two (a stale selector, a removed element, a stray modal/toast the test never
anticipated) is exactly the class of bug a disagreement-based check should surface. The two views
share the same underlying DOM, but they're built from different intentions — one hand-authored,
one exhaustive — so a mismatch is meaningful even though both ultimately read the same page.

## No classical computer vision

An earlier design for this feature assumed pixel segmentation (numpy/Pillow/opencv, color-block
clustering, confidence scores). That's the wrong tool: Chrome DevTools already knows the exact
DOM→pixel mapping. `getBoundingClientRect()` per element is **exact**, not inferred from image
color. So "segmentation" is deterministic and dependency-free:

- Dump every element's exact rect via `getBoundingClientRect`.
- **Merge** elements that share a (near-)identical rect into one region — this collapses
  wrapper/child chains that paint the same box without any heuristic.
- **Label** each merged region from accessibility/landmark role data (`navigation`,
  `complementary`, `banner`, `main`, `form`, `contentinfo`, `dialog` — explicit `role="..."` or
  the implicit tag mapping), walking up to the nearest ancestor that carries one.
- Fall back to `role: null` ("unlabeled") when no accessibility info is present anywhere in the
  group. This is a deliberately limited, correctable fallback — never a guessed label.

This eliminates classical CV entirely: no numpy, no Pillow, no opencv, no probabilistic
confidence thresholds in the segmentation step. Both sides of the comparison are exact browser
geometry; the only "fuzziness" in the whole pipeline is the IoU threshold used to **register**
manifest elements against regions — matching by geometry, not by selector string, so a
renamed/refactored selector that still occupies the same visual space is correctly treated as
"found." That's the class of drift this feature exists to catch, not selector churn.

The one optional exception, `crop.py`, is a downstream convenience: if `Pillow` happens to be
importable, `unlabeled` regions get cropped out of the archived screenshot as small PNGs for a
follow-up VLM pass to look at — instead of the whole page. This is the *only* place an image
library is ever touched, it's fully optional (lazy `try/except ImportError`, degrades to "no
crop, just bbox + screenshot path"), and it's not part of segmentation — the region itself was
already determined by exact geometry before any image is opened.

## Who scans, and the two invocation paths

`ostler vet` owns the connection to Chrome's DevTools Protocol itself; it does not depend on an
external script to have pre-dumped the DOM to a file. It attaches to an already-running Chrome
(started with `--remote-debugging-port` by whatever launched the browser) via
`playwright.chromium.connect_over_cdp(url)`, walks every frame of the live DOM, and performs the
scan + region classification (merge-identical-rects + accessibility-role-label) itself.

```
ostler vet <screenshot.png> --manifest <expected.json> (--cdp-url <url> | --regions <file>) \
  --slug <story-slug> [--state <label>] [--iou-threshold 0.5] [--json] [--write]
```

- `--cdp-url` and `--regions` are mutually exclusive, exactly one required (enforced by an
  argparse mutually-exclusive group).
- `--cdp-url` drives a live connect-scan-classify pass and writes its result as part of the
  returned plan to `docs/specs/<slug>/vet/<state>-regions.json`.
- `--regions <file>` replays a previously-written classification of the same shape instead — no
  browser needed, no `playwright` import at all. This is the path every unit test but the one
  live-scan smoke test (`tests/test_vet_cdp.py`) exercises, and the path available for offline
  re-diagnosis of a prior run.
- One invocation = one screenshot + one manifest + one CDP session (or one regions replay) =
  **one UI state**. Multi-state elements (dropdowns, expandables) are handled by the external
  driver calling `ostler vet` once per state with a different `--state` label, re-navigating or
  re-triggering state between calls — `ostler` never drives page interaction itself.
- `<screenshot.png>` is archived as evidence and referenced in the report/Concept; `ostler` never
  decodes or pixel-analyzes it (the optional `crop.py` step is the sole, optional exception).
- Exit code `0` if clean, `1` if disagreements — mirrors `doctor`'s convention, and follows
  `ostler`'s existing dry-run-by-default `EditPlan`/`--write` pattern so a calling workflow can
  branch on it the same way it already does for `edit settle-review`.

`playwright` is a real dependency, but it is imported lazily, only inside `cdp.py`'s
`connect_and_scan` function body — the base install, the `--regions` replay path, and every unit
test other than the live-scan smoke test need not have it installed. It lives behind the
optional `vet` extra (`ostler[vet]`) plus the `dev` extra (so CI can run the smoke test if the
Playwright browser binary is present; `playwright install` is a separate step this command never
invokes itself).

`pydantic` is different: every shape that crosses a serialization boundary (parsed manifest,
scanned/merged regions, the persisted report) is a `pydantic.BaseModel`, so it's a **core**
dependency, not gated behind `vet` — needed on the `--regions` replay path too, not just the
live-CDP path.

## Module layout (`ostler/ostler/vet/`)

| Module | Responsibility |
|---|---|
| `geometry.py` | `BBox` + `iou()` — pure stdlib beyond pydantic. |
| `manifest.py` | Parses `--manifest`; malformed entries are recorded in `.errors` and skipped, not fatal to the batch. |
| `cdp.py` | Lazily imports `playwright`; connects over CDP, walks every frame's DOM + landmark roles, returns `list[ScannedElement]`. The only module that ever touches `playwright`. |
| `regions.py` | `RegionBox` + `merge()`: groups `ScannedElement`s sharing a (near-)identical rect, labels via role. `RegionList` (a `TypeAdapter`) is the single source of truth for `*-regions.json` (de)serialization. |
| `register.py` | IoU greedy matching between manifest elements and regions: `matched` / `missing` (expected, no rendered region — broken/occluded render) / `unexpected` (rendered, not expected — stray overlay/z-index leak) / `unlabeled` (unexpected *and* `role is None` — held for optional VLM residual review). |
| `crop.py` | Optional: lazily imports `Pillow` to crop `unlabeled` regions out of the screenshot into in-memory PNG bytes; no-ops cleanly if `Pillow` is absent. Never writes to disk itself — dry-run-by-default is enforced by the caller bundling the bytes into the plan. |
| `report.py` | `VetReport`/`VetSummary` models, the `docs/specs/<slug>/vet.md` Concept read-modify-write, and `VetPlan`/`VetFileWrite` (own dry-run-by-default file-write plan, supporting both text and binary content). |
| `run.py` | Orchestrates one invocation end to end and returns `(VetOutcome, VetPlan)`. |

## Registration semantics (`register.match`)

Only manifest elements with `visible=True` participate. Candidate `(dom, region)` pairs with
`iou >= iou_threshold` are sorted by `(-score, i, j)` and greedily assigned — the tie-break on
`(i, j)` makes the match deterministic regardless of the order elements/regions were produced
in, which matters because a live CDP scan has no guaranteed element order across runs.

## Report shape and the `vet.md` Concept

`VetReport` (`report.py`) is persisted via `model_dump_json(by_alias=True)` to
`docs/specs/<slug>/vet/<state>-report.json`. It carries `slug`, `state`, `screenshot`,
`manifest`, `regions` (paths, relative to the repo root when possible), `cdpUrl`,
`manifestErrors`, `config` (`iouThreshold`), a `summary` (`status: clean|disagreements` +
counts), and the four `register.match()` buckets.

`docs/specs/<slug>/vet.md` is a new OKF Concept, `type: spec.vet`. It needs **zero registry
changes** — `registry.py`'s `spec` `EntityType` already globs `*/*.md` under the `specs` doc_root
with `required=("type",)` and `schema=None`, so `spec.vet` conforms exactly like `spec.plan`/
`spec.review`/`spec.qa` do. Frontmatter accumulates one entry per `--state` (`states.<state>`),
replaced in place on re-run of the same state rather than duplicated; top-level `status` is
`disagreements` if *any* recorded state is. The body has one `## State: <name>` section per
state, found/replaced via `markdown.py`'s `Section` tree (mirroring `edit.py`'s read-modify-write
style), prose-listing the `missing`/`unexpected`/`unlabeled` findings.

`VetPlan`/`VetFileWrite` are their own small classes rather than reused `edit.EditPlan`/
`FileChange`: they need `path.parent.mkdir(parents=True, exist_ok=True)` (writing into a `vet/`
subdirectory that may not exist yet) and support optional binary content, since crop PNGs flow
through the same plan.

## Verification

- `ruff check .` from the repo root.
- `uv run pytest tests/` inside `ostler/` — the new `test_vet_*.py` files plus the full existing
  suite. `test_vet_cdp.py` skips cleanly without `playwright` installed; `test_vet_crop.py` skips
  cleanly without `Pillow` installed. Every other vet test runs regardless, dependency-free.
- Manual, live path: start a real Chrome/Chromium with `--remote-debugging-port=9222` against a
  page with real landmarks, hand-build a matching `manifest.json` + a placeholder screenshot, run
  `ostler vet page.png --manifest manifest.json --cdp-url http://localhost:9222 --slug X`
  dry-run then `--write`, confirm `docs/specs/X/vet/default-regions.json` +
  `vet/default-report.json` + `vet.md` all appear and `ostler doctor` on that repo stays clean.
- Manual, replay path: re-run the same invocation with `--regions
  docs/specs/X/vet/default-regions.json` instead of `--cdp-url` (no browser running) and confirm
  an identical report.
