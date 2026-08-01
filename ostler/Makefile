# ostler — build and test tasks.
#
# Nothing here publishes. Versions come from release-please and the upload happens in
# .github/workflows/release.yml over OIDC — see the repo root's "Releasing".

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
test: ## Run the test suite
	# pytest, not the sibling packages' `python tests/test_*.py` loop: these tests are
	# pytest-style (fixtures, tmp_path) with no __main__ runner, so that loop imported each
	# module, ran nothing, and exited 0 — a green bar over an unexecuted suite.
	uv run --extra dev pytest tests -q

.PHONY: build
build: clean ## Build sdist + wheel into this package's dist/
	uv build --package $(NAME) --out-dir dist

.PHONY: check
check: build ## Build and list the wheel contents (verify packaged files)
	@unzip -l $(DIST)/$(subst -,_,$(NAME))-$(VERSION)-py3-none-any.whl

.PHONY: verify-install
verify-install: ## Install the published package from PyPI and run --help
	uv run --with $(NAME) --no-project --refresh-package $(NAME) -- ostler --help

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info

.PHONY: version
version: ## Print the current distribution name and version
	@echo "$(NAME) $(VERSION)"
