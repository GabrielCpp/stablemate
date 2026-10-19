from __future__ import annotations

import _tui_support as support
from _trail_support import booted, run
from textual.pilot import Pilot
from textual.screen import Screen
from textual.widgets import OptionList, Static, Tree

from groom import projection, state
from groom.tui.app import GroomTui
from groom.tui.widgets.code import CodeView
from groom.tui.widgets.diff import DiffTab
from groom.tui.widgets.files import FilesTab

__all__ = ["booted", "run"]

API = "api-service"
WEB = "web-app"

MODIFY = """diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,3 @@
 keep
-old line
+new line
"""
ADD = """diff --git a/README.md b/README.md
new file mode 100644
--- /dev/null
+++ b/README.md
@@ -0,0 +1,2 @@
+# Title
+body
"""
TWO_FILES = MODIFY + ADD


def repos_reply(container: str = support.GLOBEX) -> list[dict]:
    wf = state.WORKFLOWS[container]
    other = state.WORKFLOWS[support.WEBAPP]
    return projection.repo_entries([(wf, [API, WEB]), (other, [WEB])])


def route_diff(container: str, repo: str) -> str:
    return f"/diff/{container}?repo={repo}"


def route_files(container: str, repo: str) -> str:
    return f"/files/{container}?repo={repo}"


def route_file(container: str, repo: str, path: str) -> str:
    return f"/file/{container}?repo={repo}&path={path.replace('/', '%2F')}"


def serve(link: support.FakeLink, container: str = support.GLOBEX) -> None:
    link.list_replies["/repos"] = repos_reply(container)
    link.get_replies[route_diff(container, API)] = {"diff": TWO_FILES}
    link.get_replies[route_diff(container, WEB)] = {"diff": ADD}
    link.get_replies[route_files(container, API)] = {"paths": ["src/app.py", "README.md", "src/lib/util.py"]}
    link.get_replies[route_files(container, WEB)] = {"paths": ["index.html"]}
    link.get_replies[route_file(container, API, "src/app.py")] = {
        "path": "src/app.py", "content": "print('a')\n", "lang": "python",
    }
    link.get_replies[route_file(container, API, "README.md")] = {
        "path": "README.md", "content": "# Title\n", "lang": "markdown",
    }


async def open_run(app: GroomTui, pilot: Pilot, link: support.FakeLink, container: str = support.GLOBEX) -> None:
    link.push(support.state_frame())
    await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)
    await app.open_run(container)
    link.push(support.history_frame(container, []))
    await support.until(lambda: app.store.detail is not None)
    await pilot.pause()


def diff_tab(app: GroomTui) -> DiffTab:
    return app.query_one(DiffTab)


def files_tab(app: GroomTui) -> FilesTab:
    return app.query_one(FilesTab)


def text_of(app: GroomTui | Screen, selector: str) -> str:
    content = app.query_one(selector, Static).content
    code = getattr(content, "code", None)
    if code is not None:
        return str(code)
    return getattr(content, "plain", str(content))


def code_of(app: GroomTui, selector: str) -> str:
    return app.query_one(selector, CodeView).plain


def diff_rows(app: GroomTui) -> list[str]:
    listing = app.query_one("#diff-files", OptionList)
    return [str(listing.get_option_at_index(i).prompt) for i in range(listing.option_count)]


def tree_labels(app: GroomTui) -> list[str]:
    tree: Tree[str] = app.query_one("#files-tree", Tree)
    return [str(child.label) for child in tree.root.children]


def tree_leaf(app: GroomTui, *names: str):
    tree: Tree[str] = app.query_one("#files-tree", Tree)
    node = tree.root
    for name in names:
        node = next(child for child in node.children if str(child.label) == name)
    return node
