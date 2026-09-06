---
type: concept
slug: okf-builder-web-walkthrough
title: OKF-builder web walkthrough
---
# OKF-builder web walkthrough

The web walkthrough is a standalone subflow that proves an existing OKF book against a running
web application. It derives the launch contract from the documented server, uses one shared CDP
browser for the agent and visual registration, processes one journey or screen at a time, and
records returned discoveries before checking the book for convergence. A service without a
documented screen surface is a clean no-op.

The `walkthrough_web/prompts/walkthrough-web.md` turn is the live-app contract for this subflow.
It receives one selected `journey` or `screen` work item, the service and feature-book roots, the
repository root, the documented entry URL, the screenshot directory, and the shared CDP URL. It
uses the existing book as its route map: it opens the entry URL once, follows documented controls
with the browser, snapshots after transitions, and never deep-links by composing a later URL. It
does not perform destructive actions. For each state it compares the rendered accessibility tree
with the book, records route and control mismatches, captures fresh screenshot evidence, and
registers the visible components with `ostler vet`. A newly reached screen is returned as a
discovery instead of being documented in the same turn.

The turn returns the `WalkTurn` shape: `walk_status` is `confirmed`, `healed`, or `skipped`, and
`discovered` contains zero or more `{kind, target, context}` work items. `confirmed` means the
documented journey or screen matched the live app; `healed` means the turn corrected or added
book evidence; `skipped` means the item could not be walked. Prompt variables and the response
shape are statically checked by [workflow prompt static contracts](workflow-prompt-static-contracts.md).

- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb`
- tests: `workflows/tests/okf_builder/test_workflow.py::test_an_empty_book_is_filled_top_down_from_the_code_s_surfaces`
- detail: [OKF-builder workflow composition root](okf-builder-workflow-composition-root.md)

## Fields

### MAX_WALK_ROUNDS
- type: `int`
- default: `3`
- required: true
- semantics: maximum number of dirty-book fixup drains before the running app is reaped and findings are left for the build
- verify: count(subject="web walkthrough round cap", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::MAX_WALK_ROUNDS`

