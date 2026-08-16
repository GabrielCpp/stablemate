# Where the pieces come from — the base library, a workflow's tools, the config file

The install itself is three commands, and they are in [README.md](../README.md#installing).
This document is what those commands resolve against: the four routes a tool takes to find
the base library and which one wins, why a workflow's tools are dependencies of the workflow
distribution rather than a manifest of their own, and the one config file every tool shares.

## Finding the base library

Tools resolve the base in this order, highest precedence first — the cache is last, so a
fetched copy can never shadow a checkout you are editing:

1. `$STABLEMATE_BASE_DIR` — an explicit path to the content on disk.
2. `<tool> config set-base <path>` — the persisted form of that path.
3. a configured `stablemate_dir` checkout (`<checkout>/base-library`).
4. the shared cache at `~/.cache/stablemate/library`.

A checkout install gets route 3 for free. Under `pipx`, where each tool is its own venv
and the base is data with no package to import, route 4 is what makes it reachable
without configuring anything.

**`farrier install` populates and updates the cache.** It is the one command that does.
On install the base is fetched if absent and brought up to `main` if present, so a `pipx`
user gets a working base library by running the command they were going to run anyway:

```bash
farrier init              # once per repo: writes a starter agents.yml (start with packs: [stablemate])
farrier --repo .          # fetches the base if absent, updates it if stale, then renders
farrier --repo . --check  # fetches if absent, but never updates — see below
```

What lands is a sparse checkout of `base-library/` alone, with `.git` dropped once the
commit is recorded into a `.commit` sidecar. `STABLEMATE_FETCH_BASE=0` forbids the network
entirely (air-gapped hosts), and `STABLEMATE_CACHE_DIR` relocates the cache. An update
first asks the remote for the head of `main` — a few hundred bytes — so an already-current
cache costs one round-trip rather than a re-clone.

**Everything else freezes, and that is deliberate.** No lookup, no resume and no
background timer refreshes the cache; `farrier install` is the automated form of the
`rm -rf ~/.cache/stablemate` that used to be the only upgrade path, not a new polling
behaviour. A workhorse run is meant to survive a week unattended and to resume into a
checkpointed state machine after a crash, and a cache tracking `main` live could resume a
run into a different library than it started with. The corollary worth knowing: running
`farrier install` while a long run is in flight on the same machine can move the library
out from under its next resume.

`--check` fetches but does not update, because it writes nothing and runs in CI — a
library moving underneath the comparison would make a drift report depend on the hour the
job ran rather than on the commit it ran against.

Failure is soft, and in the direction of keeping what works: an unreachable remote, a
refused fetch or a broken clone each leave the existing cache in place, so `farrier
install` on a plane renders the library the machine already has. Nothing fetched is
executable either: markdown and YAML, no `.py` anywhere, so code still reaches you only as
a wheel from an index under whatever supply-chain posture you already apply to `pip`/`uv`.

A base you named yourself is never fetched over. Routes 1–3 win outright — not even the
remote probe fires — so a checkout you are editing cannot have a download appear
underneath it.

Either way the cache is a **mirror, not a workspace**: never edit it in place. Overlay
authoring belongs in a `library_dir` (below).

## Tools a workflow needs

The base library declares **no dependencies** — it is content, and importing it pulls in
nothing. The tools its workflows need are a property of *running* a workflow, not of
having the library, and a workflow is a distribution now, so they are ordinary
`[project.dependencies]` on `workhorse-workflows`. Installing that distribution installs
them with it; there is no second manifest to satisfy, and none that can disagree with
what is actually importable.

Which is the whole reason the workflows must land in workhorse's own venv rather than
beside it — and why the install above names `workhorse-workflows` rather than
`workhorse-agent`. Installing the workflows pulls the engine in as *their* dependency, so
the venv the resolver builds is by construction the venv that runs them. Installing the
engine first and adding workflows to it is the same venv reached backwards, and only if
you remember the second step. `make sync` arranges the same thing for a checkout.

## Config

Every tool reads and writes one file, `~/.config/stablemate/config.toml` (override with
`$STABLEMATE_CONFIG`), so `library_dir` / `stablemate_dir` / `base_dir` mean the same
thing to each. Per-tool files (`~/.config/workhorse`, `~/.config/farrier`) are still read
when it is absent, and the first write folds them in.

The file carries a `config_version`, and **that** is what keeps the tools honest with each
other. They install separately and version independently — `pipx install farrier` and
`pipx install ostler` are two venvs, each with its own copy of the config code — while
the config path is per *user*, not per venv. So no packaging arrangement can make
them agree; the guard has to live on the file:

- a tool **refuses to write** a config newer than it understands, rather than serializing
  back a schema it cannot represent and dropping the keys it does not know;
- a newer tool **migrates** an older config forward on its first write (keeping a
  `config.toml.v<n>.bak`), which closes the door behind it;
- **reads never fail** on a newer config — they warn. `resolve_power` re-reads per node,
  and a week-long unattended run must not die because another tool was upgraded.

If a tool refuses, upgrade it — that is the mechanism working, not a bug.

An overlay library shadows the base name-for-name via `farrier config set-library`, or
`$FARRIER_LIBRARY_DIR` for a one-off.
