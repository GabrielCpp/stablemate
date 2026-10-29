---
type: fixture
slug: explain-scratch-repo
title: explain scratch repo
---
# explain scratch repo

Seeds `explain-scratch/`, a small repo of its own under the checkout whose `lab` book holds one
resource page, `camera-booking`, an `http` resource behind a bearer token with a health probe and
one observation, `leases`. No fixture borrows from it and no claim reads it. Commands run there
with `-C explain-scratch`, so no other scenario reads these files.

## Steps

### write-explain-book

- kind: seed
- run: mkdir -p explain-scratch/docs/services/lab/resources && printf -- '---\ntype: entries\nslug: entries\ntitle: lab\n---\n\n- \133Camera booking](resources/camera-booking.md)\n' > explain-scratch/docs/services/lab/entries.md && printf -- '---\ntype: resource\ntitle: Camera booking\n---\n# Camera booking\n\nThe booking service that leases the lab camera.\n\n- reach: http\n- base: http://booking.example.internal:8080\n- credential:\n  - header: Authorization\n  - scheme: Bearer\n  - secret: CAMERA_BOOKING_TOKEN\n\n## Probe\n\n### answers\n\n- kind: probe\n- request: GET /health\n\n## Observations\n\n### leases\n\n- kind: observe\n- request: GET /leases\n' > explain-scratch/docs/services/lab/resources/camera-booking.md
