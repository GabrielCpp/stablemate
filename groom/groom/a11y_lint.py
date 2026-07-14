"""A dependency-free accessibility linter for groom's hand-authored HTML templates.

groom is Python-only — no Node, no bundler — so there is no `eslint-plugin-jsx-a11y` or
`html-validate` in reach. This module is the static half of groom's a11y gate: a stdlib-only
(`html.parser`) scan of the templates for the a11y faults a hand-authored HTMX template is prone to
and that HTML *alone* can prove — missing input labels, role-less/unnamed controls, `<img>` without
`alt`, HTMX action attributes on non-interactive tags, ARIA widget roles that aren't keyboard
focusable, and websocket/OOB push targets with no live region.

It is deliberately conservative: every rule is defensible from the markup with a low false-positive
rate, so a finding is a real bug, not a style nit. What it *cannot* see — controls wired by JS event
delegation (`document.body.addEventListener("click", …)` keyed on a class/data-attr), and the
composed post-swap DOM — is covered by the runtime axe pass on the live harness (QA phase) and the
manual keyboard smoke. See the `htmx-accessibility` / `accessibility` skills for the full contract.

Run it: ``python -m groom.a11y_lint [PATH ...]`` (defaults to the package's ``templates/``). Exit 0
when clean, 1 when any finding is reported. ``lint_html(text, path)`` is the importable core.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

# Void elements never get a close tag — the parser must not keep them on the open-element stack.
VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})
# Tags that carry an interactive role natively (keyboard-focusable, screen-reader-announced).
NATIVE_INTERACTIVE = frozenset({"a", "button", "input", "select", "textarea", "summary"})
# HTMX / inline attributes that make an element a *control* (it does something when activated).
ACTION_ATTRS = frozenset({
    "onclick", "ws-send",
    "hx-get", "hx-post", "hx-put", "hx-delete", "hx-patch",
})
# ARIA roles that denote a keyboard-operable widget — they demand focusability.
WIDGET_ROLES = frozenset({
    "button", "link", "checkbox", "radio", "switch", "tab", "menuitem",
    "menuitemcheckbox", "menuitemradio", "option",
})
# `role=` values that make a region announce its own updates — a valid live-region on their own.
LIVE_ROLES = frozenset({"status", "log", "alert"})
# `<input type>` values that get their name from a `value`/`alt`, not an associated `<label>`.
NO_LABEL_INPUT_TYPES = frozenset({"hidden", "submit", "reset", "button", "image"})


@dataclass
class Node:
    tag: str
    attrs: dict[str, str]
    line: int
    parent: "Node | None" = None
    children: list["Node"] = field(default_factory=list)
    text: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.code} {self.message}"


class _Tree(HTMLParser):
    """Builds a lightweight element tree with source lines; tolerant of malformed markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node(tag="#root", attrs={}, line=0)
        self._stack: list[Node] = [self.root]
        self.nodes: list[Node] = []

    def _open(self, tag: str, attrs: list[tuple[str, str | None]]) -> Node:
        parent = self._stack[-1]
        node = Node(
            tag=tag,
            attrs={k.lower(): (v or "") for k, v in attrs},
            line=self.getpos()[0],
            parent=parent,
        )
        parent.children.append(node)
        self.nodes.append(node)
        return node

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = self._open(tag, attrs)
        if tag not in VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._stack[-1].text.append(data)


def _has_name_attr(node: Node) -> bool:
    """True when the element carries an explicit accessible name attribute."""
    a = node.attrs
    return bool(a.get("aria-label", "").strip() or a.get("aria-labelledby", "").strip()
                or a.get("title", "").strip())


def _accessible_text(node: Node) -> str:
    """Visible/announced text of a subtree, skipping `aria-hidden` branches; includes img alt."""
    if node.attrs.get("aria-hidden") == "true":
        return ""
    parts = list(node.text)
    for child in node.children:
        if child.tag == "img":
            parts.append(child.attrs.get("alt", ""))
        elif _has_name_attr(child):
            parts.append(child.attrs.get("aria-label", "") or "x")
        else:
            parts.append(_accessible_text(child))
    return " ".join(p for p in parts if p).strip()


