# ═══════════════════════════════════════════════════════════════════════════
# GhostBuilding — Backend Dockerfile (FastAPI + Celery)
# Includes system deps for PostGIS, OpenCV, scikit-image.
# ═══════════════════════════════════════════════════════════════════════════

FROM python:3.12-slim

WORKDIR /app

# System dependencies for PostgreSQL, OpenCV headless, GDAL.
# upgrade: taban imaj güvenlik yamalarının gerisinde kalabiliyor (2026-11-09 Trivy:
# zlib1g CVE-2026-76844/85091, düzeltmesi deb13u1'de); paketler imaj kurulurken yamalanır.
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    g++ \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run FastAPI via uvicorn (override in docker-compose for celery)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
