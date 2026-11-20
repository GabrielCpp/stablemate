"""The drawing `dot` prints for the loop runner: the same text under any graph name, apart from its first line."""

from __future__ import annotations

BODY = (
    '  rankdir=TB;',
    '  bgcolor=white;',
    '  compound=true;',
    '  newrank=true;',
    '  node [shape=box, style="rounded,filled", fillcolor=lightblue];',
    '  edge [color=darkblue, fontsize=10];',
    '',
    '  subgraph cluster_default_f0__ {',
    '    label="default";',
    '    style=dashed; color=gray50; fontsize=11;',
    '',
    '    f0____start [label="START", shape=circle, fillcolor=lightgreen, width=0.4];',
    '    subgraph cluster_f0__start {',
    '      label="start"; fontsize=12;',
    '      style="rounded,filled"; fillcolor=lightblue; color=steelblue;',
    '      node [style="filled", fontsize=10];',
    '      f0__start__0 [label="run.md", shape=note, fillcolor=lightyellow];',
    '    }',
    '    f0____end [label="END", shape=doublecircle, fillcolor=gold, width=0.4];',
    '',
    '    f0____start -> f0__start__0 [lhead=cluster_f0__start];',
    '    f0__start__0 -> f0____end [color=darkgoldenrod, ltail=cluster_f0__start];',
    '  }',
    '',
    '  subgraph cluster_legend {',
    '    label="legend";',
    '    style=dashed; color=gray50; fontsize=11;',
    '    node [shape=plaintext, style="", fillcolor=white, fontsize=10];',
    '    legend_a [label=""]; legend_b [label=""];',
    '    legend_c [label=""]; legend_d [label=""];',
    '    legend_e [label=""]; legend_f [label=""];',
    '    legend_a -> legend_b [label="continue"];',
    '    legend_c -> legend_d [label="await: parked on an operator gate", style=dashed, color=darkorange];',
    '    legend_e -> legend_f [label="done: the flow ends", color=darkgoldenrod];',
    '    subgraph cluster_legend_state {',
    '      label="a state: what it runs, top to bottom";',
    '      style="rounded,filled"; fillcolor=lightblue; color=steelblue;',
    '      node [style="filled"];',
    '      legend_call [label="a node call\\nits docstring", shape=box, fillcolor=white];',
    '      legend_agent [label="an agent turn: prompt.md\\nits title", shape=note, fillcolor=lightyellow];',
    '      legend_handoff [label="handoff → a sub-flow\\nrun to its END, then back here", shape=box, fillcolor=plum];',
    '      legend_call -> legend_agent -> legend_handoff [style=invis];',
    '    }',
    '  }',
    '}',
)


def graph(name: str) -> tuple[str, ...]:
    """The lines `dot` prints for a graph of this name."""
    return (f"digraph {name} {{", *BODY)
