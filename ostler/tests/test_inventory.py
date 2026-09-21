"""The symbol front end — one grammar for the join and the grounding check."""
from __future__ import annotations

from ostler import inventory, syntax



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
    assert "Renderer" in FACADE
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



APP = '''\
LOG: deque[dict] = deque(maxlen=200)
REGISTRY = {}
_gate_locks: dict[str, Lock] = {}


def _run_run(args) -> int: ...


class Hub:
    async def send_reload(self) -> None: ...
'''


def test_grounding_admits_what_the_inventory_filters_out():
    """A book's notion of a unit is wider than the inventory's — and may be."""
    for symbol in ("LOG", "REGISTRY", "_gate_locks", "_run_run", "Hub.send_reload"):
        assert inventory.declares("state.py", APP, symbol) is True, symbol


def test_the_inventory_denominator_stays_narrow():
    """The other half of the same decision: none of those widen `symbols()`."""
    assert inventory.symbols("state.py", APP) == ["Hub"]


def test_an_augmented_assignment_declares_nothing():
    assert inventory.declares("x.py", "count += 1\n", "count") is False



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
    """The regex matched text; the parse matches code."""
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


def test_a_file_that_does_not_parse_is_recovered_not_abandoned():
    """A file mid-edit is not one we can be right about — approximating beats reporting nothing."""
    broken = "class Renderer:\n    def render(self ->\n"
    assert inventory.symbols("broken.py", broken) == ["Renderer"]
    assert inventory.declares("broken.py", broken, "Renderer.render") is True


def test_a_broken_region_grounds_only_what_it_mentions():
    """Fail-open is scoped to the unreadable region, not widened to the whole file."""
    broken = "class Renderer:\n    def render(self ->\n"
    assert inventory.declares("broken.py", broken, "Absent") is False



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
    """A Go table is where a closed vocabulary lives, and the book has to be able to cite it."""
    assert inventory.symbols("schema.go", GO_VALUES) == [
        "ElementName", "Alias", "ElementPage", "ElementBody", "InlineElements",
        "ElementRules", "Grouped", "Paired", "Also", "Table"]


def test_a_composite_literal_inside_a_value_block_is_not_a_declaration():
    """Depth, not indentation."""
    declared = inventory.declared_names("schema.go", GO_VALUES)
    assert "NotADeclaration" not in declared, sorted(declared)
    assert {"unexported", "Grouped", "ElementRules"} <= declared, sorted(declared)


GO_MEMBERS = '''\
package mocks

type MockProjectReader struct {
	mock.Mock
	name string
	Ptr  *retry.Policy
	Box  generics.Box[int]
}

type Reader interface {
	Read(p []byte) (int, error)
	io.Closer
}
'''


def test_go_struct_fields_and_interface_methods_ground():
    """A field citation is a correct citation — the Python scanner has always agreed."""
    for symbol in ("MockProjectReader.Mock", "MockProjectReader.name",
                   "Reader.Read", "Reader.Closer"):
        assert inventory.declares("mocks.go", GO_MEMBERS, symbol) is True, symbol
    assert inventory.declares("mocks.go", GO_MEMBERS, "MockProjectReader.Absent") is False


def test_go_members_stay_out_of_the_inventory():
    """The other half of the decision: members ground citations, they are not units."""
    assert inventory.symbols("mocks.go", GO_MEMBERS) == ["MockProjectReader", "Reader"]


TS = '''\
export function exported() {}
function local() {}
export const Widget = 1;
'''


def test_ts_inventory_is_exports_only_but_grounding_is_not():
    assert inventory.symbols("x.ts", TS) == ["exported", "Widget"]
    assert inventory.declares("x.ts", TS, "local") is True
    assert inventory.declares("x.ts", TS, "missing") is False


TS_SHAPES = '''\
export abstract class Widget {}
export const { alpha, beta: renamed } = config;
export const [first] = tuple;
export default function main() {}
class Panel {
  render() {}
  title = "x";
}
export { Reexported } from './elsewhere';
import { Imported } from './other';
'''


def test_ts_reads_the_shapes_the_pattern_could_not_spell():
    """`abstract` and a destructuring `const` are ordinary exports, and a regex alternation listing keywords saw neither — so a correct citation to `Widget` reported `missing-code-symbol` with no edit that could clear it."""
    assert inventory.symbols("x.ts", TS_SHAPES) == [
        "Widget", "alpha", "renamed", "first", "main"]


