## The service books

The current behaviour of each service is its book, a Python package under `services/`. `<module>` below is the book's module, the start of the path `ostler book search` prints for a `books/` hit: `services.<name>` beside the code, `services.<repo>.<name>` in the artifacts folder. Read it before you write and never write to it. Do not inspect the app or the source to learn what a service does today.

- `ostler book search <term> --service <module> [--kind rule|endpoint|action|journey|screen|decision]` finds the entries about a term.
- `ostler book explain <module> <ClassName>` shows one entry in full.
- `ostler book decisions <module>` lists the decisions the service settled.
