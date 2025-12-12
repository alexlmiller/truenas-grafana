# TrueNAS Exporters Docker Image
# Runs both truenas-exporter (custom) and graphite_exporter in a single container

# Stage 1: Download graphite_exporter
FROM alpine:3.20 AS downloader

ARG GRAPHITE_EXPORTER_VERSION=0.16.0
ARG TARGETARCH

RUN apk add --no-cache curl tar && \
    ARCH=$(case "${TARGETARCH}" in \
        "amd64") echo "amd64" ;; \
        "arm64") echo "arm64" ;; \
        "arm") echo "armv7" ;; \
        *) echo "amd64" ;; \
    esac) && \
    curl -fsSL "https://github.com/prometheus/graphite_exporter/releases/download/v${GRAPHITE_EXPORTER_VERSION}/graphite_exporter-${GRAPHITE_EXPORTER_VERSION}.linux-${ARCH}.tar.gz" \
    | tar xz --strip-components=1 -C /tmp

# Stage 2: Final image
FROM python:3.12-slim

LABEL org.opencontainers.image.title="TrueNAS Exporters"
LABEL org.opencontainers.image.description="Prometheus exporters for TrueNAS monitoring (truenas-exporter + graphite_exporter)"
LABEL org.opencontainers.image.source="https://github.com/alexlmiller/truenas-grafana"
LABEL org.opencontainers.image.licenses="MIT"

# Install supervisor
RUN apt-get update && \
    apt-get install -y --no-install-recommends supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /app /etc/truenas-exporter /etc/graphite_exporter /var/log/supervisor

# Copy graphite_exporter from downloader stage
COPY --from=downloader /tmp/graphite_exporter /usr/local/bin/

# Copy truenas-exporter
COPY exporter/truenas-exporter.py /app/

# Copy graphite mapping config
COPY graphite/graphite_mapping.conf /etc/graphite_exporter/

# Copy supervisor config
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose ports
# 9814: truenas-exporter metrics
# 2003: graphite receiver (TrueNAS sends metrics here)
# 9108: graphite_exporter Prometheus metrics
EXPOSE 9814 2003 9108

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:9814/health')" || exit 1

# Run supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
