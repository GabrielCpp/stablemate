# stablemate-core — build and test tasks.
#
# Nothing here publishes. Versions come from release-please and the upload happens in
# .github/workflows/release.yml over OIDC — see the repo root's "Releasing".
#
# This package has no CLI: workhorse and farrier depend on it, so it is published
# BEFORE either of them, or their installs resolve nothing. The workflow's publish
# steps are ordered accordingly.

.DEFAULT_GOAL := help

DIST        := dist
NAME        := $(shell grep -m1 '^name' pyproject.toml | cut -d'"' -f2)
VERSION     := $(shell grep -m1 '^version' pyproject.toml | cut -d'"' -f2)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create/sync the venv from the root uv.lock
	uv sync --extra test

.PHONY: test
test: ## Run the test suite
	uv run --extra test pytest tests -q

.PHONY: build
build: clean ## Build sdist + wheel into this package's dist/
	uv build --package $(NAME) --out-dir dist

.PHONY: check
check: build ## Build and list the wheel contents (verify packaged files)
	@unzip -l $(DIST)/$(subst -,_,$(NAME))-$(VERSION)-py3-none-any.whl

.PHONY: version
version: ## Print the current distribution name and version
	@echo "$(NAME) $(VERSION)"

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info
