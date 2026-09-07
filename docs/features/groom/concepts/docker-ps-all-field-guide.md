---
type: concept
slug: docker-ps-all-field-guide
title: Docker ps all field guide
---
# Docker ps all field guide

The three fields document complementary stages of one `docker_ps_all` read; none is an
alternative implementation or a replacement for another. The command field identifies the
fixed argv sent to Docker. The stdout-lines field describes the successful process output before
line filtering and decoding. The parsed-entries field describes the values retained after empty
and malformed lines are skipped. Read the field for the stage whose value is needed.

The source builds the command, returns immediately on a non-zero Docker exit, then processes
each stdout line in order and appends only values that JSON decoding accepts. Consequently,
the stdout-lines and parsed-entries fields apply only after a zero-exit command; the latter is a
filtered result of the former, not a competing listing source.

- code: `groom/groom/docker_io.py::docker_ps_all`
- rule: use the command field for Docker invocation, stdout lines for successful raw output, and parsed entries for the retained decoded result; no field supersedes another.