def _has_accessible_name(node: Node) -> bool:
    return _has_name_attr(node) or bool(_accessible_text(node))


def _is_focusable(node: Node) -> bool:
    a = node.attrs
    if "tabindex" in a:
        return a["tabindex"].strip() != "-1"
    if node.tag in NATIVE_INTERACTIVE:
        # a bare <a> with no href is not focusable
        return node.tag != "a" or "href" in a
    return "contenteditable" in a


def _ancestor_tags(node: Node) -> set[str]:
    tags, cur = set(), node.parent
    while cur is not None:
        tags.add(cur.tag)
        cur = cur.parent
    return tags


def lint_html(text: str, path: str) -> list[Finding]:
    """Return the a11y findings for one HTML document."""
    parser = _Tree()
    parser.feed(text)
    nodes = parser.nodes
    out: list[Finding] = []

    def add(node: Node, code: str, msg: str) -> None:
        out.append(Finding(path, node.line, code, msg))

    label_for = {n.attrs["for"].strip() for n in nodes if n.tag == "label" and n.attrs.get("for")}

    for node in nodes:
        tag, a = node.tag, node.attrs

        if tag == "html" and not a.get("lang", "").strip():
            add(node, "A11Y001", "<html> is missing a lang attribute")

        if tag in ("input", "textarea", "select"):
            itype = a.get("type", "text").lower()
            if tag == "input" and itype in NO_LABEL_INPUT_TYPES:
                if itype in ("submit", "reset", "button") and not (
                        a.get("value", "").strip() or _has_name_attr(node)):
                    add(node, "A11Y006", f"<input type={itype}> has no accessible name")
                elif itype == "image" and not (a.get("alt", "").strip() or _has_name_attr(node)):
                    add(node, "A11Y003", "<input type=image> is missing alt text")
            elif not (_has_name_attr(node) or a.get("id", "").strip() in label_for
                      or "label" in _ancestor_tags(node)):
                add(node, "A11Y002",
                    f"<{tag}> has no associated label (a placeholder is not a label)")

        if tag == "img" and "alt" not in a:
            add(node, "A11Y003", "<img> is missing an alt attribute")

        action = next((k for k in ACTION_ATTRS if k in a), None)
        if action and tag not in NATIVE_INTERACTIVE and tag not in ("form", "label"):
            add(node, "A11Y004",
                f"'{action}' on <{tag}> — use a real <button>/<a> so it is keyboard-operable")

        role = a.get("role", "").strip()
        # `option` is exempt: in the combobox/listbox pattern the options are managed via
        # aria-activedescendant while DOM focus stays on the input, so they are correctly
        # non-focusable (ARIA Authoring Practices).
        if role in WIDGET_ROLES and role != "option" and not _is_focusable(node):
            add(node, "A11Y005",
                f"role={role} on <{tag}> is not keyboard focusable (add tabindex=0)")

        if (tag in ("button", "a") or role in WIDGET_ROLES) and not _has_accessible_name(node):
            if not (tag == "a" and "href" not in a):   # a bare anchor isn't a control
                add(node, "A11Y006",
                    f"<{tag}>{' role=' + role if role else ''} has no accessible name")

        if "hx-swap-oob" in a and not (
                a.get("aria-live", "").strip() or role in LIVE_ROLES):
            add(node, "A11Y007",
                "hx-swap-oob target has no aria-live/role — pushed updates won't be announced")

    return out


def _iter_html_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.rglob("*.html")))
        elif p.suffix == ".html":
            files.append(p)
    return files


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    targets = [Path(a) for a in args] or [Path(__file__).parent / "templates"]
    findings: list[Finding] = []
    for file in _iter_html_files(targets):
        findings.extend(lint_html(file.read_text(encoding="utf-8"), str(file)))
    for f in findings:
        print(f)
    n = len(findings)
    print(f"\na11y-lint: {n} finding{'s' if n != 1 else ''}"
          f" in {len(_iter_html_files(targets))} file(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
