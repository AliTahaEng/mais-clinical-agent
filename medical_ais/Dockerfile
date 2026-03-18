# ─────────────────────────────────────────────────────────────
# Stage 1: install Python dependencies
# Using slim to keep image small; torch CPU only (~800MB vs ~2.5GB)
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# System build deps (needed by lancedb, psycopg native extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU-only FIRST to avoid the 2.5GB CUDA version
# being pulled in as a dependency of sentence-transformers
RUN pip install --no-cache-dir \
    torch \
    --index-url https://download.pytorch.org/whl/cpu

# Install the rest of the Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────
# Stage 2: runtime image
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime system libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source into /app/medical_ais/ so imports like
# "from medical_ais.config.settings import Settings" resolve correctly.
COPY . ./medical_ais/

# Create data directories (volumes will be mounted here)
RUN mkdir -p /app/data/lancedb /app/data/documents /app/data/uploads

# Non-root user for security
RUN useradd -m -u 1000 mais && chown -R mais:mais /app
USER mais

# Expose FastAPI port
EXPOSE 8000

# Health check — hits the /api/v1/health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Use -m so Python adds WORKDIR (/app) to sys.path, making
# "from medical_ais.config.settings import Settings" resolve correctly.
CMD ["python", "-m", "medical_ais.main"]
