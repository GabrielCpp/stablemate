story: track50
date: 2026-11-11
elements: Init

init ends by printing a proposed [user_library.claude] table whenever the shared config holds none and stdin is
not a terminal (farrier/farrier/cli.py:179-197). The sandbox config holds only config_version and the command
runs with stdin closed, so every run prints the proposal naming <sandbox>/config.toml. The case where a table
exists is not played, because no command of the book writes the shared config.
