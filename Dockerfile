FROM node:22-alpine AS web-build
WORKDIR /build/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DATA_DIR=/data \
    DATABASE_URL=sqlite:////data/net2net.db \
    WEB_ORIGIN=http://localhost:8080
WORKDIR /app
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends freeradius freeradius-utils && rm -rf /var/lib/apt/lists/*
COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
COPY apps/api/radius ./radius
RUN pip install --no-cache-dir .
COPY --from=web-build /build/apps/web/dist ./web_dist
COPY docker/entrypoint.sh /usr/local/bin/net2net-entrypoint
RUN chmod 755 /usr/local/bin/net2net-entrypoint && mkdir -p /data
EXPOSE 8080 1812/udp 1813/udp
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"
ENTRYPOINT ["/usr/local/bin/net2net-entrypoint"]