### BOOT_TIMEOUT_S
- type: `float`
- default: `30.0`
- required: true
- semantics: maximum seconds allowed for the browser to answer its CDP endpoint
- verify: count(subject="web walkthrough browser boot timeout", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/stack.py::BOOT_TIMEOUT_S`

### POLL_INTERVAL_S
- type: `float`
- default: `0.5`
- required: true
- semantics: interval between browser readiness and process-liveness probes
- verify: count(subject="web walkthrough browser polling interval", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/stack.py::POLL_INTERVAL_S`

### TERM_GRACE_S
- type: `float`
- default: `5.0`
- required: true
- semantics: grace period between browser termination and forced process-group kill
- verify: count(subject="web walkthrough browser termination grace", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/stack.py::TERM_GRACE_S`

### CDP_URL
- type: `str`
- default: `http://127.0.0.1:9222`
- required: true
- semantics: fixed loopback endpoint shared by the Playwright MCP and `ostler vet`
- verify: count(subject="web walkthrough CDP endpoint", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/walkthrough.py::CDP_URL`

### VET_BULLET
- type: `str`
- default: `vet`
- required: true
- semantics: bullet whose presence anywhere under a screen proves that the screen has visual registration evidence
- verify: count(subject="web walkthrough visual-evidence marker", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/walkthrough.py::VET_BULLET`

### service
- type: `str`
- default: empty string
- required: true
- semantics: service feature-book name; an empty value means no single app is selected
- verify: count(subject="web walkthrough service input", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.service`

### docs_path
- type: `str`
- default: empty string
- required: true
- semantics: optional docs repository root, otherwise resolved from the run repository
- verify: count(subject="web walkthrough docs input", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.docs_path`

### source_path
- type: `str`
- default: empty string
- required: true
- semantics: source subtree used for the app working directory, otherwise the service name
- verify: count(subject="web walkthrough source input", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.source_path`

### max_items
- type: `int`
- default: `0`
- required: true
- semantics: per-run walkthrough item ceiling; zero means no ceiling
- verify: count(subject="web walkthrough item ceiling input", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.max_items`

## Methods

### setup
- sig: `setup() -> WebApp`
- does: derives the web-app setting, launch contract, worklist path, screenshots directory, and shared CDP endpoint from the configured book
- verify: count(subject="web walkthrough settings", equals=1)
- returns: a `WebApp` setting that marks services without screen surfaces as non-web apps
- verify: json_path(path="$.is_webapp", equals=false)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.setup`

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with its service
- verify: count(subject="web walkthrough service labels", equals=1)
- does: adds the selected work item and progress after item selection
- verify: count(subject="web walkthrough item labels", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.labels`

### start
- sig: `start() -> Continue | Done`
- does: ends cleanly without booting anything when the book has no screen surface
- verify: count(subject="web walkthrough no-screen no-ops", equals=1)
- does: boots or adopts the documented app and waits for its health identity
- verify: count(subject="web walkthrough app boots", equals=1)
- does: boots or adopts the shared CDP browser
- verify: count(subject="web walkthrough browser boots", equals=1)
- does: seeds the unconfirmed journey and screen worklist before continuing to selection
- verify: persists(subject="web walkthrough worklist")
- raises: no workflow error for an app or browser boot failure; the flow exits through its documented cleanup path
- verify: count(subject="web walkthrough fail-soft boot exits", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.start`

### pick
- sig: `pick(app_pgid: str, browser_pgid: str, entry_url: str, cdp_url: str, rnd: int = 0) -> Continue | Done`
- does: selects the next pending walkthrough item without a lifetime item baseline
- verify: count(subject="web walkthrough item selections", equals=1)
- does: reaps the runtime and leaves pending work when the configured item ceiling is reached
- verify: count(subject="web walkthrough item-ceiling teardowns", equals=1)
- does: sends a dry worklist to checkpoint reconciliation
- verify: count(subject="web walkthrough dry checkpoints", equals=1)
- does: dispatches one selected journey or screen to the walk turn
- verify: count(subject="web walkthrough item dispatches", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.pick`

### walk
- sig: `walk(current_item: dict, item_kind: str, item_target: str, item_context: str, app_pgid: str, browser_pgid: str, entry_url: str, cdp_url: str, progress: str = "", rnd: int = 0) -> Continue`
- does: renders the web walkthrough prompt with the selected item, book paths, entry URL, screenshot directory, and CDP endpoint
- verify: count(subject="web walkthrough agent turns", equals=1)
- does: forwards the agent's discovered items and documentation status to marking
- verify: count(subject="web walkthrough agent results", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.walk`
- tests: `workflows/tests/test_prompt_variables.py::test_the_prompt_reads_only_names_the_workflow_can_supply`
- tests: `workflows/tests/test_prompt_output_shape.py::test_the_prompt_documents_the_keys_the_turn_is_asked_for`

### mark
- sig: `mark(current_item: dict, discovered: list[dict], app_pgid: str, browser_pgid: str, entry_url: str, cdp_url: str, rnd: int = 0) -> Continue`
- does: closes the walked worklist item
- verify: count(subject="web walkthrough closed items", equals=1)
- does: records returned discoveries as pending work before selecting again
- verify: persists(subject="web walkthrough discoveries")
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.mark`

### checkpoint
- sig: `checkpoint(app_pgid: str, browser_pgid: str, entry_url: str, cdp_url: str, rnd: int = 0) -> Continue | Done`
- does: runs the shared book checkpoint after the worklist is dry
- verify: count(subject="web walkthrough book checkpoints", equals=1)
- does: reaps the runtime when the walked book is clean
- verify: count(subject="clean web walkthrough teardowns", equals=1)
- does: queues checkpoint fixup items when the book is dirty and the round cap has not been reached
- verify: count(subject="web walkthrough fixup seeds", equals=1)
- does: reaps the runtime and leaves findings when the dirty-book round cap is reached
- verify: count(subject="web walkthrough round-cap teardowns", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb.checkpoint`

### _finish
- sig: `_finish(app_pgid: str, browser_pgid: str) -> Done`
- does: invokes app teardown with the documented stop command and working directory
- verify: count(subject="web walkthrough app teardowns", equals=1)
- does: invokes browser teardown after app teardown
- verify: count(subject="web walkthrough browser teardowns", equals=1)
- does: returns a done result carrying whether the setting identified a web app
- verify: json_path(path="$.is_webapp", equals=true)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/flow.py::WalkthroughWeb._finish`

### parse_launch_contract
- sig: `parse_launch_contract(text: str, repo_root: str, source_root: str) -> dict[str, str]`
- does: extracts launch and entry URL bullets from a server document
- verify: count(subject="web walkthrough launch-contract parses", equals=1)
- does: returns no contract when either launch or entry URL is absent
- verify: json_path(path="$.launch_cmd", absent=true)
- does: resolves relative working directories against the repository root and supplies health, identity, stop, timeout, and walkthrough values
- verify: count(subject="web walkthrough launch-contract fields", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/walkthrough.py::parse_launch_contract`

### select_server
- sig: `select_server(server_paths: Iterable[str], read_contract: Callable[[str], dict[str, str]], logger: logging.Logger) -> dict[str, str]`
- does: selects the sole documented launch contract when only one exists
- verify: count(subject="single web walkthrough server selections", equals=1)
- does: selects the marked `walkthrough` server when one is marked
- verify: count(subject="marked web walkthrough server selections", equals=1)
- does: deterministically selects the first sorted contract and warns when multiple servers are unmarked or multiply marked
- verify: count(subject="ambiguous web walkthrough server selections", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/walkthrough.py::select_server`

### detect_webapp
- sig: `detect_webapp(logger: logging.Logger, docs_path: str = "", service: str = "", source_path: str = "", repo_dir: str = "") -> WebApp`
- does: derives docs, source, and feature roots from workflow inputs
- verify: count(subject="web walkthrough root resolutions", equals=1)
- does: skips cleanly when no service or no screen surface is documented
- verify: json_path(path="$.is_webapp", equals=false)
- does: reads the marked server launch contract, with a compatibility fallback to the service's serve command
- verify: count(subject="web walkthrough runtime-contract detections", equals=1)
- does: creates the build worklist and in-book screenshots directory when a web app is detected
- verify: persists(subject="web walkthrough screenshot directory")
- returns: a `WebApp` containing launch, health, identity, teardown, worklist, screenshots, and CDP settings
- verify: json_path(path="$.cdp_url", equals="http://127.0.0.1:9222")
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/walkthrough.py::detect_webapp`

### seed_walkthrough
- sig: `seed_walkthrough(logger: logging.Logger, wt_worklist_path: str = "", service: str = "", repo_root: str = ".") -> WalkSeed`
- does: loads the service OKF graph and identifies screens without `vet` evidence
- verify: count(subject="web walkthrough unconfirmed-screen calculations", equals=1)
- does: queues journeys that traverse an unconfirmed screen before standalone unconfirmed screens
- verify: persists(subject="web walkthrough journey and screen seeds")
- does: reopens a done item when its required evidence is still absent
- verify: count(subject="web walkthrough evidence reopens", equals=1)
- does: leaves already confirmed screens and fully confirmed journeys done
- verify: count(subject="web walkthrough confirmed-item skips", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/walkthrough.py::seed_walkthrough`

### boot_app
- sig: `boot_app(logger: logging.Logger, launch_cmd: str = "", entry_url: str = "", health_path: str = "/", app_cwd: str = ".", repo_root: str = "", app_identity: str = "", boot_timeout: str = "") -> AppBoot`
- does: starts or adopts the documented app through the shared stack adapter and waits for the health identity
- verify: count(subject="web walkthrough app readiness probes", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/stack.py::boot_app`

### teardown_app
- sig: `teardown_app(logger: logging.Logger, app_pgid: str = "", stop_cmd: str = "", app_cwd: str = "") -> TornDown`
- does: reaps the started app process group or runs its documented stop recipe
- verify: count(subject="web walkthrough app cleanup calls", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/stack.py::teardown_app`

### boot_browser
- sig: `boot_browser(logger: logging.Logger, cdp_url: str = "", repo_root: str = ".") -> BrowserBoot`
- does: adopts an already answering CDP endpoint without claiming ownership
- verify: count(subject="adopted walkthrough browser sessions", equals=1)
- does: starts headless Chromium with an external scratch profile and waits for CDP readiness
- verify: count(subject="started walkthrough browser sessions", equals=1)
- does: kills its process group and fails soft when the browser exits or times out before readiness
- verify: count(subject="walkthrough browser boot failures", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/stack.py::boot_browser`

### teardown_browser
- sig: `teardown_browser(logger: logging.Logger, browser_pgid: str = "") -> TornDown`
- does: skips teardown when no browser process group is owned by this run
- verify: count(subject="adopted walkthrough browser cleanup skips", equals=1)
- does: sends termination, waits through the grace period, and force-kills a remaining owned process group
- verify: count(subject="owned walkthrough browser cleanups", equals=1)
- code: `workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/stack.py::teardown_browser`
