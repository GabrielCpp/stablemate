#!/bin/bash
# Bring up the loopback forwarder, then become the scenario process.
#
# `exec` at the end is load-bearing: the scenario has to be PID 1 so that `docker kill`
# on a timeout reaches *it*, not a shell that would be killed while the scenario it
# spawned kept running inside a container ostler has already stopped watching.
set -euo pipefail

READY=/tmp/ostler-forwarder.ready

if [[ -n "${OSTLER_SANDBOX_FORWARD:-}" ]]; then
    rm -f "$READY"
    python3 /opt/ostler-sandbox/forwarder.py "$READY" &
    for _ in $(seq 1 100); do
        [[ -f "$READY" ]] && break
        sleep 0.1
    done
    if [[ ! -f "$READY" ]]; then
        echo "sandbox: port forwarder did not bind within 10s" >&2
        exit 70
    fi
fi

exec "$@"
