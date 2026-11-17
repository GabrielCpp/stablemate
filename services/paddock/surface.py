"""paddock run in a sandbox: the benchmark root it starts from and the environment it sees."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from ostler.book import CommandSurface, Environment, Seed

TASKS = '''"""The acme benchmark: one task per behaviour of a round."""
import json
from pathlib import Path

from paddock import Score, project, score, step, task
from paddock.runner import RoundInterrupted
from paddock.tasks import forensics, inputs, judge, operator_gates, tree

SEEN = Path("<sandbox>/seen")


def note(name, *lines):
    SEEN.mkdir(parents=True, exist_ok=True)
    (SEEN / name).write_text("".join(f"{line}\\n" for line in lines), encoding="utf-8")


task(name="plain")


@step()
def copy(run):
    config = (run.stage / ".git" / "config").read_text(encoding="utf-8")
    lines = []
    if (run.stage / "README.md").is_file():
        lines.append("stage holds README.md")
    if "[remote" not in config:
        lines.append("stage has no remote")
    note("plain-stage.txt", *lines)


@step()
def look(run):
    text = run.config.read_text(encoding="utf-8")
    lines = [f"pinned={run.pinned is not None and run.pinned.pinned}"]
    if 'default_cli = "claude"' in text:
        lines.append("default_cli=claude")
    anchored = [line for line in text.splitlines() if line.startswith("artifacts_dir")]
    if anchored and str(run.stage) in anchored[0]:
        lines.append("artifacts_dir inside the stage")
    if run.pinned is not None and run.pinned.pinned:
        if (run.project / ".git").read_text(encoding="utf-8") == project.FENCE_GITFILE:
            lines.append("pin fenced")
        if "[remote" not in (project.stashed_git_dir(run.project) / "config").read_text(encoding="utf-8"):
            lines.append("pin has no remote")
    note("plain-project.txt", *lines)


task(name="override", config={"default_cli": "codex"})


@step()
def merged(run):
    text = run.config.read_text(encoding="utf-8")
    lines = []
    if 'default_cli = "codex"' in text:
        lines.append("default_cli=codex")
    if "artifacts_dir" in text:
        lines.append("artifacts_dir kept")
    note("override.txt", *lines)


task(name="inputs", inputs={"budget": 1200.0, "only": ["A-1", "B-2"], "label": "x,y", "strict": True})


@step()
def read(run):
    note(
        "inputs.txt",
        f"budget={inputs.number(run, 'budget', 0)}",
        f"only={','.join(inputs.names(run, 'only'))}",
        f"label={','.join(inputs.names(run, 'label'))}",
        f"strict={inputs.flag(run, 'strict')}",
        f"absent={inputs.number(run, 'absent', 7.5)}",
        f"none={len(inputs.names(run, 'absent'))}",
    )


@step()
def misread(run):
    inputs.number(run, "strict", 0)


task(name="failing")


@step()
def first(run):
    note("failing.txt", "first ran")


@step()
def boom(run):
    raise RuntimeError("boom")


@step()
def later(run):
    note("failing-later.txt", "later ran")


task(name="tools")


@step()
def exit_code(run):
    done = run.cli("false")
    note("tools.txt", f"exit={done.returncode}", f"ok={done.ok}")


@step()
def missing_tool(run):
    run.cli("no-such-program-xyz")


task(name="scored")


@step()
def measure(run):
    note("scored.txt", "measured")


@score()
def caught(run):
    return Score(headline="caught 7/9  missed 2", detail=("a: caught", "b: missed"), caveats=("one trial was short",))


task(name="interrupt")


@step()
def start(run):
    note("interrupt-start.txt", "started")


@step()
def park(run):
    parked = SEEN / "interrupt-park.txt"
    if not parked.exists():
        note("interrupt-park.txt", "parked")
        raise RoundInterrupted("stopped from outside")
    note("interrupt-park.txt", "parked", "passed")


@step()
def finish(run):
    note("interrupt-finish.txt", "finished")


task(name="library")


@step()
def helpers(run):
    events = run.workdir("events") / "events.jsonl"
    rows = [{"phase": "enter", "node": n} for n in "abababc"]
    events.write_text("".join(json.dumps(e) + "\\n" for e in rows) + "not json\\n", encoding="utf-8")
    entered = forensics.entered_nodes(events)
    found = forensics.cycles(entered)
    operator_gates.record_hand_answer(run, "docs/context.md", "answered by a person", "abc123")
    gates = operator_gates.operator_gates_of(run)
    note(
        "library.txt",
        f"entered={''.join(entered)}",
        f"cycle={''.join(found[0]['cycle'])} x{found[0]['repeats']}",
        f"render={judge.render('Score {{who}} on {{n}}', who='a', n='2')}",
        f"members={len(tree.stage_members(run))}",
        f"gate={gates[0]['gate']} {gates[0]['action']} {gates[0]['commit']}",
        f"repos={sorted(tree.repos_at(run.stage, ()))}",
    )
'''

SEED = Seed(
    {
        "config.toml": 'config_version = 2\npaddock_dir = "<sandbox>/root"\n',
        "home/.keep": "",
        "root/gold/acme/home-config.toml": 'config_version = 2\ndefault_cli = "claude"\nartifacts_dir = "docs"\n',
        "root/gold/acme/tasks.py": TASKS,
        "root/gold/acme/data/README.md": "acme data\n",
        "sbx/apps/api/.keep": "",
        "sbx/apps/web/.keep": "",
        "sbx/other/api/.keep": "",
        "sbx/config-none.toml": "config_version = 2\n",
        "sbx/config-claude.toml": 'config_version = 2\n[profiles.p]\ncli = "claude"\n',
        "sbx/config-opencode.toml": 'config_version = 2\n[profiles.p]\ncli = "opencode"\n',
        "sbx/config-gemini.toml": 'config_version = 2\n[profiles.p]\ncli = "gemini"\n',
    },
    name="acme",
)

TOOLS = str(Path(sys.executable).parent)

ENVIRONMENT = {
    "PATH": f"{TOOLS}{os.pathsep}{os.environ.get('PATH', '')}",
    "HOME": "<sandbox>/home",
    "STABLEMATE_CONFIG": "<sandbox>/config.toml",
    "GIT_AUTHOR_NAME": "acme",
    "GIT_AUTHOR_EMAIL": "acme@example.com",
    "GIT_COMMITTER_NAME": "acme",
    "GIT_COMMITTER_EMAIL": "acme@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}


class PaddockCli(CommandSurface):
    def __init__(self, environment: Environment):
        super().__init__(SEED, ENVIRONMENT)
