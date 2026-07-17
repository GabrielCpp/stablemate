#!/usr/bin/env python3
"""Scaffold a new research program folder from the canonical templates.

A research program is one self-contained folder in the target repo (1 folder =
1 program), consumed by the generic research workflow. This stamps the exact
layout `load_config` + the gate-loop prompts expect, so the manifest, headers,
gate-doc format, and (optionally) the `.agents/program` selection pointer never
depend on an agent remembering them.

Usage (typically via `make research-new`):
  new_program.py --repo <repo> --dir specs/my-program --code-root src/mypkg \\
      [--name "Foo Program"] [--gate G0] [--progress <repo-rel path>] \\
      [--result-branch <branch>] [--set-default] [--force]

Writes under <repo>/<dir>:
  program.yml · README.md · PROGRESS.md (at --progress if given) · <gate>_program.md · findings/

Stdlib-only: runs under the system python3.
"""
import argparse
import datetime
import logging
import os
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def slug(program_dir: str) -> str:
    parts = [p for p in program_dir.split("/") if p not in (".", "", "specs")]
    return "-".join(parts) if parts else program_dir.replace("/", "-")


def render(name: str, repl: dict[str, str]) -> str:
    text = (TEMPLATES / name).read_text()
    for k, v in repl.items():
        text = text.replace(k, v)
    return text


def write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        sys.exit(f"[new_program] refusing to overwrite {path} (pass --force)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"  wrote {path}")


def main(logger: logging.Logger) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.environ.get("AGENT_REPO_DIR") or ".")
    ap.add_argument("--dir", required=True, help="repo-relative program dir, e.g. specs/my-program")
    ap.add_argument("--code-root", required=True, help="repo-relative source dir, e.g. src/mypkg")
    ap.add_argument("--name", default="", help="human program name (default: derived from dir)")
    ap.add_argument("--gate", default="G0", help="first gate id (default: G0)")
    ap.add_argument("--progress", default="", help="override progress_path (repo-relative)")
    ap.add_argument("--result-branch", default="", help="override result_branch")
    ap.add_argument("--set-default", action="store_true", help="point <repo>/.agents/program at this program")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    program_dir = args.dir.strip("/")
    abs_dir = repo / program_dir
    name = args.name or program_dir.split("/")[-1].replace("-", " ").replace("_", " ").title()
    progress_path = args.progress.strip("/") or f"{program_dir}/PROGRESS.md"
    result_branch = args.result_branch or f"{slug(program_dir)}/auto"
    gate = args.gate
    repl = {
        "__PROGRAM_NAME__": name,
        "__PROGRAM_DIR__": program_dir,
        "__CODE_ROOT__": args.code_root.strip("/"),
        "__GATE_ID__": gate,
        "__GATE_SLUG__": "program",
        "__PROGRESS_PATH__": progress_path,
        "__RESULT_BRANCH__": result_branch,
        "__DATE__": datetime.date.today().isoformat(),
    }

    # program.yml is generated directly (tiny) so overrides land uncommented.
    manifest = [f"# {name} — research program manifest (read by load_config). 1 folder = 1 program.",
                f"code_root: {args.code_root.strip('/')}"]
    if args.progress:
        manifest.append(f"progress_path: {progress_path}")
    if args.result_branch:
        manifest.append(f"result_branch: {result_branch}")

    logger.info("scaffolding %s (repo=%s)", program_dir, repo)
    write(abs_dir / "program.yml", "\n".join(manifest) + "\n", args.force)
    write(abs_dir / "README.md", render("README.md", repl), args.force)
    write(repo / progress_path, render("PROGRESS.md", repl), args.force)
    write(abs_dir / f"{gate}_program.md", render("gate.md", repl), args.force)
    findings = abs_dir / "findings"
    if not findings.exists():
        findings.mkdir(parents=True, exist_ok=True)
        print(f"  created {findings}")

    if args.set_default:
        pointer = repo / ".agents" / "program"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(
            "# Active research program for `make agent-native`. Edit to switch.\n"
            f"{program_dir}\n"
        )
        logger.info("set default program -> %s", pointer)

    logger.info(
        "done. Next: fill README ladder + %s thresholds, then\n"
        "  make agent-native%s",
        gate,
        "" if args.set_default else f" PARAMS='{{\"program\":\"{program_dir}\"}}'",
    )


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("new_program"))
