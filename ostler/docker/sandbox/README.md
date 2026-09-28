# sandbox

The QA sandbox image a scenario runs in. What it leaves out is the control: no repo, no toolchain and no package index.

## Map

- `Dockerfile`: what the `base` and `browser` sandbox images contain, and what they leave out.
- `entrypoint.sh`: starting the loopback forwarder when one is asked for, then handing PID 1 to the scenario.
- `forwarder.py`: the loopback ports inside the sandbox and the named upstream each one forwards to.
