# Changelog

## [1.1.0](https://github.com/GabrielCpp/stablemate/compare/groom-v1.0.0...groom-v1.1.0) (2026-08-14)


### Features

* **groom:** page when a run ends instead of only when it misbehaves ([0c11fe8](https://github.com/GabrielCpp/stablemate/commit/0c11fe8b60a1f29012c4297059284e7cc4204c8a))
* **groom:** page when a run parks on an operator gate ([5d9297d](https://github.com/GabrielCpp/stablemate/commit/5d9297dfdb3a1a335b2bf981b51314249377cb4b))
* **groom:** price the priority-tier variant of gpt-5.6-terra ([6cd13aa](https://github.com/GabrielCpp/stablemate/commit/6cd13aa5a14e679961c5d02be8bfa43bbbbba73d))
* **groom:** rank a loop by the rate card when nothing billed it ([2dbbc70](https://github.com/GabrielCpp/stablemate/commit/2dbbc70e5445ef6b1e5cc3301e86bf88658000cd))

## [1.0.0](https://github.com/GabrielCpp/stablemate/compare/groom-v0.1.0...groom-v1.0.0) (2026-08-11)


### ⚠ BREAKING CHANGES

* **groom:** groom serve binds 127.0.0.1 instead of 0.0.0.0; pass --host 0.0.0.0 to restore the old reachability for containerized runs.

### Features

* **groom:** add `groom cost` — per-node spend and the rework ratio ([c9644c7](https://github.com/GabrielCpp/stablemate/commit/c9644c79faa94bea72d1b14732111bfefdc5ea18))
* **groom:** add retained run profiler ([12c389f](https://github.com/GabrielCpp/stablemate/commit/12c389f8e447221742be2d1a651af13ece9fc9ae))
* **groom:** archive and index run turn records ([1d0bd7f](https://github.com/GabrielCpp/stablemate/commit/1d0bd7f16e314d022fc585768b8b38772fcb5f34))
* **groom:** archive turns from runs older than the visit key ([af9762b](https://github.com/GabrielCpp/stablemate/commit/af9762b5f13e1a76fd36c0f85b539f56bcc9fd0d))
* **groom:** bind loopback by default ([33e3f43](https://github.com/GabrielCpp/stablemate/commit/33e3f4367266ecb8934ba11e500b8b5fed90a034))
* **groom:** count gate decisions, not just the priced ones ([8074a19](https://github.com/GabrielCpp/stablemate/commit/8074a196091e6d70322bbb2afde1caa0ad053db9))
* **groom:** export the archive in the by-node dataset layout ([63ea13c](https://github.com/GabrielCpp/stablemate/commit/63ea13ca51a8fe2d4dd60e5cff8abd10dbf27b30))
* **groom:** price a turn's tokens when the harness reports no money ([29222d8](https://github.com/GabrielCpp/stablemate/commit/29222d8e95f2614ae17293b3a3c1bd467723697e))
* **groom:** price an alias turn from the model its session names ([56e8b2a](https://github.com/GabrielCpp/stablemate/commit/56e8b2a308b59189a436a8d9b8f6b3beae4d9e90))
* **groom:** promote span cost and token fields to real columns ([f4c4208](https://github.com/GabrielCpp/stablemate/commit/f4c42081f0a15d18d3990372e7e1628902c0cd15))
* **groom:** pull container turn records through the sidecar ([e3595a7](https://github.com/GabrielCpp/stablemate/commit/e3595a7720c0bf80919706aeed1b2a1f220c287c))
* **groom:** report which review loops converge and what churn costs ([1627d74](https://github.com/GabrielCpp/stablemate/commit/1627d74e37437e17d0425f61504a3e77a3bd3e35))
* **groom:** show cost per profile group ([9329f44](https://github.com/GabrielCpp/stablemate/commit/9329f443df2fb1c18f7b8f7321be5bed1debe458))
* **groom:** show which agent cli ran the run's last turn ([a5f551d](https://github.com/GabrielCpp/stablemate/commit/a5f551d8eb5e4b90caa7cd1f63a3ee860e954fc1))
* **workhorse:** tag each run start with a resume generation ([7c34d31](https://github.com/GabrielCpp/stablemate/commit/7c34d3133835d435b786682f1d71e334200d38e4))


### Bug Fixes

* **groom:** classify live pyflow waits correctly ([a6c8c8c](https://github.com/GabrielCpp/stablemate/commit/a6c8c8cae4738d717e075439f0cad40a13eb6f08))
* **groom:** distinguish workflow visits from retries ([51fcdc9](https://github.com/GabrielCpp/stablemate/commit/51fcdc9c707d4ce0e723aeab1c4bd6b37818459d))
* **groom:** do not count a reload-cut visit as churn ([20d9f58](https://github.com/GabrielCpp/stablemate/commit/20d9f5811592e4608bfe11938c61915e35f8f301))
* **groom:** flag turns that price themselves at exactly zero ([1996ea6](https://github.com/GabrielCpp/stablemate/commit/1996ea65f27ee3a7f4e0bfeafe16ee0be8dc924d))
* **groom:** hold the pull flag until the staged mirror is gone ([0abb289](https://github.com/GabrielCpp/stablemate/commit/0abb289f1b1b8828b32b45c7e64f16b347d725cc))
* **groom:** keep alert badges true to the run's current state ([3521fca](https://github.com/GabrielCpp/stablemate/commit/3521fca78c16082c93107f5b4dee0decbc20a88b))
* **groom:** say when a run's cost coverage is partial ([31ff864](https://github.com/GabrielCpp/stablemate/commit/31ff8641a54bc806b8d5d1b60f039f3b4f353e59))
* **groom:** watch the filesystem through a portable backend ([e5f6766](https://github.com/GabrielCpp/stablemate/commit/e5f6766bdf412968b74863f6eb874b91c7a22fe2))
* remove groom wall-clock budget alerts ([79a8dad](https://github.com/GabrielCpp/stablemate/commit/79a8dad16d5900c9d7fdef006fa9e5c7cf4b837d))
* **workhorse:** make container telemetry actually reach groom ([7bf5f95](https://github.com/GabrielCpp/stablemate/commit/7bf5f95b8bcf7f04519d9619fd9a1560fe014b68))
* **workhorse:** make the otel sdk a required dependency ([9985787](https://github.com/GabrielCpp/stablemate/commit/998578789c97c8e7a974d15f0ff4d222e8dcf6e2))


### Performance Improvements

* **groom:** expire liveness counters sooner than diagnostic metrics ([d788ecc](https://github.com/GabrielCpp/stablemate/commit/d788eccab5c51caf5cb16ea80417c3fb6bc18075))
* **groom:** stop blocking the event loop on every OTLP write ([1accc55](https://github.com/GabrielCpp/stablemate/commit/1accc55bf5f63fd281f2685223ca070d398d9dc4))
