"""The process boundary: `python -m tally`.

Everything `main` can raise is already translated into an exit code by `main` itself, so this
module has exactly one job — hand that code to the interpreter. Nothing else belongs here,
because anything that did would be unreachable from an in-process test.
"""

from tally.cli import main


raise SystemExit(main())
