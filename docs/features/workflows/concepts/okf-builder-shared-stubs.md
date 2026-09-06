---
type: concept
slug: okf-builder-shared-stubs
title: OKF-builder dry-run stubs
---
# OKF-builder dry-run stubs

The dry-run registry substitutes affirmative gate results so a deterministic run advances through
the workflow without agent turns. The preparation stub marks Ostler usable; clean and covered
stubs converge the book and coverage gates; webapp, app-up, and browser-up drive the optional web
walkthrough. The real empty-worklist result remains the model default for item selection, so a
dry run does not invent work.

- code: `workflows/src/workhorse_workflows/okf_builder/shared/stubs.py`

## Methods

### prepared
- sig: `prepared(*_args: object, **_kwargs: object) -> Prepared`
- does: returns preparation with `ostler_ok` true
- verify: json_path(path="$.ostler_ok", equals=true)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/stubs.py::prepared`

### clean
- sig: `clean(*_args: object, **_kwargs: object) -> Checkpoint`
- does: returns a clean checkpoint result
- verify: json_path(path="$.checkpoint_clean", equals=true)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/stubs.py::clean`

### covered
- sig: `covered(*_args: object, **_kwargs: object) -> Coverage`
- does: returns complete source coverage
- verify: json_path(path="$.coverage_complete", equals=true)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/stubs.py::covered`

### webapp
- sig: `webapp(*_args: object, **_kwargs: object) -> WebApp`
- does: declares a web application for walkthrough routing
- verify: json_path(path="$.is_webapp", equals=true)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/stubs.py::webapp`

### app_up
- sig: `app_up(*_args: object, **_kwargs: object) -> AppBoot`
- does: declares that the application answered its health path
- verify: json_path(path="$.boot_ok", equals=true)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/stubs.py::app_up`

### browser_up
- sig: `browser_up(*_args: object, **_kwargs: object) -> BrowserBoot`
- does: declares that the shared CDP browser answered
- verify: json_path(path="$.browser_ok", equals=true)
- code: `workflows/src/workhorse_workflows/okf_builder/shared/stubs.py::browser_up`
