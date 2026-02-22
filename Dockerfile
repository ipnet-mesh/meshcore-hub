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
    # LetsMesh decoder runtime
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data

# Install meshcore-decoder CLI and patch ESM compatibility for Node 18 runtime.
RUN mkdir -p /opt/letsmesh-decoder \
    && cd /opt/letsmesh-decoder \
    && npm init -y >/dev/null 2>&1 \
    && npm install --omit=dev @michaelhart/meshcore-decoder@0.2.7 \
    && python - <<'PY'
from pathlib import Path

path = Path(
    "/opt/letsmesh-decoder/node_modules/@michaelhart/meshcore-decoder/"
    "dist/crypto/ed25519-verifier.js"
)
content = path.read_text(encoding="utf-8")

old_import = 'const ed25519 = __importStar(require("@noble/ed25519"));'
new_import = """let _ed25519 = null;
async function getEd25519() {
    if (_ed25519) {
        return _ed25519;
    }
    const mod = await import("@noble/ed25519");
    _ed25519 = mod.default ? mod.default : mod;
    try {
        _ed25519.etc.sha512Async = sha512Hash;
    }
    catch (error) {
        console.debug("Could not set async SHA-512:", error);
    }
    try {
        _ed25519.etc.sha512Sync = sha512HashSync;
    }
    catch (error) {
        console.debug("Could not set up synchronous SHA-512:", error);
    }
    return _ed25519;
}"""
if old_import not in content:
    raise RuntimeError("meshcore-decoder patch failed: import line not found")
content = content.replace(old_import, new_import, 1)

old_setup = """// Set up SHA-512 for @noble/ed25519
ed25519.etc.sha512Async = sha512Hash;
// Always set up sync version - @noble/ed25519 requires it
// It will throw in browser environments, which @noble/ed25519 can handle
try {
    ed25519.etc.sha512Sync = sha512HashSync;
}
catch (error) {
    console.debug('Could not set up synchronous SHA-512:', error);
}
"""
if old_setup not in content:
    raise RuntimeError("meshcore-decoder patch failed: sha512 setup block not found")
content = content.replace(old_setup, "", 1)

old_verify = "            return await ed25519.verify(signature, message, publicKey);"
new_verify = """            const ed25519 = await getEd25519();
            return await ed25519.verify(signature, message, publicKey);"""
if old_verify not in content:
    raise RuntimeError("meshcore-decoder patch failed: verify line not found")
content = content.replace(old_verify, new_verify, 1)

path.write_text(content, encoding="utf-8")
PY
RUN ln -s /opt/letsmesh-decoder/node_modules/.bin/meshcore-decoder /usr/local/bin/meshcore-decoder

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
