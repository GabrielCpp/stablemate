# web-app is a static bundle behind a one-file Go server — no build step, since the pages
# ship as plain HTML/CSS/JS. Its own image, its own lifecycle, independent of api-service's.

FROM golang:1.24-alpine AS build
WORKDIR /src
COPY app/web-app/go.mod ./
RUN go mod download
COPY app/web-app/ ./
RUN CGO_ENABLED=0 go build -o /out/web-app ./...

FROM alpine:3.20
RUN adduser -D -u 10001 svc
COPY --from=build /out/web-app /usr/local/bin/web-app
COPY --from=build /src/static /srv/static
USER svc
EXPOSE 18102
ENTRYPOINT ["/usr/local/bin/web-app", "-addr", ":18102", "-static", "/srv/static"]
