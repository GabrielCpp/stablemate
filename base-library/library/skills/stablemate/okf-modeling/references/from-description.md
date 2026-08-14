# Playbook A steps — modeling from a description

The step-by-step for [`okf-modeling`](../SKILL.md)'s Playbook A. Reached when a human has
handed you intent — a feature brief, a mockup, "here's the screen I want" — and no code
exists yet. The shared method (the six layers, the order, the convergence gate) is in the
skill body; this is only the loop you run.

1. **Interview the description for the six layers.** From the brief, list: what surface(s)?
   what parts does the user see? what can they do (each verb → a behavior)? what nouns recur
   (each → a concept)? what end-to-end journeys does it enable (each → a flow)? Ask the human
   to fill gaps in *that* structure — you're eliciting nodes, not prose.
2. **Scaffold breadth-first, concepts and shared components first** so downstream links resolve:
   ```bash
   ostler scaffold concept diff   --service groom --title "Diff"
   ostler scaffold screen  changes-view --service groom --title "Changes view"
   ostler scaffold interaction click-file-opens-diff --in docs/features/groom/gui/screens/changes-view.md
   ```
3. **Author the prose and structured bullets** from the description — the *why*, the states, the
   guards (`when:`), the effects (`does:`). Set relation bullets (`on:`/`parent:`/`extends:`) to real
   links between the nodes you just scaffolded. Leave `code:`/`tests:` as scaffolded stubs (or omit),
   and declare a `verify:` check for every normative bullet you write.
4. **Converge:** `ostler fmt …` then `ostler doctor`. Because `code:`/`tests:` aren't link-checked,
   an intent-only graph is fully green before a line of code is written — that's the point: the graph
   is the spec the coder later grounds. `verify:` *is* checked, but against the vocabulary rather
   than against the repo, which is exactly why it is writable this early.
