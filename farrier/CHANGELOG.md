# Changelog

## [3.0.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v2.1.0...farrier-v3.0.0) (2026-09-11)


### ⚠ BREAKING CHANGES

* **farrier:** bare `farrier hooks` no longer defaults to install; use `farrier hooks install` explicitly.
* **core:** bump stablemate config schema to v2

### Features

* **core:** let a power tier scale every wall-clock budget ([50b5081](https://github.com/GabrielCpp/stablemate/commit/50b5081d3930a22e0cae23ed2c989eb56af71d3c))
* **core:** persist a nested config table, and groom's attend settings ([3c51cca](https://github.com/GabrielCpp/stablemate/commit/3c51cca625bf29d50092cbb1cbd2a7399bec8cb3))
* **farrier:** add hooks install/list verbs with dry-run support ([e8b3ed3](https://github.com/GabrielCpp/stablemate/commit/e8b3ed3882c3446e49f1340fd5c3311de7865cfa))
* **farrier:** delete only files tagged generated_by: farrier ([518154e](https://github.com/GabrielCpp/stablemate/commit/518154eb0e718135a3121e4038972b242b978cb5))
* **farrier:** hold skills to the open agent skills spec ([d41bcf1](https://github.com/GabrielCpp/stablemate/commit/d41bcf13debedcaa022fa0d3bcd7b9fd6d77cc90))
* **farrier:** install skills into the harness home directory ([811f71d](https://github.com/GabrielCpp/stablemate/commit/811f71dcecd69c14abe473a5287288059ab43604))
* **farrier:** read the library from the CLI ([846fc81](https://github.com/GabrielCpp/stablemate/commit/846fc81a49d1462477a747f8b483d41678fe6b8a))
* **farrier:** seed a new agents.yml with the base library's two packs ([f33cae3](https://github.com/GabrielCpp/stablemate/commit/f33cae3f9115ae90c55d65ec90fa0f87d2c4a37e))
* **workhorse:** run a measurement detached under a bounded supervisor ([3c0cb8c](https://github.com/GabrielCpp/stablemate/commit/3c0cb8c64e535353a1a6dfae83b04598f2c2e2b0))


### Bug Fixes

* **farrier:** let the aggregated AGENTS.md be regenerated ([5cf584c](https://github.com/GabrielCpp/stablemate/commit/5cf584ca00613914d74aacec66c4b4e6f1d56834))
* **farrier:** stop the generated launcher taking over the help target ([aa2161f](https://github.com/GabrielCpp/stablemate/commit/aa2161f5755c9c762914e949fbe489d36583c24d))
* **workhorse:** keep a handoff's START in its flow, colour END apart ([eb00514](https://github.com/GabrielCpp/stablemate/commit/eb00514755460c77f4b10ade8d20f9d4fdb503d8))


### Performance Improvements

* consolidate package test startups ([10a5bf8](https://github.com/GabrielCpp/stablemate/commit/10a5bf88d1dee595514222eba8262ed712e3ba36))


### Code Refactoring

* **core:** bump stablemate config schema to v2 ([586d593](https://github.com/GabrielCpp/stablemate/commit/586d593134aad89d14d4f21f748a8c83ae6b4ad8))
* **core:** move the clock port into shared plumbing ([fa5a4f5](https://github.com/GabrielCpp/stablemate/commit/fa5a4f5a7323f0740ee775c6b6f40c8da8f6e64a))
* **farrier:** drop per-skill copilot instruction files ([50e2677](https://github.com/GabrielCpp/stablemate/commit/50e2677100809b5d3a56601a306eb897878ef704))
* **farrier:** guard the front-matter token's line map ([dc6a378](https://github.com/GabrielCpp/stablemate/commit/dc6a3780a13da611569ea8a8b3373c445747ebe9))
* **farrier:** name installed skills by their library group ([170b38a](https://github.com/GabrielCpp/stablemate/commit/170b38a59611a3ad35fb2444790c055a7440d2a4))

## [2.1.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v2.0.0...farrier-v2.1.0) (2026-08-14)


### Features

* **core:** read the fallback agent cli from the shared config ([8cc0836](https://github.com/GabrielCpp/stablemate/commit/8cc0836a7888b6c5942eaf36b5cb950a19148dff))


### Bug Fixes

* **farrier:** point setup errors at farrier init and the pack catalog ([6162372](https://github.com/GabrielCpp/stablemate/commit/61623720eaf4b214f34438efa8db855b6518dca9))

## [2.0.0](https://github.com/GabrielCpp/stablemate/compare/farrier-v1.5.2...farrier-v2.0.0) (2026-08-11)


### ⚠ BREAKING CHANGES

* installed skill names change for every repo that selects the `stablemate` pack — `<repo>-stablemate-ostler` becomes `<repo>-ostler`. An agents.yml selecting `stablemate/stablemate-ostler` by hand, a `localInstructions` entry, or a prompt naming an old skill has to be updated; farrier reports the miss with a suggestion rather than installing nothing. In the stablemate repo most installed names are unchanged, because the derived prefix restores them: `ostler` installs as `stablemate-ostler` exactly as before. The two that do move here are `stablemate-coder-workflow` -> `stablemate-workhorse-coder-workflow` and `stablemate-documentation` -> `stablemate-ostler-documentation`.
* `agents.yml` `repo.name` / `repo.prefix` no longer set the install prefix. A repo that used either to install under a name other than its directory's renders its skills under different filenames after this change; rename the directory to keep them. Repos whose prefix already matched their directory name — which the installer defaulted to — are unaffected.

### Features

* derive a repo's name from its directory, never from agents.yml ([884b2e4](https://github.com/GabrielCpp/stablemate/commit/884b2e4294055adbf9c51613e4620dd4339e01e4))
* **farrier:** add `library --check` to catch front matter that silently fails ([023b28d](https://github.com/GabrielCpp/stablemate/commit/023b28d807aa71c312bb0d9dba4480669e562a40))
* **farrier:** add init, and show the verbs for a bare invocation ([181a15d](https://github.com/GabrielCpp/stablemate/commit/181a15d44381981a0995e7ee820ab891aaf17817))
* **farrier:** discover runnable workflows from pipx, at make time ([b0b259e](https://github.com/GabrielCpp/stablemate/commit/b0b259e61afe0d18bfd98ea8511695b2dfed4f60))
* **farrier:** fetch and update the base library on install ([005f6dc](https://github.com/GabrielCpp/stablemate/commit/005f6dcd7a16b6650b4be17b8993fe8fd1eccc16))
* **farrier:** launch one container per run, with its own run id ([d4a0f87](https://github.com/GabrielCpp/stablemate/commit/d4a0f879b1ae899f42c8f128acbe36e818799238))
* **farrier:** let localInstructions aggregate prompts and name its file ([0bcd940](https://github.com/GabrielCpp/stablemate/commit/0bcd940e689a8af351ac74e92faa15cf4921c91b))
* **workflows:** give each run its own worktree of one host repo ([1e6c065](https://github.com/GabrielCpp/stablemate/commit/1e6c06541e919e03b9592dbfefecf921ad13d489))
* **workhorse:** keep container output host-usable, and let it log in ([b2432ea](https://github.com/GabrielCpp/stablemate/commit/b2432ea4045b6f67686452106f4c5b1a4e591296))
* **workhorse:** replace the aider backend with cline ([7cdf30e](https://github.com/GabrielCpp/stablemate/commit/7cdf30e44563d7af497ee0d341f77d205e989b0b))


### Bug Fixes

* **farrier:** catch a tag YAML resolves as something other than a string ([7cf8386](https://github.com/GabrielCpp/stablemate/commit/7cf8386638410605d88f77fa011accb94e428999))
* **farrier:** commit the codex adapters, and drop the redundant leading slash ([aab5964](https://github.com/GabrielCpp/stablemate/commit/aab596486560c9cf670f0d2f095947e9ddbcfce3))
* **farrier:** drop $ARGUMENTS from a prompt aggregated into instructions ([6805272](https://github.com/GabrielCpp/stablemate/commit/6805272ecb9db0d0c669c31882906e5c0c4d4fc5))
* **farrier:** drop the do-not-edit marker from the aggregated AGENTS.md ([cbd5527](https://github.com/GabrielCpp/stablemate/commit/cbd55270bd2534fd6aa679a9e18312e3c65c6b71))
* **farrier:** honor {% raw %} in skill files that name no helper ([5f1b39d](https://github.com/GabrielCpp/stablemate/commit/5f1b39dd480fa8c6bd9880e208c38eda83a8d4ba))
* **farrier:** stop naming the private library repo in generated output ([631386f](https://github.com/GabrielCpp/stablemate/commit/631386f5dd839e3444854d16d586587f339c6931))


### Code Refactoring

* **farrier:** aggregate local instructions into AGENTS.md ([0da2789](https://github.com/GabrielCpp/stablemate/commit/0da2789064f5de0fc8cd152b6937ffb0d726b8e6))
* name base-library skills after their tool, not after stablemate ([2244a42](https://github.com/GabrielCpp/stablemate/commit/2244a420cfc0c837331f5e4b798dd784093d52c7))

## [1.5.2](https://github.com/GabrielCpp/stablemate/compare/farrier-v1.5.1...farrier-v1.5.2) (2026-08-02)


### Code Refactoring

* vendor stablemate-core into workhorse and farrier ([0bef8ff](https://github.com/GabrielCpp/stablemate/commit/0bef8ff23771bc11992d9f33ae790604359d2804))
