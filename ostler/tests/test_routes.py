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