def test_ts_class_members_ground_but_do_not_widen_the_denominator():
    for symbol in ("Panel.render", "Panel.title"):
        assert inventory.declares("x.ts", TS_SHAPES, symbol) is True, symbol
    assert "render" not in inventory.symbols("x.ts", TS_SHAPES)


def test_a_reexported_or_imported_ts_name_does_not_ground():
    """The facade property, restated for TypeScript: the word is there, the declaration is not."""
    assert inventory.declares("x.ts", TS_SHAPES, "Reexported") is False
    assert inventory.declares("x.ts", TS_SHAPES, "Imported") is False


TS_UNREAL = '''\
/*
export function ghost() {}
*/
const template = `
function phantom() {}
`;
'''


def test_a_declaration_inside_a_comment_or_a_string_is_not_one():
    """The regex counted `ghost` as a *unit the book owed coverage for* — a commented-out export made an otherwise complete book incomplete, and `phantom` grounded a citation to a function that exists only inside a template literal."""
    assert inventory.symbols("x.ts", TS_UNREAL) == []
    assert inventory.declares("x.ts", TS_UNREAL, "ghost") is False
    assert inventory.declares("x.ts", TS_UNREAL, "phantom") is False


def test_a_go_declaration_inside_a_comment_is_not_one():
    source = "package p\n\n// func Commented() {}\n\nfunc Real() {}\n"
    assert inventory.symbols("x.go", source) == ["Real"]
    assert inventory.declares("x.go", source, "Commented") is False


GO_TYPE_GROUP = '''\
package schema

type (
	Alpha struct{}
	Beta  interface{}
)
'''


def test_go_grouped_types_are_declarations():
    """A parenthesized `type (…)` group was the one Go shape the scan left out — the entries look exactly like a struct's fields to a line matcher, and nothing but a parse tells them apart."""
    assert inventory.symbols("schema.go", GO_TYPE_GROUP) == ["Alpha", "Beta"]
    assert inventory.declares("schema.go", GO_TYPE_GROUP, "Alpha") is True


def test_a_go_function_local_value_is_not_a_package_symbol():
    source = "package p\n\nfunc F() {\n\tlocal := 1\n\tvar other = 2\n}\n"
    assert inventory.declares("x.go", source, "local") is False
    assert inventory.declares("x.go", source, "other") is False


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


PHP_AFTER_CLASS = '''\
<?php
class Holder
{
    public function method() {}
}

function standalone() {}
'''


def test_a_php_function_after_a_class_is_not_a_method_of_it():
    """Qualification follows the tree, not the last `class` seen above the match — a flat source-order scan attributed every later function to a class it never sat in."""
    assert inventory.symbols("x.php", PHP_AFTER_CLASS) == [
        "Holder", "Holder.method", "standalone"]


TWIG = "{% block content %}hi{% endblock %}\n{%- block footer -%}f{%- endblock -%}"


def test_twig_blocks_are_the_secondary_unit():
    assert inventory.symbols("x.twig", TWIG) == ["content", "footer"]


def test_a_twig_block_inside_a_comment_is_not_a_unit():
    assert inventory.symbols("x.twig", "{# {% block removed %} #}\n") == []



EXTENTS_GO = '''\
package p

func First() {
	// a comment inside the body
	x := 1
	_ = x
}

func Second() {}
'''


def test_a_hunk_inside_a_body_belongs_to_that_declaration():
    assert inventory.extents("x.go", EXTENTS_GO) == [(3, 7, "First"), (9, 9, "Second")]


def test_extents_are_empty_for_a_language_no_front_end_reads():
    """Distinguishable by the caller from a file that genuinely declares nothing."""
    assert inventory.extents("x.rb", "class Renderer; end\n") == []


EXTENTS_TSX = '''\
export function Panel({ rows }: PanelProps) {
  const [open, setOpen] = useState(false)
  const status = rows.length ? "some" : "none"
  useEffect(() => {
    const el = document.getElementById("panel")
    el?.focus()
  }, [])
  return <div>{status}</div>
}

const Badge = ({ tone }: BadgeProps) => <span className={tone} />
'''


