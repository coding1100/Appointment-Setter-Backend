# =========================
# Builder stage
# =========================
FROM python:3.11 AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Set environment variables for HuggingFace cache during build
ENV HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_CACHE=/root/.cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/root/.cache/huggingface

# Download turn detector model from HuggingFace Hub
# This downloads the model_q8.onnx file that's required
RUN python3 -c "from huggingface_hub import snapshot_download; \
    snapshot_download( \
        repo_id='livekit/turn-detector', \
        cache_dir='/root/.cache/huggingface', \
        local_files_only=False \
    ); \
    print('✓ Turn detector model downloaded successfully')"

# Verify the model files exist
RUN python3 -c "from pathlib import Path; \
    import os; \
    cache_dir = Path('/root/.cache/huggingface'); \
    print(f'Cache directory: {cache_dir}'); \
    print(f'Cache exists: {cache_dir.exists()}'); \
    if cache_dir.exists(): \
        for root, dirs, files in os.walk(cache_dir): \
            for f in files: \
                if 'onnx' in f: \
                    print(f'Found ONNX file: {os.path.join(root, f)}'); \
    else: \
        print('WARNING: Cache directory does not exist!')"

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

# Copy HuggingFace cache (includes turn detector model)
COPY --from=builder /root/.cache/huggingface /root/.cache/huggingface

# Verify the cache was copied correctly
RUN python3 -c "from pathlib import Path; \
    import os; \
    cache_dir = Path('/root/.cache/huggingface'); \
    print(f'Runtime cache directory: {cache_dir}'); \
    print(f'Runtime cache exists: {cache_dir.exists()}'); \
    if cache_dir.exists(): \
        for root, dirs, files in os.walk(cache_dir): \
            for f in files: \
                if 'onnx' in f: \
                    print(f'Runtime found ONNX file: {os.path.join(root, f)}'); \
    else: \
        print('ERROR: Runtime cache directory does not exist!')"

# Copy application code
COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/root/.cache/huggingface \
    TRANSFORMERS_CACHE=/root/.cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/root/.cache/huggingface

EXPOSE 8000

# Start ONLY at runtime
CMD ["python", "run_voice_worker.py", "start"]