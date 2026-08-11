# Changelog

## [1.0.0](https://github.com/GabrielCpp/stablemate/compare/saddlebag-v0.1.0...saddlebag-v1.0.0) (2026-08-11)


### ⚠ BREAKING CHANGES

* **saddlebag:** `acquire`/`scan` no longer accept `--output` or `--output-json`, and `saddlebag.workhorse` no longer exports `write_credential`, `read_credential` or `lease_id_of`. A workflow that needs the credential identity parses the lease JSON from stdout; a workflow that needs the value routes it through `env render`.

### Features

* **saddlebag:** remove every path that emits a stored secret ([41a3956](https://github.com/GabrielCpp/stablemate/commit/41a3956efde58f524d97f40a249ab24adf199101))


### Code Refactoring

* move the scriptutil helpers from workhorse into workflows' kit ([1360d56](https://github.com/GabrielCpp/stablemate/commit/1360d5610c7e89e0dd5cb44f7d48f92fb8fb8170))
