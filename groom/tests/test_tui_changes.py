from __future__ import annotations

import _changes_support as ch
import _tui_support as support
import pytest

from groom import state
from groom.tui.changes import PathNode, capped, cap_note, default_repo, path_tree, repo_items, split_diff
from groom.tui.route import route


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


def test_repo_items_flatten_every_group_with_its_state_and_type():
    items = repo_items(ch.repos_reply(), "")
    assert [(item["label"], item["state"], item["type"]) for item in items] == [
        ("author-globex/api-service", "running", "author"),
        ("author-globex/web-app", "running", "author"),
        ("coder-web-app/web-app", "finished", "coder"),
    ]
    assert items[0]["container"] == support.GLOBEX
    assert items[0]["repo"] == ch.API


def test_repo_items_filter_by_a_case_insensitive_substring_of_the_label():
    assert [item["label"] for item in repo_items(ch.repos_reply(), "  WEB ")] == [
        "author-globex/web-app",
        "coder-web-app/web-app",
    ]
    assert repo_items(ch.repos_reply(), "nothing") == []


def test_default_repo_takes_the_first_item_of_the_runs_own_container():
    chosen = default_repo(ch.repos_reply(), support.WEBAPP, "coder-web-app")
    assert chosen == {"container": support.WEBAPP, "repo": ch.WEB, "label": "coder-web-app/web-app"}


def test_default_repo_without_a_match_falls_back_to_the_container_and_run_name():
    assert default_repo(ch.repos_reply(), support.ACME, "coder-acme") == {
        "container": support.ACME, "repo": "", "label": "coder-acme",
    }


def test_split_diff_reads_a_modified_file():
    [file] = split_diff(ch.MODIFY)
    assert (file.path, file.added, file.deleted) == ("src/app.py", 1, 1)
    assert file.text.startswith("diff --git a/src/app.py b/src/app.py")
    assert file.text.endswith("+new line")


def test_split_diff_reads_an_added_file_and_a_deleted_file():
    deleted = "diff --git a/gone.txt b/gone.txt\ndeleted file mode 100644\n--- a/gone.txt\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-one\n-two\n"
    added, gone = split_diff(ch.ADD + deleted)
    assert (added.path, added.added, added.deleted) == ("README.md", 2, 0)
    assert (gone.path, gone.added, gone.deleted) == ("gone.txt", 0, 2)


def test_split_diff_names_a_rename_by_its_new_path():
    renamed = (
        "diff --git a/old name.txt b/new name.txt\nsimilarity index 90%\n"
        "rename from old name.txt\nrename to new name.txt\n--- a/old name.txt\n+++ b/new name.txt\n"
        "@@ -1 +1 @@\n-a\n+b\n"
    )
    [file] = split_diff(renamed)
    assert (file.path, file.added, file.deleted) == ("new name.txt", 1, 1)


def test_split_diff_names_a_pure_rename_and_a_binary_file_from_the_header():
    pure = "diff --git a/x.txt b/y.txt\nsimilarity index 100%\nrename from x.txt\nrename to y.txt\n"
    binary = "diff --git a/logo.png b/logo.png\nindex 1..2 100644\nBinary files a/logo.png and b/logo.png differ\n"
    renamed, image = split_diff(pure + binary)
    assert (renamed.path, renamed.added, renamed.deleted) == ("y.txt", 0, 0)
    assert (image.path, image.added, image.deleted) == ("logo.png", 0, 0)
    assert "Binary files" in image.text


def test_split_diff_of_nothing_is_empty():
    assert split_diff("") == []
    assert split_diff("\n  \n") == []


def test_split_diff_counts_changed_lines_but_not_the_file_headers():
    tricky = (
        "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -1,3 +1,3 @@\n"
        "--- a deleted line that starts with dashes\n+++ an added line that starts with pluses\n"
        " context\n\\ No newline at end of file\n"
    )
    [file] = split_diff(tricky)
    assert (file.added, file.deleted) == (1, 1)


def test_split_diff_keeps_each_files_own_text():
    first, second = split_diff(ch.TWO_FILES)
    assert "README" not in first.text
    assert "src/app.py" not in second.text


def test_path_tree_puts_directories_before_files_and_sorts_each():
    tree = path_tree(["zeta.txt", "src/b.py", "src/a/deep.py", "Alpha.md", "src/a.py", "docs/x.md"])
    assert [(node.name, node.is_file) for node in tree] == [
        ("docs", False), ("src", False), ("Alpha.md", True), ("zeta.txt", True),
    ]
    src = tree[1]
    assert [(node.name, node.is_file) for node in src.children] == [("a", False), ("a.py", True), ("b.py", True)]
    assert src.children[0].children == [PathNode("deep.py", "src/a/deep.py", True)]


def test_capped_keeps_the_first_lines_and_counts_them_all():
    text = "\n".join(str(n) for n in range(10))
    assert capped(text, 3) == ("0\n1\n2", 10)
    assert capped("a\nb", 5) == ("a\nb", 2)
    assert capped("", 5) == ("", 0)


def test_cap_note_speaks_only_when_lines_were_cut():
    assert cap_note(6000) == "Showing the first 3000 of 6000 lines."
    assert cap_note(3000) == ""


def test_route_quotes_the_path_segment_and_the_query():
    assert route("/diff", "abc") == "/diff/abc"
    assert route("/diff", "a b/c", repo="my repo&x=1") == "/diff/a%20b%2Fc?repo=my%20repo%26x%3D1"
    assert route("/file", "abc", repo="", path="dir name/a&b.txt") == "/file/abc?repo=&path=dir%20name%2Fa%26b.txt"
