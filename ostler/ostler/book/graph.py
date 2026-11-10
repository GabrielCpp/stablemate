"""The state graph of a record, drawn from the matrix cells and never beside
them: a transition is a solid edge labelled with the action and the kinds of
change it made, a refusal a self-loop in a warning colour, a no-op a grey one,
a move no action owns a dashed edge. The cells themselves sit under the graph
as a table, and the impossible pairs are counted there."""

from __future__ import annotations

import html
import shutil
import subprocess
from datetime import date
from typing import Any, Callable

from ostler.book.matrix import Cell, cells
from ostler.book.model import Model
from ostler.book.state import Axes

REFUSE = "#b00020"
NOOP = "#8a8a8a"
EDGE = "#1f1f1f"


def _id(name: str) -> str:
    return '"' + name.replace('"', "'") + '"'


def _label(c: Cell) -> str:
    if c.kind == "transition" and c.changes:
        return c.action + " (" + ", ".join(dict.fromkeys(ch.brief() for ch in c.changes)) + ")"
    if c.kind == "refuse":
        return f"{c.action} ({c.status} {c.message})"
    if c.kind == "defect":
        return f"{c.action} (defect {c.status} {c.message})"
    return c.action if c.kind == "transition" else f"{c.action} ({c.kind})"


def _colour(c: Cell) -> str:
    return {"refuse": REFUSE, "defect": REFUSE, "no-op": NOOP, "impossible": NOOP}.get(c.kind, EDGE)


def _node(name: str, when: str, stays: list[Cell]) -> str:
    """A state box: its name, then every action that leaves the record in it."""
    rows = [f'<TR><TD ALIGN="CENTER"><B>{html.escape(name)}</B></TD></TR>']
    rows += [f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="10" COLOR="{_colour(c)}">{html.escape(_label(c))}</FONT></TD></TR>'
             for c in stays]
    style = ', style="rounded,dashed"' if name == "(none)" else ""
    return (f'{_id(name)} [label=<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="2">{"".join(rows)}</TABLE>>'
            f', tooltip="{html.escape(when, quote=True)}"{style}];')


def _edges(found: list[Cell]) -> dict[tuple[str, str, bool], list[str]]:
    grouped: dict[tuple[str, str, bool], list[str]] = {}
    for c in found:
        if c.kind == "transition" and c.target != c.scene:
            grouped.setdefault((c.scene, c.target, c.owned_by_nobody), []).append(_label(c))
    return grouped


def _table(axes: Axes[Any], found: list[Cell]) -> str:
    actions = list(axes.actions)
    head = "".join(f"<TD><B>{html.escape(a)}</B></TD>" for a in actions)
    rows = [f"<TR><TD><B>{html.escape(axes.record)} ↓ / action →</B></TD>{head}</TR>"]
    by: dict[tuple[str, str], Cell] = {(c.scene, c.action): c for c in found}
    for scene in axes.scenes:
        tds = []
        for a in actions:
            c = by[(scene.name, a)]
            tds.append(f'<TD ALIGN="LEFT"><FONT COLOR="{_colour(c)}">{html.escape(c.brief())}</FONT></TD>')
        rows.append(f"<TR><TD><B>{html.escape(scene.name)}</B></TD>{''.join(tds)}</TR>")
    impossible = sum(c.kind == "impossible" for c in found)
    rows.append(f'<TR><TD COLSPAN="{len(actions) + 1}" ALIGN="LEFT">'
                f"{len(found)} cells, {impossible} impossible, 0 open</TD></TR>")
    return '<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="4">' + "".join(rows) + "</TABLE>>"


def dot(new_model: Callable[[date], Model], axes: Axes[Any]) -> str:
    found = cells(new_model, axes)
    lines = [f"digraph {_id(axes.record)} {{",
             f'  label="{axes.record} · computed on the model with today = {axes.today.isoformat()}"; labelloc=t;',
             '  fontname="Helvetica"; node [fontname="Helvetica", shape=box, style=rounded]; edge [fontname="Helvetica", fontsize=10];']
    for scene in axes.scenes:
        stays = [c for c in found if c.scene == scene.name and c.kind != "impossible"
                 and (c.kind != "transition" or c.target == scene.name)]
        lines.append("  " + _node(scene.name, scene.when, stays))
    known = {s.name for s in axes.scenes}
    for (source, target, dashed), labels in _edges(found).items():
        if target not in known:
            lines.append(f'  {_id(target)} [style="rounded,dashed"];')
            known.add(target)
        attrs = ['label="' + "\\n".join(labels) + '"'] + (["style=dashed"] if dashed else [])
        lines.append(f"  {_id(source)} -> {_id(target)} [{', '.join(attrs)}];")
    lines += [f"  table [shape=plaintext, label={_table(axes, found)}];",
              f"  {_id(axes.scenes[-1].name)} -> table [style=invis];",
              "}"]
    return "\n".join(lines)


def render(source: str, path: str) -> str | None:
    """Write the svg next to the dot file; None when Graphviz is not installed."""
    if shutil.which("dot") is None:
        return None
    svg = path[: -len(".dot")] + ".svg" if path.endswith(".dot") else path + ".svg"
    subprocess.run(["dot", "-Tsvg", "-o", svg], input=source.encode(), check=True)
    return svg
