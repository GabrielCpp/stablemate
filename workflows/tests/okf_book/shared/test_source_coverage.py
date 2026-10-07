"""The check names each folder of the surface's source holding a product file no page cites."""
from __future__ import annotations

from pathlib import Path

from okf_book.support import git
from ostler import index
from ostler.model import load
from workhorse_workflows.okf_book.shared.page_check import page_problems
from workhorse_workflows.okf_book.shared.source_coverage import UNCITED_CODE, product_files, uncited_by_folder

SOURCES = (
    "web/app/routes/editor.tsx",
    "web/app/routes/login.tsx",
    "web/app/lib/drafts.ts",
    "web/app/lib/drafts.test.ts",
    "web/app/vite-env.d.ts",
    "web/e2e/fixtures.ts",
    "web/vite.config.ts",
    "web/vitest.setup.ts",
    "web/README.md",
)


def _page(*cited: str) -> str:
    code = "".join(f"- code: `{path}`\n" for path in cited)
    return f"---\ntype: screen\nslug: login\ntitle: Login\n---\n# Login\n\n{code}\nWhat a user signs in with.\n"


def _repo(tmp_path: Path, *cited: str) -> Path:
    repo = tmp_path / "repo"
    for path in SOURCES:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        _ = (repo / path).write_text("export const x = 1;\n", encoding="utf-8")
    page = repo / "docs/features/web/login.md"
    page.parent.mkdir(parents=True)
    _ = page.write_text(_page(*cited), encoding="utf-8")
    _ = git(repo, "init", "-q")
    _ = git(repo, "add", "-A")
    return repo


def _uncited(repo: Path, source_folder: str = "web") -> dict[str, tuple[str, ...]]:
    with index.session(repo):
        return uncited_by_folder(repo, source_folder, load(repo), "web")


def test_product_files_leave_out_tests_declarations_and_tool_configs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert product_files(repo, "web") == ("web/app/lib/drafts.ts", "web/app/routes/editor.tsx", "web/app/routes/login.tsx")


def test_each_folder_with_an_uncited_product_file_is_named_with_its_files(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "web/app/routes/login.tsx")

    assert _uncited(repo) == {"web/app/lib": ("web/app/lib/drafts.ts",), "web/app/routes": ("web/app/routes/editor.tsx",)}


def test_a_file_cited_with_a_symbol_counts_as_cited(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "web/app/routes/login.tsx", "web/app/routes/editor.tsx::x", "web/app/lib/drafts.ts")

    assert _uncited(repo) == {}


def test_no_source_folder_names_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    assert _uncited(repo, "") == {}


def test_the_check_puts_each_uncited_folder_on_the_entries_page(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "web/app/routes/login.tsx")
    entries = "---\ntype: entries\nslug: entries\ntitle: web\n---\n# web\n\n- [Login](login.md)\n"
    _ = (repo / "docs/features/web/entries.md").write_text(entries, encoding="utf-8")

    uncited = [problem for problem in page_problems(repo, "web", "web") if problem.code == UNCITED_CODE]

    assert [(problem.page, problem.node) for problem in uncited] == [
        ("docs/features/web/entries.md", "web/app/lib"),
        ("docs/features/web/entries.md", "web/app/routes"),
    ]
    assert uncited[1].text.startswith("web/app/routes/: no page cites 1 of its product files, `web/app/routes/editor.tsx`.")
