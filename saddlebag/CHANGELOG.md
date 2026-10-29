# Changelog

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
