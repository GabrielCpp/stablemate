#!/usr/bin/env python3
"""Guard the declared-fixture rule across the benchmark corpus."""

from __future__ import annotations

import sys

from paddock import loader, paths
from paddock.fixtures import check_app


def main() -> int:
    root = paths.root()
    if not paths.gold_dir(root).exists():
        print(f"ok: no benchmark corpus at {paths.gold_dir(root)}, skipped")
        return 0

    apps = loader.data_repos(root)
    if not apps:
        print(f"check-fixtures: no benchmark repos under {paths.gold_dir(root)}", file=sys.stderr)
        return 1

    problems = [problem for app in apps for problem in check_app(app)]
    if problems:
        print("check-fixtures: declared-fixture rule violated\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"ok: fixture declarations agree with the tree in {len(apps)} benchmark apps")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
