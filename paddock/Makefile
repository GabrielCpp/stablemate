# paddock — build and test tasks.
#
# Nothing here publishes: paddock is not on PyPI (see the README). Versions still
# come from release-please so a changelog exists when it ever ships.

.DEFAULT_GOAL := help

DIST        := dist
NAME        := $(shell grep -m1 '^name' pyproject.toml | cut -d'"' -f2)
VERSION     := $(shell grep -m1 '^version' pyproject.toml | cut -d'"' -f2)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create/sync the workspace venv from the root uv.lock
	uv sync

.PHONY: test
test: ## Run the test suite — the harness's tests and the data's, in one pass
	# pytest, not a `python tests/test_*.py` loop: these tests are pytest-style
	# (fixtures, tmp_path) with no __main__ runner — see ostler/Makefile for the
	# incident that comment records.
	#
	# Two roots, one invocation. `tests/` covers the harness; `data/tests/` covers the
	# task modules and the fixtures they score against — a benchmark whose scoring is
	# wrong is worse than no benchmark, because it reports a number nobody re-derives.
	# They are named together rather than split across two targets so there is no way to
	# run "paddock's tests" and have skipped half of what a round rests on.
	#
	# `-n auto --dist loadscope`: the minutes here are subprocess minutes — go builds,
	# pulumi previews, git plumbing — each in its own tmp dir, so they parallelize
	# cleanly and the serial suite's ~11 minutes was mostly cores sitting idle.
	# `loadscope` rather than plain `load` because the compile-heavy modules share a
	# module-scoped go build cache; scattering their tests across workers would give
	# each worker a cold cache and recompile the same SDK tree once per worker.
	uv run --extra test pytest tests data/tests -q -n auto --dist loadscope

.PHONY: test-fast
test-fast: ## Run tests that need no external toolchain, mutation battery, or stress loop
	uv run --extra test pytest tests data/tests -q -n auto --dist loadscope \
		-m "not toolchain and not mutation and not stress"

.PHONY: test-toolchain
test-toolchain: ## Compile, type-check, and preview every fixture variant
	# Compiler processes parallelize internally; two pytest workers avoid oversubscribing CI.
	uv run --extra test pytest tests data/tests -q -n 2 --dist loadscope -m toolchain

.PHONY: test-mutation
test-mutation: ## Run the differential mutant corpus
	uv run --extra test pytest tests data/tests -q -m mutation

.PHONY: test-stress
test-stress: ## Run timing-sensitive filesystem stress checks
	uv run --extra test pytest tests data/tests -q -m stress

.PHONY: build
build: clean ## Build sdist + wheel into this package's dist/
	uv build --package $(NAME) --out-dir dist

.PHONY: check
check: build ## Build and list the wheel contents (verify packaged files)
	@unzip -l $(DIST)/$(subst -,_,$(NAME))-$(VERSION)-py3-none-any.whl

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info

.PHONY: version
version: ## Print the current distribution name and version
	@echo "$(NAME) $(VERSION)"
