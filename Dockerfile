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

# Copy system-wide Python packages
COPY --from=builder /usr/local /usr/local

# Copy application code
COPY . .

# Download LiveKit agent model files (turn detector, etc.)
# Uses the same CLI pattern as: `uv run agent.py download-files`
RUN python run_voice_worker.py download-files

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_CACHE=/root/.cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/root/.cache/huggingface

EXPOSE 8000

# Start ONLY at runtime
CMD ["python", "run_voice_worker.py", "start"]