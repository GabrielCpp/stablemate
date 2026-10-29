---
type: concept
slug: describing-an-outside-system-a-qa-run-depends-on
title: Describing an outside system a QA run depends on
---
# Describing an outside system a QA run depends on

A QA run sometimes depends on a system the book does not start, such as a booking service that
leases a lab camera to one run at a time. The book describes that system once, as a `resource`
page, and the claims that need it name it. The harness reaches it, asks whether it is there,
borrows from it, gives back what it borrowed, and reads its own record of what the app did.

The page lives at `docs/services/<service>/resources/<name>.md`, and its stem is the name every
other bullet uses. The ostler book depends on no outside system, so it holds no resource page.

- code: ostler/ostler/resource_checks.py::check_resources@2a4781418347
- code: ostler/ostler/resource_checks.py::check_request_step@2a4781418347
- code: ostler/ostler/explain.py::run@ca5fa7fbe8d3
- code: ostler/ostler/qa/book_fixtures.py::resolved_resources@26e58a44f4ed
- code: ostler/ostler/qa/compile_observe.py::observation_lines@53b6536bb58c
- code: ostler/ostler/qa/compile_observe.py::within_off_observation@53b6536bb58c
- code: ostler/ostler/qa/harness/ostler_qa_resources.py::ResourceDesk@6b2c8a83c7cd
- code: ostler/ostler/qa/harness/ostler_qa_resources.py::ResourceDesk.ensure_reachable@6b2c8a83c7cd
- code: ostler/ostler/qa/harness/ostler_qa_resources.py::ResourceDesk.release_all@6b2c8a83c7cd
- code: ostler/ostler/qa/harness/ostler_qa_resources.py::ResourceDesk.observe@6b2c8a83c7cd
- code: ostler/ostler/qa/harness/ostler_qa.py::Qa._owe_releases@80d0580df929
- code: ostler/ostler/qa/harness/ostler_qa.py::Qa.release_all@80d0580df929
- code: ostler/ostler/qa/harness/ostler_qa.py::Qa.observe@80d0580df929
- code: ostler/ostler/qa/drivers.py::run_pending_releases@ea4f7c0dd596
- code: ostler/ostler/qa/attribution.py::Signature@9cd259bdbe3c
- code: ostler/ostler/checks.py::WITHIN_PREAMBLE@b3b97ff94fb4
- rule: a fixture that borrows from a resource states `lifetime: scenario`, so each scenario takes its own borrow and gives it back
- rule: releases run last borrowed first, and a release that fails never stops the others
- rule: a failed release fails a scenario that had passed
- rule: a release sees the fixture's facts as they stand when the scenario ends, so a fact a later step binds is in reach
- rule: `within=` is legal only on a row held on an `observe:`, and a row that never held reports the last value the harness read
- rule: a probe runs once per harness process, before the first step or observation on its resource
- rule: the check vocabulary has no entry for `within=`, because it applies to every check that reads a subject, and the `ostler checks` preamble documents it once
- rule: the page names an environment variable and never its value, and no page, plan, transcript or record carries the value
- tests: ostler/tests/test_qa_harness_resources.py::test_a_scenario_borrows_plays_observes_and_gives_the_camera_back
- tests: ostler/tests/test_qa_harness_resources.py::test_the_camera_goes_back_after_the_scenario_raises
- tests: ostler/tests/test_qa_harness_resources.py::test_the_camera_goes_back_after_a_check_fails
- tests: ostler/tests/test_qa_harness_resources.py::test_an_absent_booking_service_is_a_capability_gap_naming_the_resource
- tests: ostler/tests/test_qa_harness_resources.py::test_observe_polls_until_the_late_recording_arrives
- tests: ostler/tests/test_qa_harness_resources.py::test_observe_fails_with_the_last_read_when_it_never_holds
- tests: ostler/tests/test_qa_harness_resources.py::test_the_credential_reaches_the_resource_and_nothing_the_scenario_wrote
- tests: ostler/tests/test_qa_harness_resources.py::test_a_run_that_died_still_gives_the_camera_back
- tests: ostler/tests/test_qa_harness_resources.py::test_a_release_the_scenario_already_sent_is_not_sent_again
- tests: ostler/tests/test_registry_resource.py::test_resource_is_a_file_type_with_probe_and_observation_containers
- tests: ostler/tests/test_registry_resource.py::test_observe_is_declared_on_the_claim_types
- tests: ostler/tests/test_registry_resource.py::test_the_valid_booking_book_raises_none_of_the_resource_codes
- tests: ostler/tests/test_registry_resource.py::test_each_resource_code_fires_on_the_smallest_page_that_breaks_it
- tests: ostler/tests/test_explain.py::test_explain_prints_the_five_sections_in_order
- tests: ostler/tests/test_explain.py::test_explain_names_the_claims_that_observe_a_resource
- tests: ostler/tests/test_explain.py::test_an_unknown_resource_exits_one_and_says_how_to_look
- tests: ostler/tests/test_qa_compile_observe.py::test_an_observation_compiles_to_a_polling_read_and_a_verify_without_within
- tests: ostler/tests/test_qa_compile_observe.py::test_an_observation_without_within_reads_once
- tests: ostler/tests/test_qa_compile_observe.py::test_within_on_a_response_row_is_a_gap_and_not_a_wait
- tests: ostler/tests/test_qa_compile_observe.py::test_an_observation_naming_no_resource_is_a_gap
- tests: ostler/tests/test_qa_compile_observe.py::test_an_observation_the_page_does_not_hold_is_a_gap
- tests: ostler/tests/test_qa_compile_observe.py::test_an_observe_value_that_is_not_a_reference_is_a_gap
- detail: [ostler qa commands](../qa.md)
- detail: [ostler doctor defects](../doctor-checks.md)
- detail: [ostler](../cli.md)
- detail: [ostler book checks](../book-checks.md)

