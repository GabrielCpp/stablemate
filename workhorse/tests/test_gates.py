"""The one reader of the `STATUS:` / `SCOPE:` header on a gate file.

These used to be five hand-copied regexes on both sides of the same file — the workflow
writes the header, groom's UI reads and rewrites it — so the cases below are the ones a
divergence would have silently broken: a hand-edited tab, a lower-cased status, a follow-up
block that quotes an earlier `STATUS:` in prose.

Run: ./.venv/bin/python tests/test_gates.py   (or via pytest)
"""
from __future__ import annotations

from workhorse import gates


def test_status_and_scope_are_read_off_their_own_lines():
    text = "STATUS: AWAITING_OPERATOR\nSCOPE: epic\n\n## Questions\n"
    assert gates.status_of(text) == "AWAITING_OPERATOR"
    assert gates.scope_of(text) == "epic"


def test_absent_is_its_own_answer_not_a_state():
    """A file with no header is in no state, and each caller decides what that means."""
    assert gates.status_of("just some notes\n") == ""
    assert gates.scope_of("just some notes\n") == ""


def test_a_hand_edited_tab_after_the_colon_still_reads():
    """These files are edited by humans in whatever editor is open."""
    assert gates.status_of("STATUS:\tANSWERED\n") == "ANSWERED"
    assert gates.scope_of("SCOPE:\tEPIC\n") == "epic"


def test_case_is_normalised_in_both_directions():
    """The writer's spelling must not decide whether the gate opens."""
    assert gates.status_of("STATUS: answered\n") == "ANSWERED"
    assert gates.scope_of("SCOPE: Epic\n") == "epic"


def test_a_status_that_is_not_at_the_start_of_a_line_is_prose():
    assert gates.status_of("the file said STATUS: ANSWERED at the time\n") == ""


def test_set_status_rewrites_only_the_first_line():
    """A re-block quotes the previous round; flipping the quote too would loop the gate.

    The file accretes: the workflow appends a fresh `## Questions` block under the history of
    the last one. Only the live header at the top is the state.
    """
    text = "STATUS: ANSWERED\nSCOPE: story\n\nEarlier we wrote:\n\n> STATUS: ANSWERED\n"
    out = gates.set_status(text, "CONSUMED")
    assert out.splitlines()[0] == "STATUS: CONSUMED"
    assert out.endswith("> STATUS: ANSWERED\n")
    assert gates.status_of(out) == "CONSUMED"


def test_set_status_prepends_a_header_when_the_file_has_none():
    """A note dropped by hand without the marker still gets consumed exactly once."""
    assert gates.set_status("please redo the login story\n", "CONSUMED") == (
        "STATUS: CONSUMED\n\nplease redo the login story\n"
    )


def test_set_status_leaves_everything_else_byte_for_byte():
    text = "STATUS: NEW\nSCOPE: epic\n\nbody line\n"
    assert gates.set_status(text, "CONSUMED") == "STATUS: CONSUMED\nSCOPE: epic\n\nbody line\n"


def test_read_after_write_round_trips():
    """The property the five copies could not guarantee between them."""
    for text in ("STATUS: NEW\n\nnote\n", "note with no header\n", "STATUS:\tnew\nSCOPE: epic\n"):
        assert gates.status_of(gates.set_status(text, "CONSUMED")) == "CONSUMED"


def test_plain_questions_format_as_a_discoverable_operator_gate():
    text = gates.format_operator_gate("which branch?")

    assert text == (
        "STATUS: AWAITING_OPERATOR\n\n"
        "## Questions from the agent\n\n"
        "which branch?\n"
    )
    assert gates.status_of(text) == "AWAITING_OPERATOR"


def test_structured_operator_gate_is_rearmed_without_double_wrapping():
    text = (
        "STATUS: ANSWERED\nSCOPE: story\n\n"
        "## Questions from the agent\n\nWhich behavior?\n"
    )

    formatted = gates.format_operator_gate(text)

    assert formatted.splitlines()[0] == "STATUS: AWAITING_OPERATOR"
    assert formatted.count("## Questions from the agent") == 1
    assert "SCOPE: story" in formatted


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
