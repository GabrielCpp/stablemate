# farrier bundles the base library

The solution was read before this note was written: the git fetch into the shared
cache, the vendored-core symlink and digest, and the readers of the cache. The
decisions it carries are listed as claims in 1b.

## 1. Problem

A person installs farrier from PyPI and runs it in a repository. Before anything
renders, farrier clones the base library from GitHub. That first run waits about
five seconds, needs `git` and the network, and fails soft to "no base library" on a
host behind a proxy or offline. Every later run asks GitHub whether the tag moved.

Done looks like this. A farrier installed from a wheel renders the base library on a
host with no network and no `git`. The base it renders is byte for byte the one its
release tagged. A tool that reads the base without carrying it, such as workhorse,
still finds it after one `farrier install`.

Out of scope: publishing the base library as its own package, letting a person pin a
base older than their farrier, and changing which skills the base holds.

## 1b. Claims

1. The base library is fetched by a sparse git clone at the farrier release tag (base cache).
2. A checkout or URL install tracks `main` (farrier cli).
3. Every tool resolves the base in one order: env, `set-base`, `stablemate_dir`, cache (discovery).
4. A base someone named is never fetched over (farrier README).
5. `--check` fetches if absent but never updates (farrier README).
6. `STABLEMATE_FETCH_BASE=0` forbids the network (base cache).
7. Shared code reaches a tool's wheel through a symlink in a checkout and a committed digest (vendor script).

## 2. Parts and concepts

Level 1, four parts:

- **Packing** puts the base into the farrier distribution. It owns the base's
  presence in every artifact farrier ships. It never knows who reads the base at
  run time. It hands the shipped base to Choosing.
- **Choosing** decides which base a run uses. It owns the precedence between a base a
  person named, the base farrier ships and the shared copy. It never knows how a
  base got onto disk. It hands one directory to the renderer.
- **Sharing** keeps the shared copy equal to the base the last install shipped. It
  owns the copy and the stamp that says what it holds. It never knows which tool
  reads it. It acts once per install.
- **Releasing** makes a change to the base ship as a new farrier. It owns the link
  between a base edit and the farrier version. It never knows the base's content.

Flow: at build, Packing copies the base into the wheel. At install, Choosing picks a
base for farrier and Sharing mirrors the shipped base into the shared copy unless a
person named one. At any later command, Choosing picks again, and another tool reads
the shared copy through the same order without the shipped one. At commit, Releasing
records the base's digest under farrier's path.

| Part | Concept | Owns | Never knows |
|---|---|---|---|
| Packing | shipped base | the base directory inside the installed farrier | the cache |
| Choosing | named base | a base a person pointed at (env, config, checkout) | where the shipped base lives |
| Choosing | resolution order | the precedence named > shipped > shared copy | how any base got there |
| Sharing | shared copy | the directory other tools read | which tool shipped it |
| Sharing | content stamp | the digest of what the shared copy holds | file meaning |
| Releasing | base digest | the committed digest of the base under farrier | the release tool |

The content stamp and the base digest are one value type, a digest over sorted
relative paths and bytes, computed by one function.

## 3. Invariants

- I1. A farrier always resolves a base unless its wheel is broken. Owner: resolution order.
- I2. A named base wins over the shipped one and the shared copy, and install writes
  nothing when one answers. Owner: resolution order. Upheld by: shared copy.
- I3. After an install with no named base, the shared copy's stamp equals the shipped
  base's digest. Owner: shared copy.
- I4. A swap of the shared copy is atomic: a reader sees the old or the new copy. Owner: shared copy.
- I5. The committed base digest equals the digest of `base-library/`. Owner: base
  digest, checked by `make check-vendor`.

## 4. Forces and patterns

Forces:

- F1. farrier and its base must change together: a rendered skill names commands of
  the farrier that renders it.
- F2. Other tools live in other virtualenvs (pipx), so they cannot import farrier's data.
- F3. A person editing a base in place must never have it replaced.
- F4. release-please releases a package only for commits that touch its path.
- F5. Tests must run without the real base and without the network.

Patterns:

- Between parts: one value handed along, a directory path. No port, because no part
  has two variants.