## The resource page

A resource page states how the harness reaches the system with `reach:`, which is `http` or `cli`.

- An `http` resource states `base:`, the URL every request path is appended to. The URL may carry
  `$NAME`, which the harness expands from its own environment at run time. A `$NAME` that is unset
  makes every claim that needs the resource gapped.
- An `http` resource may state a `credential:` with a `header:`, a `secret:` and an optional
  `scheme:`. The harness sends `<header>: <scheme> <value>` on every request to the resource. The
  `secret:` is the NAME of an environment variable.
- A `cli` resource states `binary:`, the program its steps run. The harness looks the program up
  with `which` before the first step. A `cli` resource may state `secrets:`, the names of the
  environment variables the harness puts in the environment of every `run:`, and `install:`, one
  line telling a person how to get the binary.
- A key of the other reach is a doctor finding, as is a `base:` that names this machine.

`## Probe` holds exactly one step of `kind: probe`. The probe answers yes when its `GET` request
returns a 2xx status on an `http` resource, or when its command exits 0 on a `cli` resource.
`## Observations` holds one `kind: observe` step per record of the system a claim may read. An
`http` observation is a `GET` request. A `cli` observation is a command that prints JSON on
stdout.

## Borrowing and releasing

A fixture takes a thing from the resource with a `kind: borrow` step and gives it back with a
`kind: release` step. Both name the resource with `on:` and send a `request:` on an `http`
resource or run a `run:` on a `cli` resource. A borrow runs in order, and a fact it prints is
readable through `provides:`.

A release does not run in order. When a borrow succeeds, the harness registers every release step
that follows it and announces each one in the run's record as a `release-pending` event. It sends
the releases when the scenario ends, however the scenario ended: passed, failed or errored. Each
release it sends is recorded as a `release` event with `ok` and a `detail`.

When a scenario times out, the scenario process is gone. The parent runner then reads the
`release-pending` events, skips every one that has a `release` event, and sends the rest, last
announced first, with the credential from its own environment. A release whose path or base still
holds an unbound `$NAME` is not sent.

## Reading the resource's own record

A claim reads a resource's record with `observe: @<resource>.<observation>`. The `verify:` rows
after that bullet read the observation's JSON, up to the next `observe:`. The rows before the
first `observe:` read the response.

A row held on an observation may carry `within=<seconds>`. The harness re-reads the observation
every half second until every `within=` row holds or the seconds pass, then asserts the rows on
the last read. A row that never held fails with the value of that last read. The plan compiles an
observation to a `qa.observe(resource, observation, within=N, until=[...])` call, and each row to
a `qa.verify` on the document it returned. The harness records one `observe` event per read with
the resource, the observation, the number of polls and the elapsed milliseconds.

## When the resource is absent

The harness runs the probe before the first step or observation on a resource. A probe that gets
no answer, a binary missing from the PATH, an unset secret and an unset `$NAME` in `base:` are
each a capability fault on the resource. Every claim that needs the resource is gapped, and the
report reads `gapped: <resource name> absent`, where the name is the page's stem with its dashes
as spaces. `camera-booking.md` reads `gapped: camera booking absent`. A writer never sees a gapped
claim, because only a person can bring the system back.

## The secret rule

The value of a credential lives in the harness's own environment and nowhere else. The page names
the variable. The harness logs a request as `METHOD url` and never a header value, nor a body that
a secret was substituted into. A `release-pending` event carries the path with the secret names
left unbound.

## Reading a resource back

`ostler explain <name>` prints a resource's page, its probe, its observations, the fixtures that
borrow it and the claims that reach it. See [the explain command](../book-checks.md#ostler-explain).
