# One image, one process, one port. There is no web bundle to build — the claims desk has
# no browser surface, which is the fixture's whole reason to exist.
#
# `go mod download` runs on its own layer from `go.mod`/`go.sum` alone so a defect variant,
# which only ever rewrites one source file, rebuilds the compile and not the dependency
# fetch. The Firebase Admin SDK is the one real third-party dependency tree in any of these
# fixtures, and re-downloading it per trial would cost more than the trial.

FROM golang:1.25-alpine AS api
WORKDIR /src
COPY app/api/go.mod app/api/go.sum ./
RUN go mod download
COPY app/api/ ./
RUN CGO_ENABLED=0 go build -o /out/claims-api .

FROM alpine:3.20
RUN adduser -D -u 10001 desk && mkdir -p /data && chown desk /data
COPY --from=api /out/claims-api /usr/local/bin/claims-api
USER desk
EXPOSE 18085
ENTRYPOINT ["/usr/local/bin/claims-api", "-addr", ":18085", "-data", "/data/claims.json"]
