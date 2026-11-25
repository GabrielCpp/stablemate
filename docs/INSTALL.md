# Where the pieces come from — the base library, a workflow's tools, the config file

The install itself is three commands, and they are in [README.md](../README.md#installing).
This document is what those commands resolve against: the five routes a tool takes to find
the base library and which one wins, why a workflow's tools are dependencies of the workflow
distribution rather than a manifest of their own, and the one config file every tool shares.

## Finding the base library

farrier ships the base library inside its wheel. Tools resolve the base in this order,
highest precedence first:

1. `$STABLEMATE_BASE_DIR`, an explicit path to the content on disk.
2. `<tool> config set-base <path>`, the persisted form of that path.
3. a configured `stablemate_dir` checkout (`<checkout>/base-library`).
4. the copy farrier ships, for farrier only.
5. the shared cache at `~/.cache/stablemate/library`.

A checkout install gets route 3 for free. A `pipx` install of farrier gets route 4 with
no configuration, no network and no `git`. The base farrier renders is the base its
release carried, byte for byte. A farrier installed from a checkout ships the checkout's
own `base-library/` through a symlink.

**`farrier install` mirrors the shipped base into the cache.** Under `pipx` each tool is
its own venv, so workhorse cannot read farrier's copy. Route 5 is how it finds the base.
Install compares the digest farrier shipped with the one the cache records in its
`.digest` sidecar. When they differ, it copies the base into a sibling directory and
swaps it in whole, so a reader sees the old copy or the new one. When they match, it
copies nothing.

```bash
farrier init              # once per repo: writes an agents.yml that selects no packs, and offers the general packs for your home
farrier --repo .          # mirrors the shipped base if the cache is stale, then renders
farrier --repo . --check  # renders the shipped base and writes no cache
```

`STABLEMATE_CACHE_DIR` relocates the cache.

**Everything else freezes, and that is deliberate.** No lookup, no resume and no
background timer moves the cache. A workhorse run is meant to survive a week unattended
and to resume into a checkpointed state machine after a crash. A cache that moved on its
own could resume a run into a different library than it started with. The corollary
worth knowing: `farrier install` from a newer farrier, while a long run is in flight on
the same machine, can move the library out from under its next resume.

`--check` writes nothing, because it runs in CI. It renders the base farrier ships, so a
drift report depends on the farrier version and not on the cache.

A base you named yourself is never mirrored over. When routes 1 to 3 answer, install
leaves the cache alone, so a checkout you are editing cannot have a copy appear beside it.

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
- **reads never fail** on a newer config — they warn. The config is re-read per node,
  and a week-long unattended run must not die because another tool was upgraded. A value
  of the wrong type fails the first load with its key path, and a later re-read that fails
  keeps the last good config.

If a tool refuses, upgrade it — that is the mechanism working, not a bug.

`farrier config reference` lists every key of this file and of a repository's `agents.yml`,
one line each. `farrier config reference <key>` prints the full entry of a key and the keys
under it, with type, default, meaning and example. `--file home` or `--file manifest` keeps
to one of the two. `farrier config get <key>` prints a key's value, and
`farrier config set <key>=<value>` writes one key after checking it against the schema.
[The configuration guide](guide/configuration.md) explains the output.

An overlay library shadows the base name-for-name via `farrier config set-library`, or
`$FARRIER_LIBRARY_DIR` for a one-off.
