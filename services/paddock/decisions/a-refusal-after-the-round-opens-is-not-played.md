story: none
date: 2026-11-16
elements: RunTask
sources: paddock/paddock/runner.py::execute, paddock/paddock/runner.py::_score, paddock/paddock/homeconfig.py::materialize

paddock logs `run <name>` at INFO as its first act once a round is reserved, so every error after that point has a
stderr that starts with lines naming the stablemate sha. Those refusals cannot be quoted word for word and are not
played: a score() that edits the staged tree (paddock/paddock/runner.py::_score, the manifest guard), a score() that
returns something other than a Score, and a base home-config.toml that is not TOML or fails the config schema
(paddock/paddock/homeconfig.py::materialize). Their code is named by RunTask's source.

The refusals that come before that log line are played, and they are the ones a person meets most: no such benchmark,
no such task, a data folder with no commit, and a home config that does not parse.
