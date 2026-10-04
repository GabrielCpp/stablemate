"""What a `route:` bullet can and cannot be compared against."""

from __future__ import annotations

import re

from ostler import routes


def test_a_parameterised_route_is_not_a_literal_to_compare_against() -> None:
    """A route with a parameter names a family of pages, in either of the book's spellings."""
    assert routes.literal_route("/links/:id/edit") == ""
    assert routes.literal_route("/links/{id}/edit") == ""
    assert routes.literal_route("/dashboard/") == "/dashboard"
    assert routes.literal_route("/") == "/"
    assert routes.literal_route("https://example.com/dashboard") == ""


def test_arrival_compares_paths_and_ignores_state_within_a_screen() -> None:
    assert routes.arrived_at("http://localhost:18102/dashboard?page=2#top", "/dashboard")
    assert routes.arrived_at("http://localhost:18102/", "/")
    assert not routes.arrived_at("http://localhost:18102/settings", "/dashboard")


def test_a_parameterised_route_is_arrived_at_when_each_parameter_fills_one_segment() -> None:
    """A parameter stands for one path segment, so the page is that screen whatever id it shows."""
    assert routes.arrived_at("http://localhost:18102/links/42/edit?tab=a", "/links/:id/edit")
    assert routes.arrived_at("http://localhost:18102/links/42/edit", "/links/{id}/edit")
    assert not routes.arrived_at("http://localhost:18102/links/42", "/links/:id/edit")
    assert not routes.arrived_at("http://localhost:18102/links/42/7/edit", "/links/:id/edit")


def test_a_parameterised_route_loses_to_a_sibling_that_spells_the_path_literally() -> None:
    """`/links/new` is the new-link screen, and never the link screen whose id happens to read `new`."""
    siblings = ["/links/new", "/links/:id"]
    assert not routes.arrived_at("http://localhost:18102/links/new", "/links/:id", siblings)
    assert routes.arrived_at("http://localhost:18102/links/42", "/links/:id", siblings)


def test_the_arrival_regex_matches_a_whole_url_at_the_route_and_nothing_short_of_it() -> None:
    """The harness waits on this before it photographs, so a redirect still in flight must not match."""
    regex = re.compile(routes.arrival_regex("/links/:id/stages/:form"))
    assert regex.fullmatch("http://localhost:18102/links/42/stages/7?tab=a")
    assert regex.fullmatch("http://localhost:18102/links/42/stages/7/")
    assert not regex.fullmatch("http://localhost:18102/links/42/stages")
    assert routes.arrival_regex("/files/*") == ""


def test_a_wildcard_route_is_one_no_url_comparison_can_use() -> None:
    assert not routes.is_comparable("/files/*")
    assert not routes.is_comparable("/files/report-{id}.pdf")
    assert not routes.is_comparable("the app root")
    assert routes.is_comparable("/links/:id/edit")
    assert routes.why_unreadable("/files/*").endswith("names a family of pages")
    assert routes.why_unreadable("/links/:id/edit") == ""


def test_is_screen_name_shaped_accepts_a_navigator_identifier_and_rejects_a_path_or_url() -> None:
    """The mobile counterpart of `is_path_shaped`: a bare identifier, never a path or a URL."""
    assert routes.is_screen_name_shaped("WidgetList")
    assert routes.is_screen_name_shaped("NewWidget")
    assert routes.is_screen_name_shaped("_private")
    assert not routes.is_screen_name_shaped("/")
    assert not routes.is_screen_name_shaped("/new")
    assert not routes.is_screen_name_shaped("https://x/y")
    assert not routes.is_screen_name_shaped("Widget-List")
    assert not routes.is_screen_name_shaped("")


def test_is_never_routed_always_says_no() -> None:
    """The `iac`/`cli`/`artifact`/`none` predicate: there is no value it is ever meant to read, so every value — including one shaped like a real path or screen name — is rejected honestly rather than let through by accident."""
    assert not routes.is_never_routed("/dashboard")
    assert not routes.is_never_routed("WidgetList")
    assert not routes.is_never_routed("")


def test_route_grammar_and_path_addressedness_per_driver() -> None:
    """`route_grammar` picks a driver's predicate; `is_path_addressed` states, per driver, whether that predicate is being asked to answer a path question at all — the two are read off `ROUTE_GRAMMAR`'s own columns, not inferred from each other."""
    web_predicate, web_reason = routes.route_grammar("web")
    assert web_predicate is routes.is_path_shaped
    assert web_reason == routes.NOT_PATH_SHAPED_REASON
    assert routes.is_path_addressed("web")

    http_predicate, _http_reason = routes.route_grammar("http")
    assert http_predicate is routes.is_path_shaped
    assert routes.is_path_addressed("http")

    mobile_predicate, mobile_reason = routes.route_grammar("mobile")
    assert mobile_predicate is routes.is_screen_name_shaped
    assert mobile_reason == routes.NOT_SCREEN_NAME_SHAPED_REASON
    assert not routes.is_path_addressed("mobile")

    iac_predicate, iac_reason = routes.route_grammar("iac")
    assert iac_predicate is routes.is_never_routed
    assert iac_reason == routes.NOT_ROUTED_REASON
    assert not routes.is_path_addressed("iac")

    cli_predicate, cli_reason = routes.route_grammar("cli")
    assert cli_predicate is routes.is_never_routed
    assert cli_reason == routes.NOT_ROUTED_REASON
    assert not routes.is_path_addressed("cli")

    artifact_predicate, artifact_reason = routes.route_grammar("artifact")
    assert artifact_predicate is routes.is_never_routed
    assert artifact_reason == routes.NOT_ROUTED_REASON
    assert not routes.is_path_addressed("artifact")

    driverless_predicate, driverless_reason = routes.route_grammar("none")
    assert driverless_predicate is routes.is_never_routed
    assert driverless_reason == routes.NOT_ROUTED_REASON
    assert not routes.is_path_addressed("none")

    unknown_predicate, _unknown_reason = routes.route_grammar("some-unrecognized-driver")
    assert unknown_predicate is routes.is_path_shaped
    assert routes.is_path_addressed("some-unrecognized-driver")

    none_predicate, _none_reason = routes.route_grammar(None)
    assert none_predicate is routes.is_path_shaped
    assert routes.is_path_addressed(None)


def test_a_segment_ending_in_a_question_mark_may_be_absent() -> None:
    route = "/sheets/:id/properties/categories?/:categoryId?"
    assert routes.arrived_at("http://localhost:18102/sheets/2/properties", route)
    assert routes.arrived_at("http://localhost:18102/sheets/2/properties/categories/41", route)
    assert not routes.arrived_at("http://localhost:18102/sheets/2", route)
    assert not routes.arrived_at("http://localhost:18102/sheets/2/properties/other/41", route)
    assert routes.literal_route(route) == ""