- Packing: a symlink in the checkout that the wheel builder follows (F1). Same as claim 7.
- Choosing: one ordered list of candidates (F3). The shipped base is a candidate that
  only farrier passes in, so other tools keep the old order (F2).
- Sharing: copy into a temporary sibling, then rename, compared by content stamp (F2).
- Releasing: the committed digest (F4), the vendor script's existing mechanism.
- Tests: the shipped-base location is a module value the suite points at an empty
  directory (F5).

Claims:

1. Rejected. F1 holds better when the base ships in the wheel than when it is fetched by tag.
2. Rejected. A checkout's shipped base is the checkout's own `base-library/` through the symlink.
3. Kept, with the shipped base inserted after the named routes, for farrier only.
4. Kept as I2.
5. Reshaped. `--check` reads the shipped base and writes nothing.
6. Rejected. Nothing reaches the network, so the switch has nothing to forbid.
7. Kept for Packing and Releasing.

## 5. Mapping onto the existing system

Revision log: none.

- shipped base: **New**, `farrier/farrier/_vendor/base_library`, a symlink to
  `base-library/`. The build test showed hatch follows it into sdist and wheel, 95 files each.
- named base: **Exists**, `core/stablemate_core/discovery.py` `_explicit_base`.
- resolution order: **Reshape**, `discovery.base_library_dir` takes an optional shipped
  base. farrier's `layers.set_layers` passes its own.
- shared copy: **Reshape**, `core/stablemate_core/base_cache.py`. The clone, `ls-remote`,
  `.commit` and the fetch switch go. A mirror from a local directory replaces them.
- content stamp: **New**, a `.digest` sidecar in the shared copy.
- base digest: **Reshape**, `scripts/vendor_core.py` links and stamps the base for farrier
  beside the core it already links into five tools.

What the code has that the design lacks:

- `farrier/cli.py` `_base_library_ref` and the release tag. Waste once the base ships.
- The "could not be fetched" error in `layers.resolve_library_dir`. Reachable only
  with a broken wheel and a named base that is missing. It stays, reworded.
- `services/farrier/surface.py` sets `STABLEMATE_FETCH_BASE=0` so the book's stack is
  the one overlay. With a shipped base that no longer holds. The sandbox names an
  empty base instead, which is the named route.
- Lint walks the symlink: `make lint` would check the base's scripts a second time
  under farrier. The bundle path joins the type checkers' excludes.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A person editing a base checkout | install never writes over it | core discovery tests | holds | holds |
| workhorse under pipx | finds the base in the shared copy after install | nothing end to end | holds after a fetch | holds after a mirror |
| The base's skill set in a release | the tagged base | nothing | tag `farrier-v<version>` | identical files in the wheel |
| PyPI download size | farrier wheel | nothing | 155 KB | under 600 KB |
| First-run time | clone of the base | nothing | 4.75 s on this host | under 1 s |

## 6. Slices

1. Ship and read. The symlink, the digest in the vendor script, farrier's resolution
   order with the shipped base, the mirror into the shared copy, the fetch removed.
   Done when a wheel built from the worktree, installed into a fresh venv with
   `STABLEMATE_CACHE_DIR` empty and no network route used, renders a base skill, and
   the shared copy then holds a `.digest` equal to the shipped base's. Every row of 5b
   is re-measured on that run.
2. Book and docs. The farrier book's sandbox, its decisions, the README, the install
   guide and the security note state the new behaviour. Done when
   `ostler book run services.farrier` is green and `make lint` passes.

## 7. Assumptions

1. **Assumption**: no released consumer reads the shared copy's `.commit` sidecar.
   **Decided**: drop it for `.digest`. **Basis**: a search of the workspace finds no
   reader outside base_cache and its tests. **If wrong**: content stamp.
2. **Assumption**: a person who set `STABLEMATE_FETCH_BASE=0` loses nothing when the
   variable is ignored. **Decided**: remove it without a deprecation path.
   **Basis**: its only effect was to stop the network, and nothing reaches it now.
   **If wrong**: Sharing.
3. **Assumption**: the type checkers would walk the symlink. **Decided**: exclude
   the bundle path. **Basis**: none measured before the change. **If wrong**:
   drop the exclude.
4. **Assumption**: a 531 KB wheel is acceptable on PyPI. **Basis**: the limit is
   100 MB. **If wrong**: Packing.
