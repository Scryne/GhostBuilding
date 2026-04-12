# ═══════════════════════════════════════════════════════════════════════════
# GhostBuilding — Backend Dockerfile (FastAPI + Celery)
# Includes system deps for PostGIS, OpenCV, scikit-image.
# ═══════════════════════════════════════════════════════════════════════════

FROM python:3.12-slim

WORKDIR /app

# System dependencies for PostgreSQL, OpenCV headless, GDAL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    g++ \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run FastAPI via uvicorn (override in docker-compose for celery)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