def test_a_typescript_local_is_named_for_the_declaration_that_encloses_it():
    """The extent of a component is not replaced by the extents of its locals."""
    found = inventory.extents("x.tsx", EXTENTS_TSX)
    assert (1, 9, "Panel") in found
    assert ("Panel.open", "Panel.setOpen", "Panel.status", "Panel.el") == tuple(
        name for _, _, name in found if name.startswith("Panel.")
    )
    assert (11, 11, "Badge") in found


def test_a_typescript_method_is_named_for_its_class():
    """As PHP already spells one, and for the same reason: `render` alone is not addressable."""
    source = "export class View {\n  render() {\n    return null\n  }\n}\n"
    assert inventory.extents("x.ts", source) == [(1, 5, "View"), (2, 4, "View.render")]



def test_the_front_end_states_the_grammar_version_its_answers_came_from():
    """A symbol table cached on a file's bytes alone would outlive the grammar that read it."""
    stated = getattr(syntax, "grammar_version", None)
    assert callable(stated), "the source front end states no grammar version"

    version = stated()
    assert isinstance(version, str) and version.strip()
    assert version == stated()



DIGEST_SOURCES: dict[str, tuple[str, str, str]] = {
    ".py": (
        "def alpha() -> int:\n    return 1\n\n\ndef beta() -> int:\n    return 2\n",
        "alpha",
        "def alpha() -> int:\n    return 99\n\n\ndef beta() -> int:\n    return 2\n",
    ),
    ".go": (
        "package p\n\nfunc Alpha() int {\n\treturn 1\n}\n\nfunc Beta() int {\n\treturn 2\n}\n",
        "Alpha",
        "package p\n\nfunc Alpha() int {\n\treturn 99\n}\n\nfunc Beta() int {\n\treturn 2\n}\n",
    ),
    ".ts": (
        "export function alpha() {\n  return 1\n}\n\nexport function beta() {\n  return 2\n}\n",
        "alpha",
        "export function alpha() {\n  return 99\n}\n\nexport function beta() {\n  return 2\n}\n",
    ),
    ".tsx": (
        "export function Alpha() {\n  return <b>1</b>\n}\n\nexport function Beta() {\n"
        "  return <b>2</b>\n}\n",
        "Alpha",
        "export function Alpha() {\n  return <b>99</b>\n}\n\nexport function Beta() {\n"
        "  return <b>2</b>\n}\n",
    ),
    ".php": (
        "<?php\nfunction alpha() { return 1; }\nfunction beta() { return 2; }\n",
        "alpha",
        "<?php\nfunction alpha() { return 99; }\nfunction beta() { return 2; }\n",
    ),
    ".twig": (
        "{% block alpha %}one{% endblock %}\n{% block beta %}two{% endblock %}\n",
        "alpha",
        "{% block alpha %}ninety-nine{% endblock %}\n{% block beta %}two{% endblock %}\n",
    ),
}


def test_every_documented_language_answers_with_a_digest_per_declaration():
    """The watermark's key space is `extents`'s: a citation grounds by name and by digest alike."""
    for suffix, (source, _, _) in DIGEST_SOURCES.items():
        digests = inventory.symbol_digests(f"x{suffix}", source)
        assert set(digests) >= {"alpha", "beta"} or set(digests) >= {"Alpha", "Beta"}, suffix


def test_editing_one_body_moves_exactly_one_digest():
    """The whole reason the watermark is per symbol."""
    for suffix, (source, edited_name, edited) in DIGEST_SOURCES.items():
        before = inventory.symbol_digests(f"x{suffix}", source)
        after = inventory.symbol_digests(f"x{suffix}", edited)
        moved = {name for name, digest in after.items() if before.get(name) != digest}
        assert moved == {edited_name}, suffix


REFORMATTED = {
    ".py": (
        "# a header comment\ndef alpha() -> int:\n\n    return 1\n\n\n"
        "def beta() -> int:  # trailing\n    return 2\n"
    ),
    ".go": (
        "package p\n\n// Alpha does a thing.\nfunc Alpha() int {\n\n\treturn 1\n\n}\n\n"
        "func Beta() int { return 2 }\n"
    ),
    ".ts": (
        "// a header comment\nexport function alpha() {\n\n  return 1\n}\n\n"
        "/* beta */\nexport function beta() { return 2 }\n"
    ),
    ".php": (
        "<?php\n// a header comment\nfunction alpha() {\n    return 1;\n}\n"
        "function beta() { return 2; }\n"
    ),
}


