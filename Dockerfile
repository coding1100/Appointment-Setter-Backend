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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy system-wide Python packages
COPY --from=builder /usr/local /usr/local

# Copy application code
COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Start ONLY at runtime
CMD ["python", "run_voice_worker.py", "start"]
