# backends

The agent-CLI port lives in `__init__.py`. Each other module adapts one CLI to it, or
holds a piece several adapters share. A new CLI gets its own module.
