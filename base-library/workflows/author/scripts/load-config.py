#!/usr/bin/env python3
"""Load author-workflow config and validate the backlog exists → `cfg`.

Start node of the author workflow. Resolves the repo root (the consuming repo, not
the shared library), reads project facts from ``agents.yml`` (``template.*``), and
verifies the backlog markdown file the run was pointed at actually exists — failing
fast with a clear message rather than letting downstream agents hallucinate scope
from an empty file.

The optional ``template.knowledge_dir`` value is passed through verbatim into ``cfg``
so prompts — and especially a repo's author *flavor* overrides — can read it. The base
workflow does NOT branch on it: any repo-specific behavior lives in that repo's
``.agents/flavors/author/`` prompts, not here. Grounding is always against the OKF
graph via ostler, and ostler owns id allocation (prefix derived from the repo name).

Stdlib-only: scripts run under the system ``python3``, not the uv venv.

Args:
    argv[1]  backlog   : repo-relative path to the markdown backlog (REQUIRED)
    argv[2]  epics_dir : epics root (default docs/epics)

Outputs JSON: {"cfg": {repo_root, backlog_path, epics_dir, knowledge_dir,
                       surface_manifest, features_dir, mockup_dir, layers}}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path


def find_repo_root() -> Path:
    # AGENT_REPO_DIR is pinned to the consuming repo by the makefile; the script's own
    # location points into the shared library, so prefer the env var.
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def load_template(root: Path) -> dict:
    cfg_path = root / "agents.yml"
    if not cfg_path.is_file():
        return {}
    try:
        import yaml  # available in the local-worker runtime
    except Exception:
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def main(logger: logging.Logger) -> None:
    # Default to docs/backlog.md; override with --params '{"backlog":"..."}'.
    backlog = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/backlog.md"
    epics_dir = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/epics"

    root = find_repo_root()
    backlog_path = (root / backlog).resolve()
    if not backlog_path.is_file():
        logger.warning("backlog file not found: %s", backlog_path)
        sys.exit(
            f"[load-config] backlog file not found: {backlog_path}\n"
            f"Create {backlog} (a markdown bullet list of features) before running the author "
            f"workflow, or pass --params '{{\"backlog\":\"<path>\"}}'."
        )

    data = load_template(root)
    template = data.get("template") or {}

    # Where the accumulating surface-knowledge records live (the derived, machine-built
    # source of truth — distinct from the hand-curated, read-only `features/`). Repo can
    # override via template.knowledge_dir; defaults beside the epics under docs/knowledge.
    knowledge_dir = template.get("knowledge_dir") or "docs/knowledge"

    # Convention defaults (shipped library-wide, a repo may override in agents.yml). These
    # are plain path defaults — the features the gates drive stay inert until the referenced
    # file actually exists on disk, so a greenfield repo that hasn't authored them is unaffected.
    #   - surface_manifest: machine-readable inventory of the site's surfaces; the
    #     backlog-coverage gate (verify-surface-coverage.py) checks every in-scope surface is
    #     covered by some backlog/epic/story. Absent file ⇒ gate skips. Two producers share
    #     the contract: the legacy feature inventory, and the surveyor workflow's unit
    #     manifest (docs/survey/unit-manifest.json) — when the template does not pin a path
    #     and a survey manifest exists on disk, it is picked up by presence, so a surveyed
    #     repo flows into `coverage_mode: "full"` with zero config.
    #   - features_dir: human-curated feature/journey docs the author grounds ACs in. Absent
    #     dir ⇒ feature-doc grounding stays inert.
    #   - mockup_dir: greenfield visual reference — for a genuinely new screen, the reference
    #     image is a design mockup under this dir, resolved per surface from the manifest
    #     entry's `mockup` field.
    surface_manifest = template.get("surface_manifest") or ""
    if not surface_manifest:
        survey_manifest = "docs/survey/unit-manifest.json"
        surface_manifest = (
            survey_manifest if (root / survey_manifest).is_file() else "docs/features/inventory.json"
        )
    features_dir = template.get("features_dir") or "docs/features"
    mockup_dir = template.get("mockup_dir") or "docs/design"

    # Best-effort layer list (used only for layer-aware prompt hints). The prompts use
    # isUsingInstruction() at install time for the authoritative selection; this is a hint.
    layers = []
    for li in (data.get("localInstructions") or []):
        if isinstance(li, dict) and li.get("skill"):
            layers.append(str(li["skill"]))

    cfg = {
        "repo_root": str(root),
        "backlog_path": backlog,
        "epics_dir": epics_dir,
        "knowledge_dir": str(knowledge_dir),
        "surface_manifest": str(surface_manifest),
        "features_dir": str(features_dir),
        "mockup_dir": str(mockup_dir),
        "layers": layers,
    }
    logger.info("loaded config for %s (knowledge_dir=%s, features_dir=%s, %d layer(s))",
                root, knowledge_dir, features_dir, len(layers))
    print(json.dumps({"cfg": cfg}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("load-config"))
