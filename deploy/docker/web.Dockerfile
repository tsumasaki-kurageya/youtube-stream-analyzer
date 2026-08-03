FROM node:22-alpine AS build

WORKDIR /src/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
RUN npm run build

FROM caddy:2.10-alpine
COPY deploy/docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/apps/web/dist /srv
EXPOSE 8080