def test_comments_and_layout_do_not_move_a_digest():
    """Cosmetic churn is the largest single source of false backfill work."""
    for suffix, reformatted in REFORMATTED.items():
        source = DIGEST_SOURCES[suffix][0]
        assert inventory.symbol_digests(f"x{suffix}", source) == inventory.symbol_digests(
            f"x{suffix}", reformatted
        ), suffix


def test_an_operator_is_part_of_what_a_declaration_is():
    """`walk` yields only *named* nodes, and an operator is anonymous in most grammars."""
    plus = inventory.symbol_digests("x.go", "package p\n\nfunc F(a, b int) int { return a + b }\n")
    minus = inventory.symbol_digests("x.go", "package p\n\nfunc F(a, b int) int { return a - b }\n")
    assert plus["F"] != minus["F"]


def test_a_language_no_front_end_reads_has_no_digests():
    assert inventory.symbol_digests("x.rb", "class Renderer; end\n") == {}


def test_a_nested_declaration_rolls_up_into_its_owner():
    """A citation naming the owner must move when anything inside the owner moves."""
    source = "class View:\n    def render(self) -> int:\n        return 1\n"
    edited = "class View:\n    def render(self) -> int:\n        return 2\n"
    before = inventory.symbol_digests("x.py", source)
    after = inventory.symbol_digests("x.py", edited)
    assert set(before) == {"View", "View.render"}
    assert before["View"] != after["View"]
    assert before["View.render"] != after["View.render"]


def test_the_indexed_accessor_answers_the_same_as_the_direct_one(tmp_path):
    """`symbol_digests_at` shares one extraction with `declared_names_at`; same answer, once."""
    target = tmp_path / "x.py"
    target.write_text(DIGEST_SOURCES[".py"][0], encoding="utf-8")
    assert inventory.symbol_digests_at(target) == inventory.symbol_digests(
        target, DIGEST_SOURCES[".py"][0]
    )
    assert inventory.declared_names_at(target) == frozenset({"alpha", "beta"})


def test_the_indexed_accessor_is_empty_for_an_unread_language(tmp_path):
    target = tmp_path / "x.rb"
    target.write_text("class Renderer; end\n", encoding="utf-8")
    assert inventory.symbol_digests_at(target) == {}




PY_IMPORTS = '''\
"""A module that imports three others in three shapes."""
import a.b
import c.d as dd
from .relative import sibling
from far.upstream import something
from ..package.neighbour import thing
'''


GO_IMPORTS = '''\
package acme

import (
    "fmt"
    "github.com/example/widget"
    "acme/internal/charges"
)

var _ = fmt.Sprintf
'''


TS_IMPORTS = '''\
import x from "./local";
import y from "@scope/pkg";
import "./side-effect";
const z = require("./cjs");
'''


def test_python_imports_return_dotted_module_paths():
    assert inventory.imports_of("mod.py", PY_IMPORTS) == [
        "a.b",
        "c.d",
        ".relative",
        "far.upstream",
        "..package.neighbour",
    ]


def test_go_imports_return_path_literals():
    assert inventory.imports_of("mod.go", GO_IMPORTS) == [
        "fmt",
        "github.com/example/widget",
        "acme/internal/charges",
    ]


def test_typescript_imports_capture_quire_and_side_effects():
    assert inventory.imports_of("mod.ts", TS_IMPORTS) == [
        "./local",
        "@scope/pkg",
        "./side-effect",
        "./cjs",
    ]


def test_imports_dedup_preserve_source_order():
    text = "import a\nimport b\nimport a\n"
    assert inventory.imports_of("m.py", text) == ["a", "b"]


def test_imports_for_an_unread_language_is_empty():
    assert inventory.imports_of("m.rb", "require 'x'\n") == []


def test_imports_for_an_empty_file_is_empty():
    assert inventory.imports_of("m.py", "") == []


def test_a_half_typed_python_file_yields_what_can_be_read():
    """The recovery path: a file `ast` refused still reports the imports the parser could see."""
    text = "import a.b\nfrom .relative imp\nimport c\n"
    out = inventory.imports_of("m.py", text)
    assert "a.b" in out
    assert "c" in out
