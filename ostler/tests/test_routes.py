"""What a `route:` bullet can and cannot be compared against."""

from __future__ import annotations

from ostler import routes


def test_a_parameterised_route_is_not_a_literal_to_compare_against() -> None:
    """A route with a parameter names a family of pages, in either of the book's spellings.

    Read as a literal, `/links/:id/edit` can never equal the URL of a page that is plainly
    the screen it documents, and every vet of a parameterised screen would stop its scenario
    for failing to arrive where it did arrive.
    """
    assert routes.literal_route("/links/:id/edit") == ""
    assert routes.literal_route("/links/{id}/edit") == ""
    assert routes.literal_route("/dashboard/") == "/dashboard"
    assert routes.literal_route("/") == "/"
    # Not a path at all — an absolute URL or prose says nothing a URL comparison can use.
    assert routes.literal_route("https://example.com/dashboard") == ""


def test_arrival_compares_paths_and_ignores_state_within_a_screen() -> None:
    assert routes.arrived_at("http://localhost:18102/dashboard?page=2#top", "/dashboard")
    assert routes.arrived_at("http://localhost:18102/", "/")
    assert not routes.arrived_at("http://localhost:18102/settings", "/dashboard")


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
    """The `iac`/`cli` predicate: there is no value it is ever meant to read, so every value —
    including one shaped like a real path or screen name — is rejected honestly rather than
    let through by accident."""
    assert not routes.is_never_routed("/dashboard")
    assert not routes.is_never_routed("WidgetList")
    assert not routes.is_never_routed("")


def test_route_grammar_and_path_addressedness_per_driver() -> None:
    """`route_grammar` picks a driver's predicate; `is_path_addressed` states, per driver,
    whether that predicate is being asked to answer a path question at all — the two are
    read off `ROUTE_GRAMMAR`'s own columns, not inferred from each other. Four rows cover three
    distinct situations (path-addressed, name-addressed, route-less), plus the fallback for a
    driver the table does not recognize at all."""
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

    # `iac` and `cli` are recognized rows that *state* they own no route — not path-addressed,
    # but for a different reason than `mobile`: no screen/endpoint node is ever theirs to check.
    iac_predicate, iac_reason = routes.route_grammar("iac")
    assert iac_predicate is routes.is_never_routed
    assert iac_reason == routes.NOT_ROUTED_REASON
    assert not routes.is_path_addressed("iac")

    cli_predicate, cli_reason = routes.route_grammar("cli")
    assert cli_predicate is routes.is_never_routed
    assert cli_reason == routes.NOT_ROUTED_REASON
    assert not routes.is_path_addressed("cli")

    # An unrecognized driver, and no driver declared at all (`None`), keep the same
    # `is_path_shaped` default this module always had — a fourth case, distinct from `iac`/`cli`:
    # those are recognized and route-less on purpose, this is simply undeclared.
    unknown_predicate, _unknown_reason = routes.route_grammar("some-unrecognized-driver")
    assert unknown_predicate is routes.is_path_shaped
    assert routes.is_path_addressed("some-unrecognized-driver")

    none_predicate, _none_reason = routes.route_grammar(None)
    assert none_predicate is routes.is_path_shaped
    assert routes.is_path_addressed(None)
