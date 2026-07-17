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
