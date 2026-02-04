# =========================
# Builder stage
# =========================
FROM python:3.11 AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# =========================
# Runtime stage
# =========================
FROM python:3.11-slim

# Runtime OS deps
RUN apt-get update && apt-get install -y \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set env early (rarely changes, so cached)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/root/.cache/huggingface \
    HF_HUB_CACHE=/root/.cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/root/.cache/huggingface

# Copy system-wide Python packages (cached unless requirements.txt changes)
COPY --from=builder /usr/local /usr/local

# Copy application code in stages for optimal caching:
# Strategy: Copy minimal files → Download models → Copy rest
# This ensures model download (slow step) is cached unless core files change

# Stage 1: Copy only essential files for download-files command
# These files rarely change, so model download layer stays cached
COPY run_voice_worker.py .
COPY app/__init__.py app/
COPY app/agents/ app/agents/
COPY app/core/__init__.py app/core/
COPY app/core/config.py app/core/

# Stage 2: Download models (SLOW - ~5-10 min, but cached if stage 1 unchanged)
RUN mkdir -p /root/.cache/huggingface && \
    python run_voice_worker.py download-files

# Stage 3: Copy all remaining application code
# This invalidates cache, but model download from stage 2 remains cached
COPY . .

EXPOSE 8000

# Default CMD (can be overridden in docker-compose)
CMD ["python", "run_voice_worker.py", "start"]