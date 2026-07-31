"""The `research` program scaffolder — the one thing under the old
`base-library/workflows/research/` that was never a graph node.

`new_program.py` stamps the program folder that `load_config` and the gate-loop
prompts expect. It is run by a human once, before the first run, so the port had
nothing to port it *into* — and deleting it with the rest of the YAML front-end
would have removed the only producer of the workflow's own input. Kept verbatim,
templates and all, next to the workflow it seeds.
"""
