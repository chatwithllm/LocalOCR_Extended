# LocalOCR Extended
# Backend Dockerfile (PROMPT Step 1)
# Compatible with Mac Silicon (ARM64) and x86_64

FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_PORT=8090

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ /app/src/
COPY alembic/ /app/alembic/ 
COPY alembic.ini /app/alembic.ini
COPY scripts/ /app/scripts/

# Create data directories (volumes will override these)
RUN mkdir -p /data/db /data/receipts /data/backups
RUN chmod +x /app/scripts/*.sh

# Expose Flask port
EXPOSE 8090

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8090/health || exit 1

# Run the application — applies any pending migrations first so a fresh
# deployment picks up schema changes without a manual `alembic upgrade head`.
CMD ["sh", "-c", "alembic upgrade head && exec python -m src.backend.create_flask_application"]
