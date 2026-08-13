# The QA sandbox image: an interpreter, the harness, and nothing else.
#
# What makes this a control rather than a rule is what is *absent*. There is no repo
# mounted, no `go`, no `node`, no `npm`, no package index reachable by default — so a
# scenario cannot rerun a unit suite and call it behavioral evidence. It is not forbidden
# from doing so; it is unable to. That is the entire design.
#
# `jq` is absent and stays absent. It was never an ostler dependency — every `jq` expression
# in the corpus came from the retired YAML engine's shell heredocs — and its failure mode is
# the one this whole exercise is closing: a missing field reads as an empty stream, so an
# assertion over it passes having observed nothing. A scenario parses JSON in Python, where
# a missing key raises on the line that asked for it.
#
# The shell that remains is the base image's, used by the entrypoint below and by nothing
# else in the run: the harness never shells out, and `background:` daemons are argv lists
# started on the host by ostler, not command lines. There is no `bash -c` on any path a
# scenario reaches.
#
# Build context is the `ostler/` package directory:
#   docker build -f docker/sandbox/Dockerfile --target base   -t ostler-qa-sandbox:base    .
#   docker build -f docker/sandbox/Dockerfile --target browser -t ostler-qa-sandbox:browser .

# --------------------------------------------------------------------------------------
# base — command/HTTP scenarios
# --------------------------------------------------------------------------------------
FROM python:3.12.13-bookworm AS base

# Installed from disk on purpose. A sandbox that pip-installs ostler from an index at
# build time has a network dependency in the one place the whole point is not having one,
# and would silently drift from the working tree the run is testing.
COPY . /src/ostler
RUN python3 -m pip install --no-cache-dir /src/ostler && rm -rf /root/.cache

# Where `python -m ostler_qa` is found. The harness is stdlib-only and never imports
# ostler, so this is a directory on the path rather than a package import — the same
# contract it has on the host (see ostler/qa/harness_host.py).
ENV OSTLER_HARNESS_DIR=/usr/local/lib/python3.12/site-packages/ostler/qa/harness
ENV PYTHONPATH=/usr/local/lib/python3.12/site-packages/ostler/qa/harness
# Never write bytecode into the bind-mounted spec directory: it would appear next to
# qa_plan.py in the target repo's `git status`, owned by whatever uid the container ran as.
ENV PYTHONDONTWRITEBYTECODE=1

COPY docker/sandbox/forwarder.py /opt/ostler-sandbox/forwarder.py
COPY docker/sandbox/entrypoint.sh /opt/ostler-sandbox/entrypoint.sh
RUN chmod 0755 /opt/ostler-sandbox/entrypoint.sh

# Containers run as the invoking uid (`--user`) so that artifacts written into the
# bind-mounted spec dir belong to the human, not to root. That uid has no passwd entry,
# so HOME is set explicitly and points somewhere writable rather than at `/`.
ENV HOME=/tmp/sandbox-home
RUN mkdir -p /tmp/sandbox-home && chmod 0777 /tmp/sandbox-home

ENTRYPOINT ["/opt/ostler-sandbox/entrypoint.sh"]
CMD ["python3", "-m", "ostler_qa"]

# --------------------------------------------------------------------------------------
# browser — playwright scenarios, and the display sidecar that films them
# --------------------------------------------------------------------------------------
FROM base AS browser

# Xvfb and ffmpeg are here for the *sidecar* role: window recording cannot use the host's
# X display without punching a hole through the sandbox wall, so the display lives in a
# container of its own and this same image plays that part.
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb ffmpeg x11-utils \
    && rm -rf /var/lib/apt/lists/*

# A world-readable browser path, because the container runs as an arbitrary uid that has
# no home directory of its own to have installed into.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
RUN python3 -m pip install --no-cache-dir playwright \
    && python3 -m playwright install --with-deps chromium \
    && chmod -R a+rX /opt/pw-browsers \
    && rm -rf /root/.cache
