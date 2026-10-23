# Builds the Mini App and the admin panel, then serves them with nginx,
# which also terminates TLS and proxies /api to the backend.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
COPY shared/package.json shared/
COPY webapp/package.json webapp/
COPY admin/package.json admin/
RUN npm ci --no-audit --no-fund
COPY shared shared
COPY webapp webapp
COPY admin admin
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx/common.conf /etc/nginx/conf.d/00-common.conf
COPY deploy/nginx/snippets /etc/nginx/snippets
COPY deploy/nginx/sites /etc/nginx/sites
COPY deploy/nginx/05-select-site.sh deploy/nginx/40-reload-loop.sh /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/05-select-site.sh /docker-entrypoint.d/40-reload-loop.sh
COPY --from=build /src/webapp/dist /usr/share/nginx/webapp
COPY --from=build /src/admin/dist /usr/share/nginx/admin
EXPOSE 80 443
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1/nginx-health || exit 1
# The default CMD (nginx -g 'daemon off;') keeps the image's entrypoint scripts
# running: site selection, template rendering and the reload loop.
