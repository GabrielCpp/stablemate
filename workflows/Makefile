# workhorse-workflows — build and test tasks.

.DEFAULT_GOAL := help

DIST  := dist
NAME  := $(shell grep -m1 '^name' pyproject.toml | cut -d'"' -f2)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test: ## Run the test suite (no network, no real sleeps)
	# pytest over the whole tree, not a `for` loop over tests/test_*.py: that glob is
	# top-level only, so it ran 5 of the 26 test files and the author/coder/okf_builder/
	# research suites — the bulk of the coverage — never reached the gate at all.
	# `testpaths = ["tests"]` in pyproject.toml is what points pytest at them.
	uv run pytest -q

.PHONY: build
build: clean ## Build sdist + wheel into this package's dist/
	uv build --package $(NAME) --out-dir dist

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info
