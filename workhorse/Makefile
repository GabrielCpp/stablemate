# local-worker / workhorse-agent — build and test tasks.
#
# Nothing here publishes. Versions come from release-please and the upload happens in
# .github/workflows/release.yml over OIDC — see the repo root's "Releasing".

.DEFAULT_GOAL := help

PYTHON      := .venv/bin/python
DIST        := dist
NAME        := $(shell grep -m1 '^name' pyproject.toml | cut -d'"' -f2)
VERSION     := $(shell grep -m1 '^version' pyproject.toml | cut -d'"' -f2)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Create/sync the local venv from uv.lock
	uv sync

.PHONY: test
test: ## Run the standalone test suite (no network, no real sleeps)
	# Keep each file directly runnable for focused debugging, but use one pytest process
	# for the gate: several files require pytest fixtures and process tests shard cleanly.
	uv run pytest tests -q -n auto --dist worksteal

.PHONY: build
build: clean ## Build sdist + wheel into this package's dist/
	uv build --package $(NAME) --out-dir dist

.PHONY: check
check: build ## Build and list the wheel contents (verify packaged files)
	@unzip -l $(DIST)/$(subst -,_,$(NAME))-$(VERSION)-py3-none-any.whl

.PHONY: verify-install
verify-install: ## Install the published package from PyPI and import its public API
	# Workhorse ships no command of its own — it is a library, and what a consumer
	# imports is the wiring for their own workflow's command. So the smoke test is
	# that import, not a `--help`.
	uv run --with $(NAME) --no-project --refresh-package $(NAME) -- \
		python -c "from workhorse import console_script; print(console_script)"

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf $(DIST) build *.egg-info

.PHONY: version
version: ## Print the current distribution name and version
	@echo "$(NAME) $(VERSION)"
