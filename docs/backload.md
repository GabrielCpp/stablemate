
# Backload

- epic ordered by number in the folder when created by the author workflow e.g. 0001-<slug>, 0002-<slug>, etc..
- ostler should use the short handle everywhere or have the option to sue it at least
- Rather than an exclude list in farrier for .agents we should list the dir and file we want to ignore
- Using environement variable is nodes and workflow IS PROHIBITED. Make that a rule. Everything need to be passed by argument or be a workflow parameter (like AGENT_DIR should be part of the workflow object parent). This apply to all workflows.
- Currently, what is put in the nodes folder ares the flow. This apply to all workflows. More like we will need to change the layout to
  <workflow name e.g. coder>/
      shared/
      <flow name e.g. qa>/
         flow.py
         nodes.py
      workflow.py
      nodes.py
- Paths mangleling for backload, docs, etc.. should be done / provided by ostler. This apply to all workflows.
- We need to stop collecting telemetry on test runs. We should clear telemetly of tests run from groom.
- We need to stop showing grrom telemetry from workflow which are not currently connected.

- I see the coder workflow have skill reference, we should query scripts by tags from the frontmatter rather than by name. e.g. go, tests, architecture. Then, we can reference them using a jinja method `find_by_tags('go', 'tests')` to return all instruction having all tags listed.
