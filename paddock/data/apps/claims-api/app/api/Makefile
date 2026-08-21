# Regenerating the server from the contract.
#
# `gen/` is committed and frozen: a trial must not need the generator, and a fixture whose
# build reaches the network for a code generator is a fixture that fails for reasons that
# have nothing to do with the run. This target exists so the integrity test can prove the
# committed output still matches `openapi.yml` on a machine that does have the toolchain —
# the generator is pinned by `@version` here rather than by a `tools.go`, so the pin and the
# invocation are one line apart and cannot drift.

OAPI_CODEGEN := go run github.com/oapi-codegen/oapi-codegen/v2/cmd/oapi-codegen@v2.5.1

.PHONY: generate
generate:
	$(OAPI_CODEGEN) -generate types -package gen -o gen/types.gen.go openapi.yml
	$(OAPI_CODEGEN) -generate chi-server -package gen -o gen/server.gen.go openapi.yml
