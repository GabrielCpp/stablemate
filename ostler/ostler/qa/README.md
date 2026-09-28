# ostler qa

The `ostler qa` commands: map a change to the book obligations it owes, compile a QA
plan from the book, run it, and report the evidence.

## Map

- `book_fixtures.py`: book-declared fixtures, walked into the shape the harness executes them from.
- `book_index.py`: what every scenario builder in one plan reads off the whole book, and the base URLs this run resolved for it.
- `captures.py`: the `capture:` bullet grammar, a fact a scenario produces by running and where to read it.
- `clean.py`: `ostler qa clean`, which removes the scratch roots the old sibling layout left behind.
- `compile.py`: the QA plan skeleton compiled out of the book, without reading the implementation.
- `compile_cli.py`: the CLI builders, a `command` node's claims and a journey of `run:`s as `qa.tool(...)` calls.
- `compile_http.py`: the endpoint builders, a route's claims as HTTP calls and a journey walked as requests.
- `compile_journey.py`: the flow builders, which bind each flow's journey to one driver and walk its steps.
- `compile_maestro.py`: the mobile builders, each owed screen claim and each journey as a Maestro flow.
- `compile_page.py`: the screen builders, one arrival scenario per screen and one per interaction arm.
- `compile_playwright.py`: the Playwright pieces page scenarios and web journeys share: locators, hops, observations and acts.
- `compile_support.py`: what the page, endpoint and mobile builders share past the plan source itself.
- `context.py`: the changed-code to book obligation mapping that builds the `qa context` packet.
- `dispatch.py`: which node type a runner can be given a row for.
- `drivers.py`: the execution adapter for a QA target, which runs its scenarios as Python and keeps the ledger.
- `evidence_map.py`: the join of obligations to evidence, with coverage as a set difference.
- `fixtures.py`: declared QA fixtures, the named arrangements a plan may ask for and where they live.
- `frames.py`: `ostler qa frames`, the frames around a step pulled out of a run's recording.
- `grounding_health.py`: the health findings the context packet reports about the book, citations that resolve nowhere and relation subjects named too broadly.
- `harness/`: the modules a generated `qa_plan.py` imports at run time.
- `harness_host.py`: ostler's side of the QA harness boundary, where the harness lives and how to ask it to describe.
- `lint.py`: `ostler qa lint`, the static gate a `qa_plan.py` must pass before it may run on the host.
- `manifest.py`: the current run's artifact manifest, with content-addressed provenance.
- `navigation.py`: each surface's navigation row from the context packet, read once into typed records.
- `obligation.py`: one obligation of the context packet, read once into typed records where the compiler takes it in.
- `obligation_frame.py`: the frame every obligation of a book node shares, its surface, journey, locators and repeat contract, and the typed records that carry it.
- `outcome.py`: `QaOutcome`, the return shape every `ostler qa` subcommand shares.
- `owners.py`: which book nodes own a change, the reasons a node is selected and the families that cite each changed file and symbol.
- `packet.py`: the `qa context` packet `compile-plan` reads, validated once into one typed record.
- `plan.py`: version-2 QA plan parsing and fail-closed semantic validation.
- `plan_source.py`: what every plan builder shares, the gap record and the literal spelling of a check call.
- `references.py`: the one reference grammar `fixture:`, `needs:`, route paths, request bodies and `verify:` share.
- `report.py`: the run, rendered for the person who has to sign it off.
- `run.py`: the dispatch of every `ostler qa` subcommand.
- `runbook.py`: the durable QA stack, read out of the book's ops nodes.
- `sensitivity.py`: whether a declared check can go red at all, measured rather than assumed.
- `session.py`: QA session state, the NDJSON run log, the capture store and the daemon PID registry.
- `source_context.py`: the typed inputs for mapping source repositories onto one documentation graph.
- `stack.py`: the lifecycle of a QA or dev stack that must outlive a single agent turn.
- `tools.py`: the QA tool registry, which external commands a repo opted into and what they resolve to on this machine.
- `v2.py`: version-2 QA orchestration across the command, browser and mobile drivers.
