# ── Dawei Agent Dockerfile ────────────────────────────────────────────
# Build:  docker build -t dawei-agent .
# Run:    docker run -p 8465:8465 --env-file .env dawei-agent
#
# For persistent data, mount a volume at /root/.normnomos:
#   docker run -p 8465:8465 --env-file .env -v dawei-data:/root/.normnomos dawei-agent

FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /usr/local/bin/uv

# Copy project config files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies (no source yet, for cache reuse)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source
COPY . .

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ── Runtime image ──────────────────────────────────────────────────────

FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="Dawei Agent"
LABEL org.opencontainers.image.description="DavyBot AI Agent Engine"
LABEL org.opencontainers.image.source="https://github.com/davybot/legalbot"

# Runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash dawei
USER dawei
WORKDIR /home/dawei

# Copy venv from builder
COPY --from=builder --chown=dawei:dawei /build/.venv /home/dawei/.venv

# Copy source (needed for template files, prompt configs, etc.)
COPY --from=builder --chown=dawei:dawei /build /home/dawei/agent

# Environment
ENV PATH="/home/dawei/.venv/bin:$PATH"
ENV DAWEI_HOME="/home/dawei/.normnomos"
ENV PYTHONUNBUFFERED=1

# Create data dir
RUN mkdir -p "$DAWEI_HOME"

# Default config — override via env or .env file
ENV HOST=0.0.0.0
ENV PORT=8465

# Expose port
EXPOSE 8465

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/health || exit 1

# Start the server
CMD ["sh", "-c", "exec dawei server start --host ${HOST} --port ${PORT}"]
