"""Helper agents installed from one library record, on the model each harness's profile names."""

import tomllib
from pathlib import Path

import pytest
import yaml

from farrier.install import main

PROFILES = (
    '[profiles.claude]\ncli = "claude"\n\n'
    '[profiles.claude.delegates.lookup]\nmodel = "haiku-x"\n\n'
    '[profiles.claude.delegates.worker]\nmodel = "sonnet-x"\neffort = "medium"\n\n'
    '[profiles.codex]\ncli = "codex"\n\n'
    '[profiles.codex.delegates.lookup]\nmodel = "@luna"\neffort = "max"\n\n'
    '[profiles.codex.delegates.worker]\nmodel = "terra"\n\n'
)
BOTH = (
    '[user_library.claude]\nagents = ["lookup", "worker"]\n\n'
    '[user_library.codex]\nagents = ["lookup", "worker"]\n\n'
)


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    agents = root / "library" / "agents"
    agents.mkdir(parents=True)
    (root / "packs").mkdir()
    (agents / "lookup.md").write_text(
        '---\ndescription: "Read-only lookup: one narrow question."\nread_only: true\n---\n\n'
        "You answer one question.\n",
        encoding="utf-8",
    )
    (agents / "worker.md").write_text(
        "---\ndescription: Carries out a decided plan.\n---\n\nYou carry out a plan.\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    monkeypatch.setenv("STABLEMATE_FETCH_BASE", "0")
    monkeypatch.setenv("STABLEMATE_CONFIG", str(tmp_path / "config.toml"))
    return path


def install(home: Path, library: Path, config: str, *flags: str) -> int:
    (home.parent / "config.toml").write_text(config, encoding="utf-8")
    return main(["--user", "--home", str(home), "--library", str(library), *flags])


def claude_head(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---\n")[1])


def test_one_record_lands_on_each_harness_with_its_own_model(home: Path, library: Path) -> None:
    assert install(home, library, PROFILES + BOTH) == 0
    assert claude_head(home / ".claude/agents/lookup.md")["model"] == "haiku-x"
    assert claude_head(home / ".claude/agents/worker.md")["effort"] == "medium"
    codex = tomllib.loads((home / ".codex/agents/lookup.toml").read_text(encoding="utf-8"))
    assert codex["name"] == "lookup"
    assert codex["description"] == "Read-only lookup: one narrow question."
    assert codex["model"] == "luna"
    assert codex["model_reasoning_effort"] == "high"
    assert tomllib.loads((home / ".codex/agents/worker.toml").read_text(encoding="utf-8"))["model"] == "terra"


def test_read_only_restricts_tools_on_claude_and_goes_in_the_prompt_on_codex(
    home: Path, library: Path
) -> None:
    assert install(home, library, PROFILES + BOTH) == 0
    assert claude_head(home / ".claude/agents/lookup.md")["tools"] == "Read, Grep, Glob, Bash"
    assert "Edit, Write" in claude_head(home / ".claude/agents/worker.md")["tools"]
    lookup = tomllib.loads((home / ".codex/agents/lookup.toml").read_text(encoding="utf-8"))
    worker = tomllib.loads((home / ".codex/agents/worker.toml").read_text(encoding="utf-8"))
    assert lookup["developer_instructions"].startswith("Read only.")
    assert lookup["developer_instructions"].rstrip().endswith("You answer one question.")
    assert "sandbox_mode" not in lookup
    assert worker["developer_instructions"] == "You carry out a plan.\n"


def test_a_role_with_no_model_stops_the_install_and_names_the_table(
    home: Path, library: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = '[profiles.codex]\ncli = "codex"\n\n[user_library.codex]\nagents = ["lookup"]\n'
    with pytest.raises(SystemExit, match=r"\[profiles\.codex\.delegates\.lookup\] names no model"):
        install(home, library, config)
    assert not (home / ".codex/agents").exists()


def test_copilot_cannot_take_agents(home: Path, library: Path) -> None:
    with pytest.raises(SystemExit, match="only for claude, codex"):
        install(home, library, PROFILES + '[user_library.copilot]\nagents = ["lookup"]\n')


def test_an_unknown_agent_and_a_strange_record_key_stop_the_install(home: Path, library: Path) -> None:
    with pytest.raises(SystemExit, match="unknown agent 'ghost'. Available: lookup, worker"):
        install(home, library, PROFILES + '[user_library.claude]\nagents = ["ghost"]\n')
    (library / "library/agents/lookup.md").write_text(
        "---\ndescription: x\nmodel: haiku\n---\n\nprompt\n", encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="unknown keys: model"):
        install(home, library, PROFILES + BOTH)


def test_a_hand_written_agent_stops_the_install_and_survives(home: Path, library: Path) -> None:
    mine = home / ".claude/agents/lookup.md"
    mine.parent.mkdir(parents=True)
    mine.write_text("---\nname: lookup\n---\n\nmine\n", encoding="utf-8")
    other = home / ".claude/agents/mine.md"
    other.write_text("---\nname: mine\n---\n\nkeep\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="will not overwrite"):
        install(home, library, PROFILES + BOTH)
    assert mine.read_text(encoding="utf-8").endswith("mine\n")
    mine.unlink()
    assert install(home, library, PROFILES + BOTH) == 0
    assert other.read_text(encoding="utf-8").endswith("keep\n")


def test_check_reports_drift_and_writes_nothing(
    home: Path, library: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert install(home, library, PROFILES + BOTH) == 0
    capsys.readouterr()
    assert install(home, library, PROFILES + BOTH, "--check") == 0
    changed = PROFILES.replace("@luna", "@sol") + BOTH
    before = (home / ".codex/agents/lookup.toml").read_text(encoding="utf-8")
    assert install(home, library, changed, "--check") == 1
    assert ".codex/agents/lookup.toml" in capsys.readouterr().out
    assert (home / ".codex/agents/lookup.toml").read_text(encoding="utf-8") == before


def test_a_dropped_agent_goes_away_and_a_pack_selects_one(home: Path, library: Path) -> None:
    assert install(home, library, PROFILES + BOTH) == 0
    (library / "packs/helpers.yml").write_text("agents: [lookup]\n", encoding="utf-8")
    config = PROFILES + '[user_library.codex]\npacks = ["helpers"]\n'
    assert install(home, library, config) == 0
    assert (home / ".codex/agents/lookup.toml").is_file()
    assert not (home / ".codex/agents/worker.toml").exists()
    assert not (home / ".claude/agents/lookup.md").exists()
