story: workhorse-book
date: 2026-11-12
elements: Control

`control status` without `--params`, `stop`, `reload`, `questions`, `answer` and `switch-cli` with a backend name talk to the run's listener, and a run is live only while a backend drives it. The sandbox has none, so those verbs are reached only through their refusals: a verb that names no run, a switch with no backend, a stop with a scope it does not take. What the book plays in full is the offline half: `status --params` reads the checkpoint on disk, `rewind` rewrites it, and `resume` refuses a run that finished or never launched. The model therefore keeps a run's checkpoint and event log, and never a listener.
