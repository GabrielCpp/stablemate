"""The symbol front end — one grammar for the join and the grounding check.

The central case is `test_a_reexported_symbol_does_not_ground`: it is the bug this module was
extracted to fix. Grounding asked whether the symbol appeared as a *word* in the file, so a
facade module that re-exports a name kept a moved symbol's citation green — `doctor` was
blind to exactly the refactor §4.4 exists to catch.
"""
from __future__ import annotations

from ostler import inventory


# ── grounding must read declarations, not words ───────────────────────────────────────

FACADE = '''\
"""The install facade — the ``Renderer`` class lives in ``renderer``."""
from farrier.renderer import Renderer
from farrier.outputs import render_expected

__all__ = ["Renderer", "render_expected"]
'''

REAL = '''\
class Renderer:
    def render_templates(self) -> None: ...
'''


def test_a_reexported_symbol_does_not_ground():
    """The name is present in every sense but the one that matters: it is not declared here."""
    assert "Renderer" in FACADE  # the word is right there
    assert inventory.declares("install.py", FACADE, "Renderer") is False
    assert inventory.declares("install.py", FACADE, "render_expected") is False


def test_the_defining_module_grounds():
    assert inventory.declares("renderer.py", REAL, "Renderer") is True
    assert inventory.declares("renderer.py", REAL, "Renderer.render_templates") is True


def test_a_name_only_in_a_comment_does_not_ground():
    assert inventory.declares("x.py", "# Renderer does the thing\n", "Renderer") is False


def test_an_unreadable_language_grounds_anything():
    """Silence about a language is not evidence against a citation."""
    assert inventory.declares("x.rb", "class Renderer; end", "Renderer") is True


# ── grounding is wider than the inventory, on purpose ─────────────────────────────────

APP = '''\
LOG: deque[dict] = deque(maxlen=200)
REGISTRY = {}
_gate_locks: dict[str, Lock] = {}


def _run_run(args) -> int: ...


class Hub:
    async def send_reload(self) -> None: ...
'''


def test_grounding_admits_what_the_inventory_filters_out():
    """A book's notion of a unit is wider than the inventory's — and may be.

    Module constants, private symbols and methods are all real things to document for an
    application. The inventory narrows its denominator deliberately; grounding must not
    punish a book for citing outside it.
    """
    for symbol in ("LOG", "REGISTRY", "_gate_locks", "_run_run", "Hub.send_reload"):
        assert inventory.declares("state.py", APP, symbol) is True, symbol


def test_the_inventory_denominator_stays_narrow():
    """The other half of the same decision: none of those widen `symbols()`.

    Widening the denominator would change what "complete" means and make every existing book
    instantly less complete — so the split is load-bearing, not an accident.
    """
    assert inventory.symbols("state.py", APP) == ["Hub"]


def test_an_augmented_assignment_declares_nothing():
    assert inventory.declares("x.py", "count += 1\n", "count") is False


# ── Python is parsed, so the words in a string are not declarations ───────────────────

PARSED = '''\
"""A module whose docstring shows usage.

    def looks_declared(): ...
    class AlsoNot: ...
"""
# class Commented: ...

import functools


@functools.cache
def wrapped(
    first: str,
    second: int,
) -> str:
    """Wrapped across lines, and decorated."""
    local_binding = 1
    return first


class Outer:
    HEADER = "x"

    class Inner:
        @property
        def value(self) -> int: ...


FIRST, SECOND = 1, 2
'''


def test_a_declaration_shaped_line_inside_a_docstring_is_not_a_declaration():
    """The regex matched text; the parse matches code. `# class Commented` is gone too."""
    for name in ("looks_declared", "AlsoNot", "Commented"):
        assert inventory.declares("m.py", PARSED, name) is False, name


def test_a_wrapped_signature_declares_its_own_name():
    """`def wrapped(\\n first: str,` — the line regex read the continuation, not the def."""
    assert inventory.symbols("m.py", PARSED) == ["wrapped", "Outer"]


def test_nested_classes_decorated_methods_and_unpacked_constants_all_ground():
    for symbol in ("Outer.Inner", "Inner.value", "HEADER", "FIRST", "SECOND", "local_binding"):
        assert inventory.declares("m.py", PARSED, symbol) is True, symbol


