"""What an app's own server hands a page: the decoding of the data it serves, the routes a path is on, and the form action an answer matches."""

from __future__ import annotations

import json

import pytest

from ostler.book import BookError, action
from ostler.book.pagedata import decode, on_route

SHARED = [{"when": 1, "tags": 2, "by": 5, "gone": -1, "first": 8, "second": 8, "big": 10, "nan": -3, "inf": -4,
           "neg": -6, "re": 11, "plain": 12}, ["Date", "2026-11-04T10:00:00.000Z"], ["Set", 3, 4], "a", "b",
          ["Map", 6, 7], "x", 1, {"name": 9}, "bo", ["BigInt", "12"], ["RegExp", "ab+c", "gi"], [7, -1, 13], 3]



def _answer(*nodes: object) -> str:
    return json.dumps({"type": "data", "nodes": list(nodes)}) + "\n"


def _data(flat: list) -> dict:
    return {"type": "data", "data": flat, "uses": {}}


def test_a_page_s_data_decodes_dates_sets_maps_undefined_and_a_value_referenced_twice():
    got = decode(_answer(None, _data(SHARED)))
    assert got["when"] == "2026-11-04T10:00:00.000Z"
    assert got["tags"] == ["a", "b"]
    assert got["by"] == {"x": 1}
    assert got["gone"] is None
    assert got["first"] == {"name": "bo"}
    assert got["first"] is got["second"]
    assert got["big"] == 12
    assert got["re"] == "ab+c"
    assert got["plain"] == [1, None, 3]
    assert got["nan"] != got["nan"]
    assert got["inf"] == float("inf")


def test_layout_and_page_data_merge_with_the_page_winning():
    layout = _data([{"users": 1, "title": 4}, [2], {"name": 3}, "bo", "layout"])
    page = _data([{"title": 1}, "page"])
    assert decode(_answer(layout, page)) == {"users": [{"name": "bo"}], "title": "page"}


def test_a_skipped_node_is_left_out_of_the_page_s_data():
    page = _data([{"title": 1}, "page"])
    assert decode(_answer({"type": "skip"}, page, None)) == {"title": "page"}


def test_an_error_node_is_refused_with_what_the_run_met():
    boom = {"type": "error", "error": {"message": "Internal Error"}, "status": 500}
    with pytest.raises(BookError, match="a load of the page failed: .*Internal Error"):
        decode(_answer(None, boom))


def test_a_streamed_answer_is_refused_with_what_the_run_met():
    streamed = _answer(None, _data([{"title": 1}, "page"])) + '{"type":"chunk","id":1,"data":"1"}\n'
    with pytest.raises(BookError, match="streamed its data in 2 lines"):
        decode(streamed)


def test_a_redirect_is_refused_with_where_it_led():
    with pytest.raises(BookError, match="redirected to '/login'"):
        decode(json.dumps({"type": "redirect", "location": "/login"}))


@pytest.mark.parametrize("route, path, on", [
    ("/", "/", True), ("/assign", "/assign", True), ("/assign", "/", False), ("/tickets/[id]", "/tickets/7", True),
    ("/tickets/[id]", "/tickets", False), ("/(app)/tickets", "/tickets", True), ("/docs/[...rest]", "/docs/a/b", True),
])
def test_a_path_is_on_a_route_the_way_sveltekit_spells_it(route: str, path: str, on: bool):
    assert on_route(route, path) is on


def test_a_path_with_more_segments_than_its_route_is_not_on_it():
    assert not on_route("/assign", "/assign/extra")


def test_a_path_with_a_suffix_after_its_route_is_not_on_it():
    assert not on_route("/assign", "/assignment")


def test_a_route_parameter_takes_exactly_one_segment():
    assert on_route("/tickets/[id]", "/tickets/7")
    assert not on_route("/tickets/[id]", "/tickets/7/edit")


def test_a_rest_parameter_takes_no_segment_as_well_as_several():
    assert on_route("/docs/[...rest]", "/docs")
    assert on_route("/docs/[...rest]", "/docs/a")
    assert on_route("/docs/[...rest]", "/docs/a/b")


def test_a_trailing_slash_leaves_a_path_on_its_route():
    assert on_route("/assign", "/assign/")
    assert on_route("/tickets/[id]", "/tickets/7/")


class _Request:
    def __init__(self, method: str, url: str):
        self.method = method
        self.url = url


class _Response:
    def __init__(self, method: str, url: str):
        self.request = _Request(method, url)


def test_a_form_action_matches_the_post_to_its_page_that_names_it():
    assert action("/", "add")(_Response("POST", "http://app.test/?/add"))
    assert action("/tickets/[id]", "close")(_Response("POST", "http://app.test/tickets/7?/close"))


def test_a_form_action_matches_no_get_to_the_same_page():
    assert not action("/", "add")(_Response("GET", "http://app.test/?/add"))


def test_a_form_action_matches_no_post_to_another_page():
    assert not action("/", "add")(_Response("POST", "http://app.test/other?/add"))


def test_a_form_action_matches_no_post_that_names_another_action():
    assert not action("/", "add")(_Response("POST", "http://app.test/?/remove"))


def test_a_form_action_matches_no_post_that_names_no_action():
    assert not action("/", "add")(_Response("POST", "http://app.test/"))
