"""Package marker.

`tests/author/` and `tests/research/` both carry a `test_workflow.py`, so without this
the three would collide on one module name under pytest's rootdir-relative import mode.
"""
