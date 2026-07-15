"""The base library must be usable with NO private overlay configured.

This is the guard that keeps the public/private split honest. The base ships in a
wheel that anyone can `pip install`; the overlay is a private repo only the maintainer
has. Nothing in the base may therefore depend on the overlay — not a pack it does not
define, not a skill it cannot resolve, and not a client's name in its prose.

Without this test the coupling comes back silently: a base workflow starts referencing
an overlay skill, everything keeps working on the maintainer's machine (where the
overlay is configured and shadows everything), and the break only shows up for a
public user who has no overlay at all.

Run directly (no pytest required):
    uv run python tests/test_base_stands_alone.py
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

from farrier import install
from stablemate_library import base_dir

# Every text format the base ships: prose (md), graphs/configs (yml), and the
# workflow scripts (py/sh). A leak hides just as well in a script comment.
TEXT_SUFFIXES = (".md", ".yml", ".yaml", ".py", ".sh", ".json", ".toml", ".txt")

BASE = base_dir()

# The overlay's project names are deliberately absent from this file. stablemate is
# public, and a denylist publishes the words it bans just as surely as a leak does.
# scripts/private_names.py reads them from an untracked source instead — see its
# docstring. Unconfigured (the public-contributor case), there is nothing to check.
RESOLVER = Path(__file__).resolve().parents[2] / "scripts" / "private_names.py"


def _private_names_module():
    spec = importlib.util.spec_from_file_location("private_names", RESOLVER)
    assert spec and spec.loader, f"cannot load the name resolver at {RESOLVER}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _isolate_from_the_overlay() -> None:
    """Resolve as a public user would: base only, no overlay in env or home config."""
    os.environ.pop("FARRIER_LIBRARY_DIR", None)
    install.CONFIG_PATH = Path(tempfile.mkdtemp()) / "config.toml"
    install.set_layers(None)
    assert [layer.name for layer in install.LAYERS] == [install.BASE_LAYER_NAME], (
        "the base library must be the only layer for this test to mean anything"
    )


def test_base_is_a_library():
    assert install.is_library_dir(BASE), f"{BASE} is not a usable library root"
    print("ok: the base is a usable library root")


def test_base_skills_resolve_with_no_overlay():
    _isolate_from_the_overlay()
    skills = install.load_layered_sources("skill", "library", "skills")
    assert skills, "the base library resolves no skills at all"
    for skill in skills:
        assert skill.layer.name == install.BASE_LAYER_NAME
        assert skill.id.startswith("stablemate/"), (
            f"skill {skill.id!r} is in the base but is not a stablemate/* skill — the "
            "base carries the toolchain's own skills; everything else is overlay content"
        )
    print(f"ok: {len(skills)} base skills resolve with no overlay configured")


def test_base_workflows_resolve_with_no_overlay():
    """Every workflow the base ships must be found by the same lookup workhorse uses."""
    _isolate_from_the_overlay()
    workflows_dir = BASE / "workflows"
    names = (
        sorted(p.name for p in workflows_dir.iterdir() if (p / "workflow.yaml").is_file())
        if workflows_dir.is_dir()
        else []
    )
    for name in names:
        assert install.find_in_layers("workflows", name) is not None
    print(f"ok: {len(names)} base workflows resolve with no overlay configured")


def test_base_names_no_private_project():
    """A skill promoted into the base must not carry a client's name with it.

    Structural checks cannot catch prose. This one is cheap and gets more valuable
    every time something is promoted out of the overlay.
    """
    private_names = _private_names_module()
    pattern = private_names.pattern(private_names.load())
    if pattern is None:
        print(
            f"skip: no private names configured (${private_names.ENV_VAR} or "
            f"$GIT_DIR/{private_names.GIT_FILE}) — nothing to check against"
        )
        return

    offenders: list[str] = []
    for path in BASE.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(BASE)}:{number}: {line.strip()}")
    assert not offenders, "private project names leaked into the base library:\n" + "\n".join(
        offenders
    )
    print("ok: no private project names in the base")


if __name__ == "__main__":
    failures = 0
    for test in (
        test_base_is_a_library,
        test_base_skills_resolve_with_no_overlay,
        test_base_workflows_resolve_with_no_overlay,
        test_base_names_no_private_project,
    ):
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    if failures:
        sys.exit(1)
    print("\nthe base library stands alone")
