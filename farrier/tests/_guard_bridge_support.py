import json
import subprocess
from pathlib import Path


def add_guard(
    library: Path, name: str, script: str, record: str = "watches: [shell, edit]\n"
) -> None:
    folder = library / "library" / "hooks" / name
    folder.mkdir(parents=True)
    (folder / "hook.yml").write_text(
        f"command: sh {{dir}}/check.sh\n{record}timeout: 5\n", encoding="utf-8"
    )
    (folder / "check.sh").write_text(script, encoding="utf-8")


def read_hooks(config: Path) -> dict:
    return json.loads(config.read_text(encoding="utf-8"))["hooks"]


def run_hook(command: str, payload: dict) -> dict | None:
    done = subprocess.run(
        ["sh", "-c", command],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(done.stdout) if done.stdout.strip() else None
