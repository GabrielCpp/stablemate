story: none
date: 2026-11-23
elements: Run
sources: workhorse/workhorse/pyflow/run.py::_interrupt_on_terminate

A run that receives SIGTERM stops the way Ctrl-C and `control stop` stop it. It ends its active agent turn, records the
interrupt in `run.json`, keeps its worktree, prints the resume command and exits 130. Its telemetry closes with the
terminal `interrupted`, so groom shows how the run ended.

Before this, SIGTERM killed the process at once. The root span never reached groom, so groom saw a run that went quiet
and labelled it silent, and History recorded no ending. Paddock sends SIGTERM to every process a round leaves standing,
so every reaped round looked that way.

The exit code stays 130 rather than 143 so a caller sees one code for every operator stop. The handler is installed only
while the run drives its flow on the main thread. A signal that arrives during start-up, before the run exists, still
kills the process.
