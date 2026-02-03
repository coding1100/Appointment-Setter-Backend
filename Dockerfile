FROM python:3.11 AS builder

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    cmake \
    libffi-dev \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Download LiveKit VAD + turn detector models (NO credentials required)
RUN python run_voice_worker.py download-files




# ===============================
# Runtime stage
# ===============================
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser && mkdir -p /app && chown -R appuser:appuser /app

WORKDIR /app

COPY --from=builder /root/.local /home/appuser/.local
COPY --from=builder /app /app

ARG BUILD_TIME=unknown
RUN echo "Docker build time: ${BUILD_TIME}" > /app/.build-info

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
