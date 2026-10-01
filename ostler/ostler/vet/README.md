# vet

The `ostler vet` command. It registers the regions of one rendered UI state against what a manifest and the book say should be on screen.

## Map

- `cdp.py`: the live Chrome DevTools connection and the scan of every visible element's rect.
- `crop.py`: cutting region snippets out of the screenshot as small PNGs, when asked.
- `geometry.py`: the exact-rect box both sides of a vet share, and intersection over union.
- `manifest.py`: parsing `--manifest`, the test-authored list of elements a QA script expects.
- `placement.py`: where a documented component should sit on screen and whether it did, and which selector forms each driver accepts.
- `regions.py`: merging scanned elements that share a rect into labeled regions.
- `register.py`: the deterministic greedy IoU match between manifest elements and regions.
- `report.py`: the vet report's shape and the `vet.md` Concept it rewrites.
- `run.py`: one `ostler vet` invocation from a screenshot and a scan or replay to a report.
- `writes.py`: the dry-run-by-default file writes `ostler vet --write` applies, text or binary.