def test_an_imported_name_still_does_not_ground():
    """The property the module exists for, restated against the parser."""
    assert inventory.declares("m.py", PARSED, "functools") is False


def test_a_file_that_does_not_parse_falls_back_to_the_regex():
    """A file mid-edit is not one we can be right about — approximating beats reporting nothing."""
    broken = "class Renderer:\n    def render(self ->\n"
    assert inventory.symbols("broken.py", broken) == ["Renderer"]
    assert inventory.declares("broken.py", broken, "Renderer.render") is True


# ── the languages ─────────────────────────────────────────────────────────────────────

GO = '''\
package main

type Stack[T any] struct{}

func (w *FirebaseClaimsWriter) SetRoleClaims(ctx context.Context) error { return nil }

func (v ValueRecv) Read() string { return "" }

func Map[T any](xs []T) []T { return xs }

func unexported() {}
'''


def test_go_methods_are_qualified_by_their_receiver():
    """Source order, and note `Stack` — a generic type declaration is a unit, not a blind spot."""
    assert inventory.symbols("x.go", GO) == [
        "Stack", "(*FirebaseClaimsWriter).SetRoleClaims", "ValueRecv.Read", "Map"]


def test_go_grounds_a_qualified_method_and_an_unexported_func():
    assert inventory.declares("x.go", GO, "(*FirebaseClaimsWriter).SetRoleClaims") is True
    assert inventory.declares("x.go", GO, "unexported") is True
    assert inventory.declares("x.go", GO, "NotHere") is False


GO_VALUES = '''\
package schema

type ElementName string

type Alias = ElementName

const (
	ElementPage ElementName = "page"
	ElementBody ElementName = "body"
	unexported  ElementName = "nope"
)

var InlineElements = []ElementName{ElementRef}

var ElementRules = map[ElementName]ElementRule{
	ElementPage: {RequiredAttributes: []string{"schema"}},
}

var (
	Grouped = 1
	Paired, Also = 2, 3
	Table = map[string]int{
		NotADeclaration: 1,
	}
)
'''


def test_go_resolves_package_level_values_and_named_types():
    """A Go table is where a closed vocabulary lives, and the book has to be able to cite it.

    `ElementRules` is the direct analog of a TypeScript `const` the TS scanner has always
    resolved, so a parity doc could ground the TS half and never the Go one — a correct
    citation that `doctor` reports as `missing-code-symbol` forever. `Alias` and
    `ElementName` come with it: only `struct`/`interface` used to count as a type.
    """
    assert inventory.symbols("schema.go", GO_VALUES) == [
        "ElementName", "Alias", "ElementPage", "ElementBody", "InlineElements",
        "ElementRules", "Grouped", "Paired", "Also", "Table"]


def test_a_composite_literal_inside_a_value_block_is_not_a_declaration():
    """Depth, not indentation. `NotADeclaration: 1` is a map key one level in, and reads
    exactly like a `var (…)` entry until you count braces."""
    declared = inventory.declared_names("schema.go", GO_VALUES)
    assert "NotADeclaration" not in declared, sorted(declared)
    assert {"unexported", "Grouped", "ElementRules"} <= declared, sorted(declared)


TS = '''\
export function exported() {}
function local() {}
export const Widget = 1;
'''


def test_ts_inventory_is_exports_only_but_grounding_is_not():
    assert inventory.symbols("x.ts", TS) == ["exported", "Widget"]
    assert inventory.declares("x.ts", TS, "local") is True
    assert inventory.declares("x.ts", TS, "missing") is False


PHP = '''\
<?php
class AddProjectAction
{
    public function getRenderPath() {}
    private function helper() {}
    public function __construct() {}
}
'''


def test_php_inventory_skips_private_and_magic_methods():
    assert inventory.symbols("x.php", PHP) == [
        "AddProjectAction", "AddProjectAction.getRenderPath"]


def test_php_grounds_a_private_method():
    assert inventory.declares("x.php", PHP, "AddProjectAction.helper") is True


TWIG = "{% block content %}hi{% endblock %}\n{%- block footer -%}f{%- endblock -%}"


def test_twig_blocks_are_the_secondary_unit():
    assert inventory.symbols("x.twig", TWIG) == ["content", "footer"]
