"""Shared plumbing for the stablemate tools.

workhorse, farrier and ostler are independent CLIs — none may import another — but they
share runtime state: one home config file, one base-library cache directory, and one
resolution order for finding the base library. Anything they must AGREE about lives
here; anything one of them merely happens to do lives in that tool.

Agreement is not the only reason to be here. ``clock`` is here because it is plumbing
with no owner: a substitutable clock is the same three operations for every tool, and a
second hand-rolled copy is how two of them end up disagreeing about whether a deadline
is monotonic. What disqualifies a module is dependency, not subject matter — this package
depends on nothing else in the workspace and must not: ``workhorse -> core``,
``farrier -> core`` and ``ostler -> core``, never back. It knows no workflow's
vocabulary, no node types, and nothing about the library's content.

It is not published. Each tool carries a byte-identical copy of this directory under its
own ``_vendor/``, written by ``make vendor``, so **every import inside this package must
be relative**. An absolute ``from stablemate_core.x import y`` resolves to whatever copy
happens to be on ``sys.path`` — in a checkout that is this one, and the vendored copy
would silently reach back out of the wheel that contains it.
"""

from __future__ import annotations
