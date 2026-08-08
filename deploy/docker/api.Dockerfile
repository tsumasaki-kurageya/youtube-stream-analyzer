FROM golang:1.24-alpine AS build

WORKDIR /src
COPY apps/api/go.mod apps/api/go.sum ./apps/api/
RUN cd apps/api && go mod download
COPY apps/api ./apps/api
RUN cd apps/api && \
    CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/api ./cmd/api && \
    CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/migrate ./cmd/migrate && \
    CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/m4-demo-report ./cmd/m4-demo-report

FROM alpine:3.22
RUN addgroup -S ysa && adduser -S -G ysa ysa && apk add --no-cache ca-certificates tzdata
WORKDIR /app/apps/api
COPY --from=build /out/api /out/migrate /out/m4-demo-report ./
COPY database /app/database
USER ysa
EXPOSE 8080
CMD ["./api"]
