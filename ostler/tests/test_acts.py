"""The `arrange:` act vocabulary: what a performer can be told to do, and what is refused."""

from __future__ import annotations

from ostler import acts, checks, registry


def test_positional_and_keyword_arguments_bind_to_the_declared_params() -> None:
    call = acts.parse_act('fill("#name-field", value="Widget A")')
    assert isinstance(call, acts.ActCall)
    assert call.name == "fill"
    assert call.args == {"locator": "#name-field", "value": "Widget A"}


def test_text_is_identity_not_display() -> None:
    """Two spellings of one act render one string, so a compiled plan and the bullet it came
    from compare on substance rather than on argument order."""
    one = acts.parse_act('fill(value="A", locator="#name-field")')
    two = acts.parse_act('fill("#name-field",   "A")')
    assert isinstance(one, acts.ActCall) and isinstance(two, acts.ActCall)
    assert one.text() == two.text() == 'fill(locator="#name-field", value="A")'


def test_a_soft_wrapped_bullet_parses_as_markdown_renders_it() -> None:
    call = acts.parse_act('fill(locator="#note",\n  value="a long typed note")')
    assert isinstance(call, acts.ActCall)
    assert call.text() == 'fill(locator="#note", value="a long typed note")'


def test_a_bare_name_is_a_fixture_relocated_rather_than_a_malformed_act() -> None:
    """`fixture:` was the only arrangement key for a long time, so its habit is the likeliest
    mistake — and it is not a mistake in the value, only in the key above it."""
    refused = acts.parse_act("widgets-on-hand")
    assert isinstance(refused, checks.Refusal)
    assert refused.kind == "misfiled-fixture"
    assert refused.relocates_to == "fixture"
    assert refused.bullet("arrange") == "- fixture: widgets-on-hand"


def test_an_unknown_name_gets_the_act_vocabulary_not_the_check_vocabulary() -> None:
    """The two keys share a call grammar and not a vocabulary: `visible` is a check and
    nothing at all here, and handing back the wrong list sends the author to write one."""
    refused = acts.parse_act('visible(locator="#x")')
    assert isinstance(refused, checks.Refusal)
    assert refused.kind == "unknown-act"
    assert "click, fill, press, select" in refused.message
    assert refused.form == acts.vocabulary()


def test_a_missing_required_argument_is_refused_with_that_act_s_signature() -> None:
    refused = acts.parse_act('fill(locator="#name-field")')
    assert isinstance(refused, checks.Refusal)
    assert refused.kind == "bad-arguments"
    assert refused.form == acts.ACT_BY_NAME["fill"].signature()


def test_a_non_string_argument_is_refused_because_a_performer_types_strings() -> None:
    """`value=3` states a value no driver can deliver without inventing a rendering for it:
    the user types "3", and the book is the place that says so."""
    refused = acts.parse_act('fill(locator="#quantity", value=3)')
    assert isinstance(refused, checks.Refusal)
    assert "is str, got int" in refused.message


def test_an_unparseable_expression_is_not_a_call() -> None:
    refused = acts.parse_act("fill(locator=")
    assert isinstance(refused, checks.Refusal)
    assert refused.kind == "not-a-call"


def test_bind_and_parse_agree_so_a_plan_compares_to_the_bullet_it_came_from() -> None:
    parsed = acts.parse_act('press(locator="#search", key="Enter")')
    bound = acts.bind("press", {"locator": "#search", "key": "Enter"})
    assert isinstance(parsed, acts.ActCall) and isinstance(bound, acts.ActCall)
    assert parsed.text() == bound.text()


def test_every_act_declares_at_least_one_driver_that_can_perform_it() -> None:
    """Performability is a relation between what the act needs and what a driver supplies —
    an act no driver can perform is a name the book can write and no target can honour."""
    vocabulary = {"web", "mobile", "http", "cli", "artifact", "iac", "none"}
    for spec in acts.ACTS:
        assert spec.drivers, spec.name
        assert set(spec.drivers) <= vocabulary, spec.name
        assert spec.establishes and spec.establishes[0].islower(), spec.name


def test_every_act_names_the_control_it_operates_by_a_locator() -> None:
    """An act with no locator would operate whatever the driver last touched, which is not a
    statement the book can make about a control."""
    for spec in acts.ACTS:
        assert any(p.locator and p.required for p in spec.params), spec.name


def test_the_act_key_is_an_arrangement_the_binding_sees_but_not_a_fixture_name() -> None:
    """The two halves of `arrange_keys`: everything that binds an arrangement to a claim reads
    both, and only the checkers that resolve a fixture *name* read `fixture_keys`."""
    assert registry.performed_keys("interaction") == ("arrange",)
    assert registry.fixture_keys("interaction") == ("fixture",)
    assert set(registry.arrange_keys("interaction")) == {"fixture", "arrange"}
    assert "arrange" in registry.attached_keys("interaction")
    assert "arrange" in registry.LOAD_BEARING_KEYS
