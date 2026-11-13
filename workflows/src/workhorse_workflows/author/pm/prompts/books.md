## The service books

The current behaviour of each service is its book, a Python package under `services/<name>/`. Read it before you write and never write to it. Do not inspect the app or the source to learn what a service does today.

- `ostler book search <term> --service services.<name> [--kind rule|endpoint|action|journey|screen|decision]` finds the entries about a term.
- `ostler book explain services.<name> <ClassName>` shows one entry in full.
- `ostler book decisions services.<name>` lists the decisions the service settled.
