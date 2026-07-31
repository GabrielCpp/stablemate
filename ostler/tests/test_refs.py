"""`ostler.refs` — the `code:` bullet's grammar, which three readers share.

The bug these pin was silent by construction. A bullet citing two files —

    - code: `docs-app/react-router.config.ts`, `docs-app/package.json`

— was read as *one* ref by stripping decoration off the ends of the whole string, yielding a
path with a backtick-comma-backtick in the middle: a ref matching no file, so the node owned
**neither** of the files it cited. Nothing downstream can tell "cites nothing" from "cites
something unparseable", so `qa context` simply reported the changed file as `unmapped-change`
and the node documenting it went unfound.
"""

from __future__ import annotations

from ostler import refs


def test_one_bullet_may_cite_several_targets():
    """The case that was silently owning nothing: two backticked refs in one bullet."""
    value = "`docs-app/react-router.config.ts`, `docs-app/package.json`"
    assert refs.code_refs(value) == [
        "docs-app/react-router.config.ts", "docs-app/package.json",
    ]


def test_a_trailing_gloss_is_dropped_not_glued_on():
    """Prose after a ref is prose — a single-ref case that was mangled too."""
    value = "`web/app/components/navbar/Navbar.tsx::Navbar` (inline JSX, not a named export)"
    assert refs.code_refs(value) == ["web/app/components/navbar/Navbar.tsx::Navbar"]


def test_inline_code_inside_a_gloss_is_not_a_ref():
    """A gloss backticks its own identifiers; reading those as refs invents citations.

    The books this shipped against carry dozens of these, and each invented ref resolves to
    nothing — so an over-eager parse trades a silent miss for a loud false `dangling-code-ref`.
    """
    value = (
        "`legacy/src/Controller/EntityEditorController.php::tableViews` — the `tableViews` "
        "const, read by the `save` handler"
    )
    assert refs.code_refs(value) == [
        "legacy/src/Controller/EntityEditorController.php::tableViews",
    ]


def test_prose_before_the_first_span_falls_back_to_the_whole_value():
    """The run must lead: opening with prose is not the grammar, so the comma fallback applies.

    The value comes back whole — unchanged from what this replaced, and loud rather than
    silent: a malformed bullet surfaces as a ref that resolves to nothing, which is what it is.
    """
    assert refs.code_refs("see `api/a.py` for the handler") == [
        "see `api/a.py` for the handler",
    ]


def test_a_plain_single_ref_is_unchanged():
    assert refs.code_refs("`api/handlers.py::serve`") == ["api/handlers.py::serve"]
    assert refs.code_refs("api/handlers.py::serve") == ["api/handlers.py::serve"]


def test_without_backticks_commas_delimit():
    """No inline code anywhere means no backtick delimiter, so fall back to commas."""
    assert refs.code_refs("api/a.py, api/b.py") == ["api/a.py", "api/b.py"]


def test_a_repeated_key_arrives_as_a_list():
    assert refs.code_refs(["`api/a.py`", "`api/b.py`, `api/c.py`"]) == [
        "api/a.py", "api/b.py", "api/c.py",
    ]


def test_duplicates_collapse_in_first_seen_order():
    assert refs.code_refs("`api/b.py`, `api/a.py`, `api/b.py`") == ["api/b.py", "api/a.py"]


def test_an_absent_or_empty_bullet_cites_nothing():
    """Never invent a ref: a caller cannot distinguish "cited nothing" from "unreadable"."""
    assert refs.code_refs(None) == []
    assert refs.code_refs("") == []
    assert refs.code_refs([]) == []
    assert refs.code_refs("``") == []
    assert refs.code_refs("  ,  ") == []


def test_ref_path_splits_the_symbol_off():
    assert refs.ref_path("api/handlers.py::serve") == "api/handlers.py"
    assert refs.ref_path("api/handlers.py") == "api/handlers.py"


def test_normalize_ref_strips_a_single_targets_decoration():
    assert refs.normalize_ref(" `api/a.py`, ") == "api/a.py"
