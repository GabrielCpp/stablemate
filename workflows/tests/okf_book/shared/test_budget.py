"""A turn reads what fits its budget, nearest first, and counts what it leaves out."""
from __future__ import annotations

from pathlib import Path

from workhorse_workflows.okf_book.shared import budget
from workhorse_workflows.okf_book.shared.budget import ALONE_CEILING_TOKENS, SKILL_TOKENS, estimated_tokens, pack_read, pack_told
from workhorse_workflows.okf_book.main.nodes.listing import listing_context, prompt_tokens
from workhorse_workflows.okf_book.main.nodes.surface import Surface, SurfaceKind

OKF_SKILL = Path(__file__).resolve().parents[4] / "base-library/library/skills/ostler/okf/SKILL.md"


def _context_cost(root: Path, surface: Surface) -> int:
    whole = listing_context(root, surface, budget=10**9)
    return whole.slugs.tokens + whole.files.tokens


def test_items_are_kept_in_order_until_the_budget_is_spent() -> None:
    packed = pack_read([("a", 4), ("b", 5), ("c", 2), ("d", 1)], budget=8)
    assert packed.kept == ("a", "c", "d")
    assert packed.left_out == 1
    assert packed.tokens == 7


def test_the_first_item_goes_alone_when_it_is_over_the_budget() -> None:
    packed = pack_read([("big", 50), ("small", 1)], budget=10)
    assert packed.kept == ("big",)
    assert packed.left_out == 1


def test_an_item_past_the_ceiling_is_left_out_even_first() -> None:
    packed = pack_read([("huge", ALONE_CEILING_TOKENS + 1), ("small", 1)], budget=10)
    assert packed.kept == ("small",)
    assert packed.left_out == 1


def test_told_text_over_the_budget_never_goes_alone() -> None:
    packed = pack_told([("big", 50), ("small", 1)], budget=10)
    assert packed.kept == ("small",)
    assert packed.left_out == 1


def test_a_character_count_rounds_up_to_whole_tokens() -> None:
    assert [estimated_tokens(n) for n in (0, 1, 4, 5)] == [0, 1, 1, 2]


def test_the_listing_turn_reads_the_entry_and_its_nearest_imports_first(tmp_path: Path) -> None:
    _ = (tmp_path / "main.py").write_text("import near\n", encoding="utf-8")
    _ = (tmp_path / "near.py").write_text("import far\n" + "x = 1\n" * 10, encoding="utf-8")
    _ = (tmp_path / "far.py").write_text("y = 2\n" * 1_000, encoding="utf-8")
    surface = Surface(service="svc", kind=SurfaceKind.CLI, entry="main.py")

    context = listing_context(tmp_path, surface, budget=prompt_tokens() + 100)

    assert context.files.kept == ("main.py", "near.py")
    assert context.files.left_out == 1
    assert context.files.tokens <= 100
    assert context.slugs.kept == ()


def test_the_prompt_and_the_entry_slugs_are_charged_before_any_file(tmp_path: Path) -> None:
    pages = tmp_path / "docs" / "features" / "svc"
    (pages / "concepts").mkdir(parents=True)
    _ = (pages / "svc.md").write_text("# svc\n\n## Commands\n\n### home\n", encoding="utf-8")
    _ = (pages / "concepts" / "ledger.md").write_text("# ledger\n", encoding="utf-8")
    _ = (tmp_path / "main.py").write_text("import near\n", encoding="utf-8")
    _ = (tmp_path / "near.py").write_text("x = 1\n", encoding="utf-8")
    surface = Surface(service="svc", kind=SurfaceKind.CLI, entry="main.py")

    context = listing_context(tmp_path, surface, budget=prompt_tokens() + _context_cost(tmp_path, surface) - 1)

    assert context.slugs.kept == ("home",)
    assert context.files.kept == ("main.py",)
    assert context.files.left_out == 1


def test_an_entry_past_a_spent_budget_goes_alone(tmp_path: Path) -> None:
    _ = (tmp_path / "main.py").write_text("import near\n", encoding="utf-8")
    _ = (tmp_path / "near.py").write_text("x = 1\n", encoding="utf-8")
    surface = Surface(service="svc", kind=SurfaceKind.CLI, entry="main.py")

    context = listing_context(tmp_path, surface, budget=1)

    assert context.files.kept == ("main.py",)
    assert context.files.left_out == 1


def test_the_skill_reservation_holds_the_whole_okf_skill() -> None:
    assert estimated_tokens(len(OKF_SKILL.read_text(encoding="utf-8"))) <= SKILL_TOKENS


def test_a_prompt_is_charged_for_the_skill_it_loads_and_the_text_it_includes() -> None:
    bar = (budget.PACKAGE_DIR / "aggregate/prompts/_bar.md").read_text(encoding="utf-8")
    template = (budget.PACKAGE_DIR / "aggregate/prompts/verify-page.md").read_text(encoding="utf-8")
    expanded = template.replace('{% include "aggregate/prompts/_bar.md" %}', bar)
    assert budget.prompt_tokens("aggregate/prompts/verify-page.md") == estimated_tokens(len(expanded)) + SKILL_TOKENS
