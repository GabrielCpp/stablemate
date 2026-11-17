story: none
date: 2026-11-16
elements: Doctor

`farrier doctor` names the repository as typed, not resolved: `--repo .` reports "no agents.yml in .", and a call with
no `--repo` reports the working directory (`farrier/farrier/doctor.py::diagnose`). It reports an error and exits 1 only
when there is no agents.yml. Every config the book writes lacks a `services:` block, so the report is the one warning
and exit 0.
