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

import pytest

from ostler import refs


def test_one_bullet_may_cite_several_targets():
    """The case that was silently owning nothing: two backticked refs in one bullet."""
    value = "`docs-app/react-router.config.ts`, `docs-app/package.json`"
    assert refs.code_refs(value) == [
        "docs-app/react-router.config.ts", "docs-app/package.json",
    ]


def test_a_bullet_wrapped_across_lines_still_cites_both():
    """Found by diffing `ostler doctor` over a real book before and after this pass.

    Two refs do not fit on one line at the width books are written to, so the second lands on
    a continuation line. The parser hands that newline back as a `softbreak` token rather
    than as text, and reading only `text` for the separator ended the run there — dropping
    the second target, and with it a genuinely ungrounded symbol the book had been reporting.
    """
    value = "`report/services/render.go::buildHTML`,\n`report/services/render.go::tmpl`"
    assert refs.code_refs(value) == [
        "report/services/render.go::buildHTML", "report/services/render.go::tmpl",
    ]


def test_prose_on_a_continuation_line_still_ends_the_run():
    """The line break is whitespace, not an exemption: what follows it is judged as before."""
    value = "`api/a.py`,\n`api/b.py`\nread by the `save` handler"
    assert refs.code_refs(value) == ["api/a.py", "api/b.py"]


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


def test_parse_legacy_ref_has_no_repository_and_normalizes_its_path():
    assert refs.parse_code_ref(r"api\handlers.py::serve") == refs.CodeRef(
        repository="",
        path="api/handlers.py",
        symbol="serve",
    )


def test_parse_qualified_ref_preserves_its_symbol():
    assert refs.parse_code_ref(
        r'repo://acme/api\handlers.py::describe("a::b") > serves',
    ) == refs.CodeRef(
        repository="acme",
        path="api/handlers.py",
        symbol='describe("a::b") > serves',
    )


def test_qualified_refs_keep_the_same_path_distinct_between_repositories():
    value = "`repo://acme/src/main.py::run`, `repo://globex/src/main.py::run`"
    assert refs.code_refs(value) == [
        "repo://acme/src/main.py::run",
        "repo://globex/src/main.py::run",
    ]


def test_qualified_duplicates_collapse_in_first_seen_order():
    value = (
        "`repo://globex/src/b.py`, `repo://acme/src/a.py`, "
        "`repo://globex/src/b.py`"
    )
    assert refs.code_refs(value) == [
        "repo://globex/src/b.py",
        "repo://acme/src/a.py",
    ]


@pytest.mark.parametrize(
    "value",
    [
        "repo:///src/main.py::run",
        "repo://acme/::run",
        "repo://acme",
    ],
)
def test_explicit_parse_rejects_malformed_qualified_refs(value: str):
    with pytest.raises(ValueError, match="repository-qualified code ref"):
        refs.parse_code_ref(value)


def test_tolerant_bullet_extraction_keeps_malformed_qualified_refs():
    value = "`repo://acme/::run`, `repo://acme/src/main.py::run`"
    assert refs.code_refs(value) == [
        "repo://acme/::run",
        "repo://acme/src/main.py::run",
    ]


@pytest.mark.parametrize(
    "value",
    [
        "api/handlers.py",
        "api/handlers.py::serve",
        "repo://acme/api/handlers.py",
        'repo://acme/api/handlers.py::describe("a::b") > serves',
    ],
)
def test_render_roundtrips_parsed_refs(value: str):
    assert refs.render_code_ref(refs.parse_code_ref(value)) == value


def test_ref_path_returns_only_the_qualified_path_portion():
    assert refs.ref_path("repo://acme/api/handlers.py::serve") == "api/handlers.py"

