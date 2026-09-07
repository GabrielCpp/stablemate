---
type: concept
slug: application-factory-usage
title: Application factory usage
---
# Application factory usage

`create_app` is the single application factory. It assembles the dashboard,
HTTP, websocket, OTLP, and static-asset route handlers, and registers the
discovery, alert-rule, and live-clock lifecycle hooks.

The production-serving journey uses that factory to describe the application
that `groom serve` exposes. The dynamic accessibility-audit journey uses the
same factory to boot that application against a synthetic fleet so Chromium can
measure the dashboard an operator receives. Neither journey is a replacement
for the other: one specifies the running service lifecycle, while the other
specifies the test measurement path. The factory itself records no ranking
between those contexts.

- code: `groom/groom/app.py::create_app`
- rule: use the service journey for production startup and delivery; use the audit journey only when measuring the rendered dashboard under its synthetic test setup
