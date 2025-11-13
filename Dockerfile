# Multi-stage build for production-ready Docker image
FROM python:3.11 AS builder

# Install build dependencies (more complete toolchain)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    cmake \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser && mkdir -p /app && chown -R appuser:appuser /app

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
# IMPORTANT: Docker caches layers based on file checksums
# If build completes in <5 seconds, Docker likely used cached COPY layer
# This means your code changes may NOT be included!
#
# SOLUTION: Force rebuild with: docker build --no-cache -t your-image .
# Or: docker build --build-arg CACHE_BUST=$(Get-Date -Format 'yyyyMMddHHmmss') -t your-image .
COPY --chown=appuser:appuser . .

# Build argument to force cache invalidation when code changes
# Usage: docker build --build-arg BUILD_TIME=$(date +%s) -t your-image .
ARG BUILD_TIME=unknown
RUN echo "Docker build time: ${BUILD_TIME}" > /app/.build-info && \
    echo "To verify your code is included, check: cat /app/.build-info"

# Set environment variables
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run the application with --proxy-headers flag to trust proxy headers from Nginx
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

