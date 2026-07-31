"""The sentinel gate's diff reader — `_added_lines`.

The version this pins replaces a hand-written scan whose every branch was a `startswith`
test on a raw diff line. That is a claim about where a line sits in the file, and a hunk
*body* can forge any of them: an added line whose own content begins `+++ b/` or `@@ `
re-pointed the filename and the line counter at whatever that content said. The gate then
reported a real sentinel under a filename that does not exist, or missed it entirely. Only
one seam is faked here — `diff_text`, the process boundary — so what is under test is the
parse, on diffs `git` really emits.
"""
from __future__ import annotations

import pytest

from workhorse_workflows.coder.qa.nodes import hygiene


def _lines(monkeypatch, diff: str):
    monkeypatch.setattr(hygiene, "diff_text", lambda *a, **k: diff)
    return hygiene._added_lines(hygiene.Path("."), "base")


DIFF = """\
diff --git a/api-service/handler.go b/api-service/handler.go
index 1111111..2222222 100644
--- a/api-service/handler.go
+++ b/api-service/handler.go
@@ -12,0 +34 @@ func Serve() {
+\tconst tenant = "00000000-0000-0000-0000-000000000000"
@@ -40,0 +63,2 @@ func Close() {
+\t// TODO until the registry lands
+\treturn nil
"""


def test_added_lines_carry_their_target_line_numbers(monkeypatch):
    """`@@ -12,0 +34 @@` — the old side is spelled without a comma, so a `\\+(\\d+)` search
    over the header text finds `+34` only by luck of ordering; the parser reads the field."""
    assert _lines(monkeypatch, DIFF) == [
        ("api-service/handler.go", 34, '\tconst tenant = "00000000-0000-0000-0000-000000000000"'),
        ("api-service/handler.go", 63, "\t// TODO until the registry lands"),
        ("api-service/handler.go", 64, "\treturn nil"),
    ]


NESTED = """\
diff --git a/web-app/testdata/sample.diff b/web-app/testdata/sample.diff
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/web-app/testdata/sample.diff
@@ -0,0 +1,3 @@
++++ b/not/a/real/file.ts
+@@ -1,0 +900 @@
++const stub = "placeholder until the API exists";
"""


def test_a_diff_committed_as_a_fixture_does_not_forge_a_filename(monkeypatch):
    """Every line here is hunk *content*. The scan read lines 1 and 2 as headers, and
    attributed the sentinel on line 3 to `not/a/real/file.ts:900`."""
    assert _lines(monkeypatch, NESTED) == [
        ("web-app/testdata/sample.diff", 1, "+++ b/not/a/real/file.ts"),
        ("web-app/testdata/sample.diff", 2, "@@ -1,0 +900 @@"),
        ("web-app/testdata/sample.diff", 3, '+const stub = "placeholder until the API exists";'),
    ]


RENAME = """\
diff --git a/web-app/old.ts b/web-app/new.ts
similarity index 100%
rename from web-app/old.ts
rename to web-app/new.ts
diff --git a/web-app/logo.png b/web-app/logo.png
index 4444444..5555555 100644
Binary files a/web-app/logo.png and b/web-app/logo.png differ
"""


def test_renames_and_binaries_add_no_lines(monkeypatch):
    """Both yield a file with no hunks — nothing to scan for a sentinel, and no crash."""
    assert _lines(monkeypatch, RENAME) == []


def test_no_diff_and_a_malformed_diff_both_yield_nothing(monkeypatch):
    """Fail soft: this gate runs unattended, and a patch it cannot read is not a defect
    it may report. `--unified=0` output it *can* read is the only evidence it acts on."""
    assert _lines(monkeypatch, "") == []
    assert _lines(monkeypatch, "@@ -1 +1 @@\n+orphan hunk, no file header\n") == []


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
