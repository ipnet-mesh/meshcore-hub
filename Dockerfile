# MeshCore Hub - Multi-stage Dockerfile
# Build and run MeshCore Hub components

# =============================================================================
# Stage 1: Builder - Install dependencies and build package
# =============================================================================
FROM python:3.14-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and use virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy project files
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Build argument for version (set via CI or manually)
ARG BUILD_VERSION=dev

# Set version in _version.py and install the package
RUN sed -i "s|__version__ = \"dev\"|__version__ = \"${BUILD_VERSION}\"|" src/meshcore_hub/_version.py && \
    pip install --upgrade pip && \
    pip install .

# =============================================================================
# Stage 2: Runtime - Final production image
# =============================================================================
FROM python:3.14-slim AS runtime

# Labels
LABEL org.opencontainers.image.title="MeshCore Hub" \
      org.opencontainers.image.description="Python monorepo for managing MeshCore mesh networks" \
      org.opencontainers.image.source="https://github.com/meshcore-dev/meshcore-hub"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Default configuration
    LOG_LEVEL=INFO \
    MQTT_HOST=mqtt \
    MQTT_PORT=1883 \
    MQTT_PREFIX=meshcore \
    DATA_HOME=/data \
    API_HOST=0.0.0.0 \
    API_PORT=8000 \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8080 \
    API_BASE_URL=http://api:8000

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # For serial port access
    udev \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy alembic configuration for migrations
WORKDIR /app
COPY --from=builder /app/alembic.ini ./
COPY --from=builder /app/alembic/ ./alembic/

# Create non-root user
RUN useradd --create-home --shell /bin/bash meshcore && \
    chown -R meshcore:meshcore /data /app

# Default to non-root user (can be overridden for device access)
USER meshcore

# Expose common ports
EXPOSE 8000 8080

# Health check - uses the API health endpoint by default
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Set entrypoint to the CLI
ENTRYPOINT ["meshcore-hub"]

# Default command shows help
CMD ["--help"]
