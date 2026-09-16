# One process, one port, no bundle — api-service answers HTTP only. Its own image, its own
# lifecycle, independent of web-app's.

FROM golang:1.24-alpine AS build
WORKDIR /src
COPY app/api-service/go.mod ./
RUN go mod download
COPY app/api-service/ ./
RUN CGO_ENABLED=0 go build -o /out/api-service ./...

FROM alpine:3.20
RUN adduser -D -u 10001 svc
COPY --from=build /out/api-service /usr/local/bin/api-service
USER svc
EXPOSE 18101
ENTRYPOINT ["/usr/local/bin/api-service", "-addr", ":18101"]
