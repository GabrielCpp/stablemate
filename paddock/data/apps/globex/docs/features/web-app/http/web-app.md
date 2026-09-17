---
type: server
slug: web-app
title: Widget directory bundle
---
# Widget directory bundle

The static server the browser loads the UI from. It has no API routes of its own and no
server-side call to [api-service](../../api-service/http/api-service.md) — it answers
`/healthz` and serves the bundle, and every widget read or write the served pages make is
a browser request straight to api-service's origin. That is what makes this fixture two
separately addressable services rather than one service with a web folder attached, and it
is why the bundle's own files are documented here: the screens document what a reader sees,
this node documents the files that get served to produce them.

- code: `app/web-app/main.go` @a84a667463fc
- code: `app/web-app/static/config.js` @9cc26bcf5c1a
- code: `app/web-app/static/styles.css` @919d0d49910b
- openapi:
- detail: `config.js` carries the one address the bundle is configured with — api-service's
  origin as the *browser* reaches it, not as the compose network does — because the fetch is
  made by the page rather than by this process. `styles.css` is the bundle's whole
  presentation; it is cited here rather than on a screen because both screens are served
  from it and neither one decides it.
- launch:
- entry-url: http://localhost:18102
- health-path: /healthz
- working-directory:
- identity:
- stop:
- boot-timeout:
- walkthrough:

## Endpoints

### get-health
- method: GET
- path: /healthz
- channel:
- message:
- does:
  - report the static server is up, with no dependency on api-service
- emits:
- consumes:
- status: 200
- errors:
- auth: none
- verify: http_status(200, path="/healthz")
- code: `app/web-app/main.go::handleHealth` @a84a667463fc
- openapi:
- detail:
- fixture:
- capture:
- tests:
