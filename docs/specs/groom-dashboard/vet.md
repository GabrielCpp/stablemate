---
type: spec.vet
slug: groom-dashboard
status: disagreements
states:
  smoke:
    status: disagreements
    matchedCount: 3
    missingCount: 0
    unexpectedCount: 0
    unlabeledCount: 43
    report: vet/smoke-report.json
  post-discovery:
    status: disagreements
    matchedCount: 6
    missingCount: 0
    unexpectedCount: 34
    unlabeledCount: 7
    report: vet/post-discovery-report.json
---
# Vet: groom-dashboard

## State: smoke

- status: disagreements
- screenshot: docs/features/groom/gui/screenshots/groom-dashboard-smoke.png
- manifest: docs/specs/groom-dashboard/vet/smoke-manifest.json
- matched: 3
- missing: 0
- unexpected: 0
- unlabeled: 43

### Matched (documented components registered on screen)

- `activity-inbox-mode` — iou 1.00 — crop: vet/smoke-activity-inbox-mode.png
- `activity-files-mode` — iou 1.00 — crop: vet/smoke-activity-files-mode.png
- `inbox-list` — iou 1.00 — crop: vet/smoke-inbox-list.png

### Unlabeled (rendered, no accessibility role — needs VLM review)

- at 0,0 (`html:nth(0), body:nth(15), div.app:nth(16)`) — crop: vet/smoke-residual-0.png
- at 0,0 (`#activitybar`) — crop: vet/smoke-residual-1.png
- at 14,18 (`svg:nth(19)`) — crop: vet/smoke-residual-2.png
- at 17,29 (`path:nth(20)`) — crop: vet/smoke-residual-3.png
- at 19,22 (`path:nth(21)`) — crop: vet/smoke-residual-4.png
- at 14,62 (`svg:nth(23)`) — crop: vet/smoke-residual-5.png
- at 18,66 (`path:nth(24)`) — crop: vet/smoke-residual-6.png
- at -0,94 (`div.act-btn:nth(25)`) — crop: vet/smoke-residual-7.png
- at 14,106 (`svg:nth(26)`) — crop: vet/smoke-residual-8.png
- at 20,109 (`path:nth(27)`) — crop: vet/smoke-residual-9.png
- at 20,118 (`path:nth(28)`) — crop: vet/smoke-residual-10.png
- at -0,425 (`div.act-btn:nth(30)`) — crop: vet/smoke-residual-11.png
- at 14,437 (`svg:nth(31)`) — crop: vet/smoke-residual-12.png
- at 22,444 (`circle:nth(32)`) — crop: vet/smoke-residual-13.png
- at 17,440 (`path:nth(33)`) — crop: vet/smoke-residual-14.png
- at 48,0 (`#main, #inbox-pane`) — crop: vet/smoke-residual-15.png
- at 48,0 (`#inbox`) — crop: vet/smoke-residual-16.png
- at 48,0 (`div.pane-head:nth(37)`) — crop: vet/smoke-residual-17.png
- at 58,12 (`span:nth(38)`) — crop: vet/smoke-residual-18.png
- at 199,6 (`input.filter:nth(39)`) — crop: vet/smoke-residual-19.png
- at 48,40 (`div.empty:nth(41)`) — crop: vet/smoke-residual-20.png
- at 370,0 (`#detail`) — crop: vet/smoke-residual-21.png
- at 370,0 (`div.detail-empty:nth(43)`) — crop: vet/smoke-residual-22.png
- at 0,469 (`#statusbar`) — crop: vet/smoke-residual-23.png
- at 10,473 (`span.stat:nth(74)`) — crop: vet/smoke-residual-24.png
- at 10,478 (`span.dot.blocked:nth(75)`) — crop: vet/smoke-residual-25.png
- at 23,473 (`span.n:nth(76)`) — crop: vet/smoke-residual-26.png
- at 97,473 (`span.stat:nth(77)`) — crop: vet/smoke-residual-27.png
- at 97,478 (`span.dot.running:nth(78)`) — crop: vet/smoke-residual-28.png
- at 110,473 (`span.n:nth(79)`) — crop: vet/smoke-residual-29.png
- at 185,473 (`span.stat:nth(80)`) — crop: vet/smoke-residual-30.png
- at 185,478 (`span.dot.idle:nth(81)`) — crop: vet/smoke-residual-31.png
- at 198,473 (`span.n:nth(82)`) — crop: vet/smoke-residual-32.png
- at 251,473 (`span.stat:nth(83)`) — crop: vet/smoke-residual-33.png
- at 251,478 (`span.dot.finished:nth(84)`) — crop: vet/smoke-residual-34.png
- at 264,473 (`span.n:nth(85)`) — crop: vet/smoke-residual-35.png
- at 457,473 (`span.status-right:nth(86)`) — crop: vet/smoke-residual-36.png
- at 457,473 (`span:nth(87)`) — crop: vet/smoke-residual-37.png
- at 603,473 (`span.stat:nth(88)`) — crop: vet/smoke-residual-38.png
- at 603,478 (`span.ws-dot:nth(89)`) — crop: vet/smoke-residual-39.png
- at 656,473 (`#btn-refresh-bar`) — crop: vet/smoke-residual-40.png
- at 692,473 (`span:nth(91)`) — crop: vet/smoke-residual-41.png
- at 692,474 (`span.kbd:nth(92)`) — crop: vet/smoke-residual-42.png

