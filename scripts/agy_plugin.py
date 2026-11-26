#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIBRARY = REPO / "base-library"
CONFIG = REPO / "scripts" / "agy_plugin.toml"
NAME = "stablemate"
DESCRIPTION = (
    "The stablemate agent toolchain: workhorse workflows, farrier, groom, ostler and "
    "saddlebag, with the stablemate base library's skills and the groom MCP server."
)
SKILL_LIMIT = 24 * 1024
TOOLS = (
    "farrier",
    "groom",
    "groom-sidecar",
    "ostler",
    "saddlebag",
    "workhorse-loop-runner",
    "workhorse-research",
    "workhorse-author",
    "workhorse-coder",
    "workhorse-okf-book",
    "workhorse-review-debt",
    "workhorse-new",
)
CONFIG_HOME = ".gemini/config/"
GUARD_HOME = ".agents/hooks/"
PLACES = (
    (CONFIG_HOME + "AGENTS.md", "rules/AGENTS.md"),
    (CONFIG_HOME, ""),
    (GUARD_HOME, "hooks/"),
)
LEFT_OUT = (".agents/.farrier-home.json",)
PACKAGES = (
    "ostler",
    "workhorse-agent",
    "farrier",
    "workhorse-workflows",
    "stablemate-groom",
    "stablemate-saddlebag",
    "stablemate",
)
LAUNCHER = (
    '#!/bin/sh\nSTABLEMATE_WHEELS="$(cd "$(dirname "$0")/../wheels" && pwd)"\nexport STABLEMATE_WHEELS\n'
    '{drive}exec uvx --overrides "$STABLEMATE_WHEELS/overrides.txt" --from "$STABLEMATE_WHEELS/{main}" {tool} "$@"\n'
)
DRIVE_AGY = 'export AGENT_CLI="${AGENT_CLI:-antigravity}"\n'
TOOL_CALL = re.compile(r"(?<=')(" + "|".join(re.escape(tool) for tool in TOOLS) + r")(?=[ '])")


def render_home(farrier: str, config: Path, home: Path) -> None:
    env = {key: value for key, value in os.environ.items() if key != "FARRIER_LIBRARY_DIR"}
    env["STABLEMATE_CONFIG"] = str(config)
    command = [*shlex.split(farrier), "install", "--user", "--library", str(LIBRARY), "--home", str(home)]
    subprocess.run(command, env=env, cwd=REPO, check=True)


def placed(rel: str) -> str | None:
    if rel in LEFT_OUT:
        return None
    for home_rel, target in PLACES:
        if rel == home_rel or (home_rel.endswith("/") and rel.startswith(home_rel)):
            return target + rel[len(home_rel):]
    raise SystemExit(f"error: the home render wrote {rel}, which has no place in the plugin.")


def relative(text: str, home: Path) -> str:
    text = text.replace(f"{home}/{CONFIG_HOME}", "").replace(f"{home}/{GUARD_HOME}", "hooks/")
    return TOOL_CALL.sub(r"bin/\1", text)


def launch_servers(text: str) -> str:
    document = json.loads(text)
    for server in document.get("mcpServers", {}).values():
        if server.get("command") in TOOLS:
            server["args"] = ["${PLUGIN_ROOT}/bin/" + server["command"], *server.get("args", [])]
            server["command"] = "sh"
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def build_wheels(folder: Path) -> tuple[str, ...]:
    wheels = folder / "wheels"
    for package in PACKAGES:
        subprocess.run(
            ["uv", "build", "--quiet", "--package", package, "--wheel", "--out-dir", str(wheels)],
            cwd=REPO,
            check=True,
        )
    return tuple(sorted(path.name for path in wheels.glob("*.whl")))


def overrides(wheels: tuple[str, ...]) -> str:
    return "".join(f"{wheel.split('-')[0].replace('_', '-')} @ ${{STABLEMATE_WHEELS}}/{wheel}\n" for wheel in wheels)


