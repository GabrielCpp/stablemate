"""Shared plumbing for the stablemate tools.

workhorse and farrier are independent CLIs — neither may import the other — but they
share runtime state: one home config file, one base-library cache directory, and one
resolution order for finding the base library. Anything both must AGREE about lives
here; anything either merely happens to do lives in that tool.

This package depends on nothing else in the workspace, and must not: ``workhorse ->
core`` and ``farrier -> core``, never back. It knows no workflow's vocabulary, no node
types, and nothing about the library's content — only where things live on disk.
"""

from __future__ import annotations
