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

# Copy minimal files required to run LiveKit `download-files` during build
COPY run_voice_worker.py .
COPY app/__init__.py app/
COPY app/agents/__init__.py app/agents/
COPY app/agents/voice_worker.py app/agents/
COPY app/core/__init__.py app/core/
COPY app/core/config.py app/core/
COPY app/core/async_redis.py app/core/
COPY app/core/prompts.py app/core/

# Download models/plugins at build time per LiveKit docs
RUN mkdir -p /root/.cache/huggingface && \
    python run_voice_worker.py download-files

# Copy application code
COPY . .

EXPOSE 8000

# Default CMD (can be overridden in docker-compose)
CMD ["python", "run_voice_worker.py", "start"]