def launcher(tool: str, wheels: tuple[str, ...]) -> str:
    drive = DRIVE_AGY if tool.startswith("workhorse-") else ""
    (main,) = [wheel for wheel in wheels if wheel.split("-")[0] == NAME]
    return LAUNCHER.format(drive=drive, main=main, tool=tool)


def oversized(out: Path) -> list[str]:
    return [
        f"{path.relative_to(out)} ({path.stat().st_size / 1024:.1f} KB)"
        for path in sorted(out.glob("skills/*/SKILL.md"))
        if path.stat().st_size > SKILL_LIMIT
    ]


def assemble(home: Path, out: Path, version: str, wheels: tuple[str, ...]) -> None:
    for path in sorted(home.rglob("*")):
        if not path.is_file():
            continue
        target = placed(path.relative_to(home).as_posix())
        if target is None:
            continue
        destination = out / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        if target in ("hooks.json", "mcp_config.json"):
            text = relative(path.read_text(encoding="utf-8"), home)
            destination.write_text(launch_servers(text) if target == "mcp_config.json" else text, encoding="utf-8")
        else:
            shutil.copy2(path, destination)
    (out / "wheels").mkdir(parents=True, exist_ok=True)
    (out / "wheels" / "overrides.txt").write_text(overrides(wheels), encoding="utf-8")
    for tool in TOOLS:
        script = out / "bin" / tool
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(launcher(tool, wheels), encoding="utf-8")
        script.chmod(0o755)
    manifest = {"name": NAME, "version": version, "description": DESCRIPTION}
    (out / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    absolute = sorted(
        str(path.relative_to(out))
        for path in out.rglob("*")
        if path.is_file() and path.suffix != ".whl" and str(home) in path.read_text(encoding="utf-8", errors="ignore")
    )
    if absolute:
        raise SystemExit(f"error: these plugin files name the render folder: {', '.join(absolute)}")
    long = oversized(out)
    if long:
        raise SystemExit(
            f"error: Antigravity reads only the first {SKILL_LIMIT // 1024} KB of a skill, and these "
            f"are longer: {', '.join(long)}. Split each into an entry skill and reference files."
        )


def validate(folder: Path) -> None:
    if shutil.which("agy") is None:
        print("agy is not installed here, so the plugin was not validated", file=sys.stderr)
        return
    subprocess.run(["agy", "plugin", "validate", "--strict", str(folder)], check=True)


def archive(folder: Path, out: Path, version: str) -> Path:
    zipped = out / f"{NAME}-antigravity-{version}.zip"
    with zipfile.ZipFile(zipped, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(folder).as_posix(), (1980, 1, 1, 0, 0, 0))
                info.external_attr = (path.stat().st_mode & 0o777) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                bundle.writestr(info, path.read_bytes())
    digest = hashlib.sha256(zipped.read_bytes()).hexdigest()
    (out / f"{zipped.name}.sha256").write_text(f"{digest}  {zipped.name}\n", encoding="utf-8")
    return zipped


def released_version() -> str:
    with (REPO / "stablemate" / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def clear(out: Path) -> None:
    if not out.exists():
        return
    if any(out.iterdir()) and not (out / NAME / "plugin.json").is_file():
        raise SystemExit(f"error: {out} holds files but no earlier plugin build, so it was left alone.")
    shutil.rmtree(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Antigravity plugin from the base library and the stablemate tools."
    )
    parser.add_argument("--version", default=None, help="the version the plugin carries")
    parser.add_argument("--out", type=Path, default=REPO / "dist" / "antigravity")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--farrier", default="uv run --all-packages farrier")
    args = parser.parse_args(argv)
    version = args.version or released_version()
    out = args.out.resolve()
    clear(out)
    folder = out / NAME
    folder.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as scratch:
        config = Path(scratch) / "config.toml"
        shutil.copy2(args.config, config)
        home = Path(scratch) / "home"
        home.mkdir()
        render_home(args.farrier, config, home)
        assemble(home, folder, version, build_wheels(folder))
    validate(folder)
    zipped = archive(folder, out, version)
    print((out / f"{zipped.name}.sha256").read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
