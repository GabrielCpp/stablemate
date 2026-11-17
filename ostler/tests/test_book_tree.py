"""An object that holds itself: a tree is one object, and every walker of a shape ends on it."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from ostler.book import Answer, BookError, Endpoint, Field, Id, Itself, List, Map, Object, Str
from ostler.book.check import check, itself_faults
from ostler.book.http import (Identities, Witness, _id_values, apart, bare_ids, blind, breaches, canonical, declared_paths, named_shapes,
                              opaque_fields, real_paths, states)
from ostler.book.rpc import proto_named
from ostler.book.witness import report

from test_book_web import _service

EXPRESSION = Object(
    "BundleExpression",
    kind=Field(Str()),
    value=Field(Str(), required=False),
    operand=Field(Itself("BundleExpression"), required=False),
    left=Field(Itself("BundleExpression"), required=False),
    right=Field(Itself("BundleExpression"), required=False),
)
FORMULA = Object("Formula", ast=Field(EXPRESSION))


class Evaluate(Endpoint):
    path = "/evaluate"
    answers = (Answer(200, FORMULA, "the formula as the app holds it"),)
    does = "Reads a formula."


def deep(levels: int) -> dict[str, Any]:
    node: dict[str, Any] = {"kind": "number", "value": "1"}
    for _ in range(levels):
        node = {"kind": "negate", "operand": node}
    return node


def test_a_tree_object_holds_itself():
    assert EXPRESSION.fields["left"].shape is EXPRESSION


@pytest.mark.parametrize("levels", [0, 4, 9])
def test_a_tree_checks_a_value_at_any_depth(levels: int):
    assert EXPRESSION.check(deep(levels)) == []


def test_a_tree_refuses_an_undeclared_key_deep_down_and_names_its_path():
    value = deep(3)
    value["operand"]["operand"]["operand"]["extra"] = 1
    assert EXPRESSION.check(value) == ["body.operand.operand.operand.extra: not declared"]


def test_a_tree_refuses_a_wrong_type_deep_down_and_names_its_path():
    value = deep(9)
    node = value
    for _ in range(8):
        node = node["operand"]
    node["operand"]["kind"] = 5
    [fault] = EXPRESSION.check(value)
    assert fault.startswith("body" + ".operand" * 9 + ".kind")


def test_a_tree_in_a_list_checks_every_level():
    node = Object("Node", name=Field(Str()), children=Field(List(Itself("Node"))))
    assert node.check({"name": "a", "children": [{"name": "b", "children": [{"name": "c", "children": []}]}]}) == []
    assert node.check({"name": "a", "children": [{"name": "b", "children": [{"name": 1, "children": []}]}]}) != []


def test_a_tree_in_a_map_checks_every_level():
    node = Object("Node", name=Field(Str()), kids=Field(Map(Itself("Node"))))
    assert node.check({"name": "a", "kids": {"x": {"name": "b", "kids": {}}}}) == []
    assert node.check({"name": "a", "kids": {"x": {"name": 2, "kids": {}}}}) != []


def test_a_tree_declares_each_field_once_and_returns():
    assert declared_paths(EXPRESSION) == ["kind", "value", "operand", "left", "right"]
    assert declared_paths(FORMULA) == ["ast", "ast.kind", "ast.value", "ast.operand", "ast.left", "ast.right"]


def test_a_sibling_that_reuses_a_shape_declares_it_in_both_places():
    both = Object("Both", one=Field(FORMULA), two=Field(FORMULA))
    paths = declared_paths(both)
    assert "one.ast.kind" in paths and "two.ast.kind" in paths


def test_the_real_paths_of_a_deep_value_fold_onto_the_declared_ones():
    value = {"ast": {"kind": "add", "left": deep(5), "right": {"kind": "number", "value": "2"}}}
    real = real_paths(FORMULA, value)
    assert real == {"ast", "ast.kind", "ast.left", "ast.right", "ast.operand", "ast.value"}
    assert real <= set(declared_paths(FORMULA))


def test_a_one_of_on_a_tree_holds_at_a_nested_level():
    either = Object("Either", a=Field(Str(), required=False), b=Field(Str(), required=False),
                    next=Field(Itself("Either"), required=False)).one_of("a", "b")
    assert either.fields["next"].shape is either
    assert either.check({"a": "x", "next": {"b": "y", "next": {"a": "z"}}}) == []
    assert either.check({"a": "x", "next": {"b": "y", "next": {"a": "z", "b": "w"}}}) == ["body.next.next: exactly one of a, b"]


def test_a_together_on_a_tree_holds_at_a_nested_level():
    pair = Object("Pair", a=Field(Str(), required=False), b=Field(Str(), required=False),
                  next=Field(Itself("Pair"), required=False)).together("a", "b")
    assert pair.check({"next": {"a": "x"}}) == ["body.next: a, b come together or not at all"]


def test_a_relation_copy_leaves_the_original_as_it_was():
    base = Object("Either", a=Field(Str(), required=False), b=Field(Str(), required=False),
                  next=Field(Itself("Either"), required=False))
    either = base.one_of("a", "b")
    assert base.fields["next"].shape is base
    assert base.check({"next": {}}) == []
    assert either is not base


def test_a_mutual_tree_resolves_and_checks():
    b = Object("B", back=Field(Itself("A"), required=False))
    a = Object("A", name=Field(Str()), bs=Field(List(b)))
    assert b.fields["back"].shape is a
    assert a.check({"name": "x", "bs": [{"back": {"name": "y", "bs": [{}]}}]}) == []
    assert a.check({"name": "x", "bs": [{"back": {"name": 3, "bs": []}}]}) != []


def test_a_mutual_tree_survives_a_relation_on_its_outer_object():
    b = Object("B", back=Field(Itself("A"), required=False))
    a = Object("A", x=Field(Str(), required=False), y=Field(Str(), required=False), bs=Field(List(b))).one_of("x", "y")
    assert a.check({"x": "1", "bs": [{"back": {"x": "1", "y": "2", "bs": []}}]}) == ["body.bs[0].back: exactly one of x, y"]
    assert b.fields["back"].shape is not a
    assert isinstance(a.fields["bs"].shape, List) and a.fields["bs"].shape.of is not b


def test_an_unresolved_itself_refuses_to_check_and_to_describe():
    stray = Object("Stray", next=Field(Itself("Other"), required=False))
    with pytest.raises(BookError, match=r"Itself\('Other'\) names no enclosing object 'Other'"):
        stray.check({"next": {}})
    with pytest.raises(BookError, match=r"Itself\('Other'\) names no enclosing object 'Other'"):
        Itself("Other").describe()


class Strays(Endpoint):
    path = "/strays"
    answers = (Answer(200, Object("Stray", next=Field(List(Itself("Other")), required=False)), "a stray"),)
    does = "Reads a stray."


def test_the_book_check_reports_an_unresolved_itself_with_its_endpoint_and_path():
    service = replace(_service(languages=("en",)), endpoints=(Strays,))
    [found] = itself_faults(service)
    assert found.name == "endpoint Strays"
    assert found.problem == "answer 200.next[]: Itself('Other') names no enclosing object 'Other'"
    assert found in check(service, "mini")


def test_a_book_of_trees_has_no_such_finding():
    service = replace(_service(languages=("en",)), endpoints=(Evaluate,))
    assert itself_faults(service) == []


def test_every_walker_of_the_shape_returns_on_a_tree():
    node = Object("Node", id=Field(Str(), opaque="made by the app"), children=Field(List(Itself("Node"))))
    assert [n for n in named_shapes((Evaluate,))] == ["Formula", "BundleExpression"]
    assert opaque_fields(node) == [("id", "made by the app")]
    assert states(node, lambda entries: []) is False
    assert bare_ids(node, "answer") == ["answer.id: looks like an identifier but is typed Str, not Id"]
    assert bare_ids(EXPRESSION, "answer") == []


def test_every_walker_of_the_data_returns_on_a_tree():
    value = {"ast": {"kind": "add", "left": deep(9), "right": deep(4)}}
    assert canonical(FORMULA, value, app=True, ids=Identities(), where="body")["ast"]["left"]["operand"]["kind"] == "negate"
    assert blind(FORMULA, value) == value
    assert breaches(FORMULA, value) == []
    assert apart(FORMULA, value, (lambda entries: [],)) == value
    assert proto_named(FORMULA, value) == value
    assert FORMULA.pack(value) == value


def test_the_id_values_of_a_tree_are_each_judged():
    class Thing:
        pass

    leaf = Object("Leaf", id=Field(Id(Thing, Str())), next=Field(Itself("Leaf"), required=False))
    out: list = []
    _id_values(leaf, {"id": "a", "next": {"id": "b", "next": {"id": "c"}}}, "body", out)
    assert [where for where, _, _ in out] == ["body.id", "body.next.id", "body.next.next.id"]


def test_a_witness_report_counts_each_field_of_a_tree_once():
    seen = Witness()
    seen.see(Evaluate, Evaluate.answers[0], {"ast": {"kind": "add", "left": deep(6), "right": deep(2)}})
    counted = report([Evaluate], seen)
    assert (counted.fields_seen, counted.fields_total) == (6, 6)
    assert counted.gaps == []


def test_a_witness_report_names_the_field_of_a_tree_no_level_held():
    seen = Witness()
    seen.see(Evaluate, Evaluate.answers[0], {"ast": {"kind": "add", "left": {"kind": "number", "value": "1"}}})
    counted = report([Evaluate], seen)
    assert (counted.fields_seen, counted.fields_total) == (4, 6)
    [gap] = counted.gaps
    assert gap.fields == {200: ["ast.operand", "ast.right"]}
