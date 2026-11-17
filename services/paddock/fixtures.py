"""What a user types after the command name, as the model reads it. A field is
named as the argument is, and left None where the user leaves the flag out."""

from __future__ import annotations

from dataclasses import dataclass, field

from ostler.book import Fixture

BENCHMARK = "acme"
APPS = "sbx/apps"
OTHER = "sbx/other"
PRESENT = (f"{APPS}/api", f"{APPS}/web", f"{OTHER}/api")
NO_LOGIN = "sbx/config-none.toml"
CLAUDE = "sbx/config-claude.toml"
OPENCODE = "sbx/config-opencode.toml"
GEMINI = "sbx/config-gemini.toml"
CONFIGS = (NO_LOGIN, CLAUDE, OPENCODE, GEMINI)
LOGINS = {CLAUDE: ("claude",), OPENCODE: ("opencode",), GEMINI: ("gemini",)}


@dataclass
class ListArgs(Fixture):
    pass


@dataclass
class RunArgs(Fixture):
    benchmark: str | None = BENCHMARK
    task: str | None = "plain"
    no_pin_project: bool | None = True
    quiet: bool | None = True


@dataclass
class RunStepArgs(Fixture):
    task: str | None = "failing"
    no_pin_project: bool | None = True
    quiet: bool | None = True

    @property
    def benchmark(self) -> str:
        return BENCHMARK


@dataclass
class ResumeArgs(Fixture):
    benchmark: str | None = BENCHMARK
    task: str | None = "interrupt"
    n: int | None = None
    quiet: bool | None = True


@dataclass
class SandboxRunArgs(Fixture):
    apps: list[str] = field(default_factory=lambda: [f"{APPS}/api"])
    workdir: str | None = None
    runs_dir: str | None = "sbx/out"
    config: str | None = NO_LOGIN
    credentials: str | None = None
    command: str | None = "true"

    @property
    def names(self) -> list[str]:
        return [app.rsplit("/", 1)[-1] for app in self.apps]

    @property
    def count(self) -> int:
        return len(self.apps)

    @property
    def listed(self) -> str:
        return ", ".join(self.names)

    @property
    def logins(self) -> tuple[str, ...]:
        return LOGINS.get(self.config or "", ())

    @property
    def refusals(self) -> str:
        found: list[str] = []
        seen: set[str] = set()
        for app, name in zip(self.apps, self.names):
            if name in seen:
                found.append(f"two --app directories are named {name}, so they would share /work/{name}. Rename one")
            seen.add(name)
        for app, name in zip(self.apps, self.names):
            if app not in PRESENT:
                found.append(f"{app} does not exist. Create it, or name another path for /work/{name}")
        for cli in self.logins:
            if cli == "claude" and self.credentials is None:
                found.append("<sandbox>/home/.claude/.credentials.json does not exist. Create it, or name another path "
                             "for /tmp/sandbox-home/.claude/.credentials.json")
            if cli == "opencode":
                found.append("<sandbox>/home/.local/share/opencode/auth.json does not exist. Create it, or name another "
                             "path for /tmp/sandbox-home/.local/share/opencode/auth.json")
        return "\n".join(found)


def run(task: str | None = "plain", *, benchmark: str | None = BENCHMARK, pinned: bool = False) -> RunArgs:
    return RunArgs(benchmark=benchmark, task=task, no_pin_project=None if pinned else True)


def run_step(task: str | None = "failing") -> RunStepArgs:
    return RunStepArgs(task=task)


def resume(task: str | None = "interrupt", *, benchmark: str | None = BENCHMARK, n: int | None = None) -> ResumeArgs:
    return ResumeArgs(benchmark=benchmark, task=task, n=n)


def sandbox_run(*apps: str, workdir: str | None = None, config: str | None = NO_LOGIN, credentials: str | None = None,
                command: str | None = "true") -> SandboxRunArgs:
    return SandboxRunArgs(apps=list(apps) or [f"{APPS}/api"], workdir=workdir, config=config, credentials=credentials,
                          command=command)
