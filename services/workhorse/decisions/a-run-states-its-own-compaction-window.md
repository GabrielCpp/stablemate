story: none
date: 2026-11-23
elements: Run
sources: workhorse/workhorse/runner/backends/claude.py, workhorse/workhorse/profile.py

A run states the compaction window of each claude turn. It does not inherit the operator's. The interactive home
configuration sets `autoCompactWindow` to 150000, and an unattended turn that reads a lot then compacts about every 13
tool calls and writes nothing. A writer turn compacted 20 times in 70 minutes. Turns that worked reached 367k to 441k
tokens with zero or one compaction. A run's configuration is not the home configuration, so the run passes
`--autocompact` on every claude turn.

The engine default is the fixed number 400000, not `auto`. A fixed number makes two runs compact at the same point. It
bounds the cost of one turn's context. The turn that worked compacted once, at 367k.

A power tier can name its own `compact_window`, and the profile's default fills in for a tier that names none. The value
`auto` is accepted and passes the CLI's per-model window. A value that is not `auto` or an integer of at least 100000
reads as unset. The other CLIs ignore the setting.

An inherited `CLAUDE_CODE_AUTO_COMPACT_WINDOW` still wins over the flag, because the CLI reads the environment variable
first. The run documents this and does not strip the variable.
