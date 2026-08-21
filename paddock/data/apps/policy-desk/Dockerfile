# One image, one process, one port. The web bundle is built and then handed to the Go
# binary as static files, so a deep link into a client route is served by the same
# process that answers the API call the screen makes next.

FROM node:22-alpine AS web
WORKDIR /src
COPY app/web/package.json app/web/package-lock.json ./
RUN npm ci
COPY app/web/ ./
RUN npm run build

FROM golang:1.24-alpine AS api
WORKDIR /src
COPY app/api/go.mod ./
RUN go mod download
COPY app/api/ ./
RUN CGO_ENABLED=0 go build -o /out/policy-desk ./...

FROM alpine:3.20
RUN adduser -D -u 10001 desk && mkdir -p /data && chown desk /data
COPY --from=api /out/policy-desk /usr/local/bin/policy-desk
COPY --from=web /src/dist /srv/web
USER desk
EXPOSE 18084
ENTRYPOINT ["/usr/local/bin/policy-desk", "-addr", ":18084", "-data", "/data/policies.json", "-web", "/srv/web"]
