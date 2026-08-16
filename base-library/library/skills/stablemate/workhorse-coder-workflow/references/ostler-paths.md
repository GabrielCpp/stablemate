# Ostler path integration

Ostler resolves slugs to canonical paths. Scripts call it instead of hardcoding path patterns.

## CLI Subcommands
```bash
ostler path epic <epic>              # → docs/epics/<NNNN-epic>
ostler path spec <slug>              # → docs/specs/<slug>
ostler path story <epic> <slug>      # → docs/epics/<NNNN-epic>/stories/<slug>/story.md
ostler path branch <slug>            # → <slug>  (bare id — already unique)
ostler path branch <slug> --epic     # → feat/<slug>  (the epic's number is dropped)
```

Epic directories carry their creation order (`0001-checkout-flow`), which is exactly why nothing
here joins `docs/epics/<epic>` by hand — the commands above take the bare slug and return the
folder that exists.

All commands respect `docRoots` from `ostler.yml` / `agents.yml`. Pass `-C <docs_root>` when not running from the docs repo CWD.

## In nodes (Python) — the library facade, never the CLI

Nodes command ostler **in-process** through `Ostler`. There is no `run_tool(["ostler", …])`
here: the CLI is a different process with a different interpreter, and pipx isolation makes
"the shim is on PATH" and "the module imports" routinely disagree.

```python
from ostler import Ostler, path as okf_path

okf = Ostler(docs_root)                        # root discovered upward, like `ostler -C DIR`
spec_dir_rel = okf.spec_path(slug)             # docs/specs/<slug>
try:
    story_path_rel = okf.story_path(epic, slug)
except (OSError, ValueError, RuntimeError):    # an unloadable graph raises; [] means empty
    story_path_rel = ""
# The fallback is the last resort only, for a docs tree ostler could not read at all; it is
# still ostler's layout rule being applied, just without a graph.
story_path = (
    (docs_root / story_path_rel).resolve() if story_path_rel
    else okf_path.story_dir_in(docs_root, epic, slug) / "story.md"
)
```

Note what the fallback is *not*: a `f"docs/epics/{epic}/stories/{slug}/story.md"` literal.
A workflow joins the filename **it** owns — `story.md`, `context.md`, `<gate>-context.md` —
onto a directory ostler resolved, and never spells a `docs/…` path of its own. The graph-free
`ostler.path` helpers (`story_dir_in`, `epic_dir_in`, `epics_index_in`, `backlog_path_in`,
`features_root_in`) exist for exactly this: they honour `docRoots:` and find the numbered
epic folder from a bare slug without paying for a graph load. Full rule and its reasoning:
"A workflow does not spell a doc path" in `workflows/README.md`.

Catch the raise where a fallback is genuinely correct — a path convention the graph cannot
confirm. Never catch it to emit a **verdict**: a gate that could not read the graph is a
failure, not a pass. Full verb→method reference: the `ostler` skill.
