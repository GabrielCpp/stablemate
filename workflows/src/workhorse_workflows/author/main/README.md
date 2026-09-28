# main

The default `author` flow and the node set most author machines call.

## Map

- `flow.py`: the flat author loop: dispatch survey or story mode, else run the next stage the planner picks.
- `nodes/`: the nodes shared across author machines: config, intake, planning, epic and story picks, gates and the commit.
