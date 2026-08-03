#!/usr/bin/env bash
set -euo pipefail

for config in deploy/railway/*.json; do
  python3 -m json.tool "$config" >/dev/null
done

docker build -f deploy/docker/api.Dockerfile -t ysa-api:ci .
docker build -f deploy/docker/worker.Dockerfile -t ysa-worker:ci .
docker build -f deploy/docker/gateway.Dockerfile -t ysa-gateway:ci .
docker build -f deploy/docker/web.Dockerfile -t ysa-web:ci .

docker run --rm ysa-api:ci ./api -help >/dev/null 2>&1 || true
docker run --rm ysa-worker:ci python -c 'import ysa_worker.main'
docker run --rm ysa-gateway:ci python -c 'import ysa_gateway.app'
docker run --rm -e YSA_API_ORIGIN=http://api:8080 ysa-web:ci \
  caddy validate --config /etc/caddy/Caddyfile
