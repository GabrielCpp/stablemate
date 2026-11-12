story: workhorse-book
date: 2026-11-12
elements: Replay

`replay` re-runs one recorded agent turn against a live backend. The sandbox has none, so the book plays only its refusals: a run that is not there, and a turn directory without a `turn.json`. `Service.unseen` says so for the inputs of `Replay`. Both `--run` and the turn are required by the command's parser, so the book declares both fields required and never sends the command without them.
