story: none
date: 2026-11-16
elements: RunTask, ListBenchmarks, ResumeTask, Look
sources: paddock/paddock/paths.py::root, paddock/paddock/loader.py::load_benchmark, paddock/paddock/runner.py::execute

The book plays paddock against a sandbox that is a benchmark root. The home config names it with paddock_dir, and
under it gold/acme holds the base home-config.toml, a tasks.py of eight small tasks and a data folder. Each task
exists to show one behaviour of a round: the copy of the data, the merged config, the inputs, a failing step, a
command that fails, a score, an interruption and the helpers a task module imports. The benchmark is named by its folder under gold/, and its data folder is
named data because paddock reads it by that name (paddock/paddock/paths.py, DATA).

The data folder must be a git repository with a commit before a round can copy it. The seed cannot carry a .git
folder, so a person commits it with the CommitTheData event, and the scene `uncommitted` is the one before.

The surface puts the bin folder of the interpreter that runs ostler first on PATH, so that `paddock` is the copy
installed beside it and not whichever one the caller's PATH finds first (a pipx copy on a machine can fail to import).
The environment holds that PATH, HOME, STABLEMATE_CONFIG and the git identity the commit needs, and nothing else of the
machine.