## State: post-discovery

- status: disagreements
- screenshot: docs/features/groom/gui/screenshots/serve-dashboard-and-startup-discovery-post-discovery.png
- manifest: docs/specs/groom-dashboard/vet/post-discovery-manifest.json
- matched: 6
- missing: 0
- unexpected: 34
- unlabeled: 7

### Matched (documented components registered on screen)

- `activity-inbox-mode` — iou 1.00 — crop: vet/post-discovery-activity-inbox-mode.png
- `activity-files-mode` — iou 1.00 — crop: vet/post-discovery-activity-files-mode.png
- `activity-diff-mode` — iou 1.00 — crop: vet/post-discovery-activity-diff-mode.png
- `activity-settings-mode` — iou 1.00 — crop: vet/post-discovery-activity-settings-mode.png
- `inbox-filter-input` — iou 1.00 — crop: vet/post-discovery-inbox-filter-input.png
- `statusbar-refresh-button` — iou 1.00 — crop: vet/post-discovery-statusbar-refresh-button.png

### Unexpected (rendered, not expected)

- role `toolbar` at 0,0 (`#activitybar`)
- role `button` at 14,18 (`svg:nth(19)`)
- role `button` at 17,29 (`path:nth(20)`)
- role `button` at 19,22 (`path:nth(21)`)
- role `button` at 14,62 (`svg:nth(23)`)
- role `button` at 18,66 (`path:nth(24)`)
- role `button` at 14,106 (`svg:nth(26)`)
- role `button` at 20,109 (`path:nth(27)`)
- role `button` at 20,118 (`path:nth(28)`)
- role `button` at 14,437 (`svg:nth(31)`)
- role `button` at 22,444 (`circle:nth(32)`)
- role `button` at 17,440 (`path:nth(33)`)
- role `log` at 48,40 (`#inbox-list`)
- role `log` at 48,40 (`div.empty:nth(41)`)
- role `status` at 0,469 (`#statusbar`)
- role `status` at 10,473 (`span.stat:nth(74)`)
- role `status` at 10,478 (`span.dot.blocked:nth(75)`)
- role `status` at 23,473 (`span.n:nth(76)`)
- role `status` at 97,473 (`span.stat:nth(77)`)
- role `status` at 97,478 (`span.dot.running:nth(78)`)
- role `status` at 110,473 (`span.n:nth(79)`)
- role `status` at 185,473 (`span.stat:nth(80)`)
- role `status` at 185,478 (`span.dot.idle:nth(81)`)
- role `status` at 198,473 (`span.n:nth(82)`)
- role `status` at 251,473 (`span.stat:nth(83)`)
- role `status` at 251,478 (`span.dot.finished:nth(84)`)
- role `status` at 264,473 (`span.n:nth(85)`)
- role `status` at 452,471 (`span.status-right:nth(86)`)
- role `status` at 452,473 (`span:nth(87)`)
- role `status` at 598,473 (`span.stat:nth(88)`)
- role `status` at 598,478 (`span.ws-dot:nth(89)`)
- role `button` at 655,474 (`span:nth(91)`)
- role `button` at 687,471 (`#btn-palette`)
- role `button` at 691,473 (`span.kbd:nth(93)`)

### Unlabeled (rendered, no accessibility role — needs VLM review)

- at 0,0 (`html:nth(0), body:nth(15), div.app:nth(16)`) — crop: vet/post-discovery-residual-0.png
- at 48,0 (`#main, #inbox-pane`) — crop: vet/post-discovery-residual-1.png
- at 48,0 (`#inbox`) — crop: vet/post-discovery-residual-2.png
- at 48,0 (`div.pane-head:nth(37)`) — crop: vet/post-discovery-residual-3.png
- at 58,12 (`span:nth(38)`) — crop: vet/post-discovery-residual-4.png
- at 370,0 (`#detail`) — crop: vet/post-discovery-residual-5.png
- at 370,0 (`div.detail-empty:nth(43)`) — crop: vet/post-discovery-residual-6.png
