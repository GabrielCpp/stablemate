# Changelog

## [5.0.0](https://github.com/GabrielCpp/stablemate/compare/saddlebag-v4.0.0...saddlebag-v5.0.0) (2026-11-27)


### ⚠ BREAKING CHANGES

* **farrier:** agents.<harness>.skills_from is refused on every harness but claude, and claude may only name codex, antigravity or pi. Write codex: true and claude: {skills_from: codex} instead.

### Features

* **core:** add the per-user farrier state dir helper ([16bcf6f](https://github.com/GabrielCpp/stablemate/commit/16bcf6fc23f33bd614222e0e7d9e793bdc3915b5))
* **core:** expand environment variables in home config paths ([5060f82](https://github.com/GabrielCpp/stablemate/commit/5060f824957d2b65240548686dc3fbf7898573af))
* **farrier:** land codex repo prompts as name-only skills ([4b9f044](https://github.com/GabrielCpp/stablemate/commit/4b9f044bb92af8fa696416abe158b6734c12d647))
* **farrier:** link only claude skills, to .agents/skills ([339e627](https://github.com/GabrielCpp/stablemate/commit/339e6274401fe51048f412d03f3b871b01787a69))
* **workhorse:** run workflow turns on Antigravity ([64e2094](https://github.com/GabrielCpp/stablemate/commit/64e2094c76d9dcc5810fc0c954180367175b9f90))


### Code Refactoring

* **farrier:** stop writing the agents-context manifests ([7769eb1](https://github.com/GabrielCpp/stablemate/commit/7769eb1cd896acd9babc6bb404d1992b584417db))

## [4.0.0](https://github.com/GabrielCpp/stablemate/compare/saddlebag-v3.1.0...saddlebag-v4.0.0) (2026-11-25)


### ⚠ BREAKING CHANGES

* **workhorse:** workhorse no longer runs turns through cline. A profile or dispatch that names it is refused.

### Features

* **core:** add the harness registry and tie each harness table to it ([5659cdf](https://github.com/GabrielCpp/stablemate/commit/5659cdf6812b3bf37db18321866e40f5c01c93ed))
* **farrier:** add antigravity as a render-only harness ([96cff2c](https://github.com/GabrielCpp/stablemate/commit/96cff2c4974bb1c353f4e266825161a842b3dd56))
* **farrier:** render a shared skill folder once per harness group ([bd90259](https://github.com/GabrielCpp/stablemate/commit/bd902591a43f77604e272a007575fcc7e0efd9c5))
* **workhorse:** add pi as a harness and backend ([73ee80c](https://github.com/GabrielCpp/stablemate/commit/73ee80c9aa2e1dc1d7f7bd864d919a6c1a8af20d))
* **workhorse:** derive backends from the registry, load opencode dirs ([be5476d](https://github.com/GabrielCpp/stablemate/commit/be5476dc851bfc5ab39bebe4eaf36b14ddf8b6bc))
* **workhorse:** retire the cline backend ([12f2df4](https://github.com/GabrielCpp/stablemate/commit/12f2df4040c5ff777778bfc4fb5cfa0b5fb80f85))


### Code Refactoring

* **core:** split value coercers and QA tables out of the schema ([4958775](https://github.com/GabrielCpp/stablemate/commit/49587753f991deeaa53371ac93ff6bed1d829982))
* **farrier:** derive harness lists and paths from the registry ([5649bed](https://github.com/GabrielCpp/stablemate/commit/5649bedd0f505c58b0e67ad619108ba02de8d20c))

## [3.1.0](https://github.com/GabrielCpp/stablemate/compare/saddlebag-v3.0.0...saddlebag-v3.1.0) (2026-11-25)


### Features

* **core:** add a portable pid_alive and pid_start_token ([27131bf](https://github.com/GabrielCpp/stablemate/commit/27131bf10221a51c60eea6a78d978a91aabb0a65))


### Bug Fixes

* **core:** find a book when the artifacts dir is a linked worktree ([3c341dd](https://github.com/GabrielCpp/stablemate/commit/3c341dd8944fbe0c31e469256b3acb0cc5650835))
* **workflows:** keep a timed tool in the run's process group ([88d2ec0](https://github.com/GabrielCpp/stablemate/commit/88d2ec02dde4c756bc3726d8f268c77100f6cd59))

## [3.0.0](https://github.com/GabrielCpp/stablemate/compare/saddlebag-v2.1.0...saddlebag-v3.0.0) (2026-11-24)


### ⚠ BREAKING CHANGES

* **core:** QaTool, QaTable.tools and HomeConfig.qa_tools are removed from the schema.

### Features

* **core:** let a power tier name its compaction window ([0e06e1d](https://github.com/GabrielCpp/stablemate/commit/0e06e1de7fc328a2c4dea65918bffc250995ec99))
* **core:** name the folder of a repository's service books ([1796703](https://github.com/GabrielCpp/stablemate/commit/1796703bf800844e3d0b2b36fb20e08f0f04b80c))
* **core:** open and land a book branch in the artifacts repository ([5a7a818](https://github.com/GabrielCpp/stablemate/commit/5a7a818447780f8d6b9202c6461333cb253d4c7f))
* **core:** resolve the book home from agents.yml and the artifacts repo ([b94c7f9](https://github.com/GabrielCpp/stablemate/commit/b94c7f9609aa52312206f58bc651c73ca791cef4))
* **farrier:** merge library settings files into ~/.claude/settings.json ([3e134f1](https://github.com/GabrielCpp/stablemate/commit/3e134f1d44ab0833e39cd5305b3d909cdc03aaae))
* **farrier:** ship the base library inside the farrier wheel ([9c71dba](https://github.com/GabrielCpp/stablemate/commit/9c71dba3f1a202a3c5fd470c82305e56f4461e6d))
* **ostler:** read product, team and company books beside services ([a5ae8fe](https://github.com/GabrielCpp/stablemate/commit/a5ae8fe2f81ec551a0c6dfe62f1889411ba18f34))
* **saddlebag:** change a secret's username, description or var ([8387866](https://github.com/GabrielCpp/stablemate/commit/838786626a40a9e15e9cc2b3f388d4816f4d8f2c))


### Bug Fixes

* **core:** let a test forget remembered warnings and cached reads ([1bfe2c5](https://github.com/GabrielCpp/stablemate/commit/1bfe2c5557c5968cdbe793c6d9e8615e7b9f47e4))


### Performance Improvements

* keep a folder's repository identity while its git layout holds ([0a31568](https://github.com/GabrielCpp/stablemate/commit/0a31568c543351e4b2b2be60b33ca686a3835fa2))


### Code Refactoring

* **core:** drop config.book_home for books.book_home ([5086eb5](https://github.com/GabrielCpp/stablemate/commit/5086eb5268247be2ab8ee7eefe9675ef62d9f0f7))
* **core:** drop the qa tools keys from both config schemas ([bd68e8c](https://github.com/GabrielCpp/stablemate/commit/bd68e8c9f4826cc155bf7c2bb31d7b81ad1a9c93))

## [2.1.0](https://github.com/GabrielCpp/stablemate/compare/saddlebag-v2.0.0...saddlebag-v2.1.0) (2026-10-29)


### Features

* **saddlebag:** deny a command that carries a stored secret value ([d3826d0](https://github.com/GabrielCpp/stablemate/commit/d3826d0bc781de723f07755a90d9cc0f7413f7cc))
* **saddlebag:** give a secret printable metadata editable by key ([197181b](https://github.com/GabrielCpp/stablemate/commit/197181bed36b7303ecb664bbf361157a0513f35f))
* **saddlebag:** guard agent reads of secrets and show a dotenv masked ([614212b](https://github.com/GabrielCpp/stablemate/commit/614212b1996abfc7a3a3d25bdb2b6ee0ec42ebc1))
* **saddlebag:** import a dotenv's secret lines into records ([94e5ad6](https://github.com/GabrielCpp/stablemate/commit/94e5ad6c5816b0f642fda89fd835bb470d2400bc))
* **saddlebag:** mask secret values in exec output off a terminal ([2f5ac1f](https://github.com/GabrielCpp/stablemate/commit/2f5ac1fe00823bbfbfe6729ebfd5f13fbe32c23a))
* **saddlebag:** read a dotenv from stdin when FILE is - ([38a39a8](https://github.com/GabrielCpp/stablemate/commit/38a39a8675be842f3d8916c5d05cd4a2966d4a7f))

## [2.0.0](https://github.com/GabrielCpp/stablemate/compare/saddlebag-v1.1.0...saddlebag-v2.0.0) (2026-10-26)


### ⚠ BREAKING CHANGES

* books are read from docs/services only. A repository that still has docs/features must run `ostler okf migrate` or rename the folder.
* **saddlebag:** the OS keyring backend, the SQLite pool, credential leases, AI selection, the `env` command family, `link`/`unlink` and the YAML manifest are removed. Nothing is migrated. Items in a 1.x pool or in the OS keyring are left in place and orphaned.

### Features

* **saddlebag:** choose the route from the config key and a ping ([a1f8d70](https://github.com/GabrielCpp/stablemate/commit/a1f8d70e2fab0b19cd101111176a723cd9c8acd5))
* **saddlebag:** hold the vault token in a daemon and fill by tag ([a4b0f84](https://github.com/GabrielCpp/stablemate/commit/a4b0f843aabfaf21978dfc1b838a02af6d431d48))
* **saddlebag:** probe the keyring door and name the mac interpreter ([a3bc4bf](https://github.com/GabrielCpp/stablemate/commit/a3bc4bf5bfa6ceecf9b69a26f4586ad9125c7bba))
* **saddlebag:** read the vault token from the keyring or a 0600 file ([3305462](https://github.com/GabrielCpp/stablemate/commit/33054627c0bf614462dea1f6c8ddc8988642fa4f))
* **saddlebag:** report the store behind doctor and check the keyring ([6ab8aaf](https://github.com/GabrielCpp/stablemate/commit/6ab8aafb4fed0818fc16fd900b3390a45fc65403))
* **saddlebag:** serve ad hoc commands from the OS keyring ([27deeff](https://github.com/GabrielCpp/stablemate/commit/27deeff577caecc1d8954fa2bfc6d1cf30f570b1))


### Code Refactoring

* move the book root from docs/features to docs/services ([9c14166](https://github.com/GabrielCpp/stablemate/commit/9c141662047ead9a9ed398a21477b62223db9ef0))

## [1.1.0](https://github.com/GabrielCpp/stablemate/compare/saddlebag-v1.0.0...saddlebag-v1.1.0) (2026-09-11)


### Features

* **saddlebag:** fill a credential into a browser over CDP ([6a8763e](https://github.com/GabrielCpp/stablemate/commit/6a8763e2cc230cbd6b3b5846412e0345e824d7b5))
* **saddlebag:** read a credential from a keychain item it did not write ([593f5d7](https://github.com/GabrielCpp/stablemate/commit/593f5d7a2480a2458d5ff6d98d0a5f1db157a84e))


### Bug Fixes

* **workhorse:** keep a handoff's START in its flow, colour END apart ([eb00514](https://github.com/GabrielCpp/stablemate/commit/eb00514755460c77f4b10ade8d20f9d4fdb503d8))

## [1.0.0](https://github.com/GabrielCpp/stablemate/compare/saddlebag-v0.1.0...saddlebag-v1.0.0) (2026-08-11)


### ⚠ BREAKING CHANGES

* **saddlebag:** `acquire`/`scan` no longer accept `--output` or `--output-json`, and `saddlebag.workhorse` no longer exports `write_credential`, `read_credential` or `lease_id_of`. A workflow that needs the credential identity parses the lease JSON from stdout; a workflow that needs the value routes it through `env render`.

### Features

* **saddlebag:** remove every path that emits a stored secret ([41a3956](https://github.com/GabrielCpp/stablemate/commit/41a3956efde58f524d97f40a249ab24adf199101))


### Code Refactoring

* move the scriptutil helpers from workhorse into workflows' kit ([1360d56](https://github.com/GabrielCpp/stablemate/commit/1360d5610c7e89e0dd5cb44f7d48f92fb8fb8170))
