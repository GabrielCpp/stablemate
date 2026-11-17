"""What a person does to the root between commands, outside paddock."""

from __future__ import annotations

from ostler.book import Outside, Sandbox

from .model import actions as act

GIT = "git -C root/gold/acme/data"
KEEP = (
    "mkdir -p kept; for d in root/results/acme/*; do t=$(basename \"$d\"); for r in \"$d\"/*/*; do "
    "cp \"$r/ledger.json\" \"kept/$t.ledger.json\" 2>/dev/null; cp \"$r/score.json\" \"kept/$t.score.json\" 2>/dev/null; "
    "done; done; true"
)


class CommitTheData(Outside):
    does = "A person makes the benchmark's data folder a git repository and commits what it holds."
    carries = act.CommitData

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.run(["sh", "-c", f"{GIT} init -q && {GIT} add -A && {GIT} commit -q -m data && mkdir -p made && echo committed > made/data-repo.txt"], None)


class AddABrokenBenchmark(Outside):
    does = "A person adds a benchmark whose tasks.py raises when it is imported."
    carries = act.AddBrokenBenchmark

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.write("root/gold/broken/tasks.py", 'raise RuntimeError("bad")\n')
        sandbox.write("root/gold/broken/home-config.toml", "config_version = 2\n")
        sandbox.write("root/gold/broken/data/README.md", "broken\n")


class BreakTheHomeConfig(Outside):
    does = "A person leaves the home config as text that is not TOML."
    carries = act.BreakHomeConfig

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.write("config.toml", "x = (\n")


class EmptyTheRoot(Outside):
    does = "A person points paddock_dir at a folder that holds no gold/."
    carries = act.EmptyRoot

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.write("config.toml", 'config_version = 2\npaddock_dir = "<sandbox>/empty"\n')


class KeepTheResults(Outside):
    does = "A person copies the ledger and the score of each task's latest result out of results/, as the README says to keep a result."
    carries = act.KeepResults

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.run(["sh", "-c", KEEP], None)


class StopARound(Outside):
    does = "A person starts the interrupt task and a step stops the round before it ends, as Ctrl-C would."
    carries = act.StopRound

    def happen(self, sandbox: Sandbox) -> None:
        sandbox.run(["paddock", "run", "acme", "interrupt", "--no-pin-project", "--quiet"], None)
