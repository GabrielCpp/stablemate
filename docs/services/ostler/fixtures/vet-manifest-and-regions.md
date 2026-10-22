---
type: fixture
slug: vet-manifest-and-regions
title: vet manifest and regions
---
# vet manifest and regions

Seeds a `--manifest` and a `--regions` file for `ostler vet`: three documented elements and four
scanned regions, placed far enough apart on the x axis that each pair's overlap is independent of
the others. One pair overlaps at exactly the 0.5 default `--iou-threshold`, one just above it, one
just below it, and the fourth region has no matching element and no accessibility role.

## Steps

### write-manifest

- kind: seed
- run: printf '%s' '[{"selector":".at-boundary","name":"AtBoundary","role":"button","bbox":{"x":0,"y":0,"width":90,"height":90}},{"selector":".above-threshold","name":"AboveThreshold","role":"button","bbox":{"x":1000,"y":0,"width":90,"height":90}},{"selector":".below-threshold-dom","name":"BelowThreshold","role":"link","bbox":{"x":2000,"y":0,"width":90,"height":90}}]' > vet-manifest.json

### write-regions

- kind: seed
- run: printf '%s' '[{"bbox":{"x":30,"y":0,"width":90,"height":90},"role":"button","selectors":[".at-boundary"],"ownRoles":["button"],"names":["AtBoundary"]},{"bbox":{"x":1029,"y":0,"width":90,"height":90},"role":"button","selectors":[".above-threshold"],"ownRoles":["button"],"names":["AboveThreshold"]},{"bbox":{"x":2031,"y":0,"width":90,"height":90},"role":"note","selectors":[".below-threshold-region"],"ownRoles":["note"],"names":[""]},{"bbox":{"x":3000,"y":0,"width":50,"height":50},"role":null,"selectors":[".stray-region"],"ownRoles":[],"names":[]}]' > vet-regions.json
