# GhostBuilding

**GhostBuilding** is an OSINT (Open Source Intelligence) platform that detects and highlights discrepancies between map providers (Google Maps, OpenStreetMap, Bing Maps, Yandex). It identifies censored areas, ghost buildings, hidden structures, and systematic map data manipulation.

## 🎯 What It Does

- **Cross-provider image comparison** — Downloads tiles from 4 providers and computes pixel-level differences (SSIM, histogram, contour analysis)
- **Blur & censorship detection** — Distinguishes intentional blurring (censorship) from natural low resolution using Laplacian variance, FFT frequency analysis, and regional blur maps
- **Geospatial anomaly detection** — Cross-references OSM building data with YOLO v8 satellite imagery detection to find ghost buildings (in OSM but missing from imagery) and hidden structures (visible in imagery but absent from OSM)
- **Historical change analysis** — Tracks location changes over time via Wayback Machine archives, detecting sudden structure appearances/disappearances and blur application dates
- **Weighted confidence scoring** — Fuses all signals into a single anomaly score with category classification

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Next.js 14)                 │
│                    MapLibre GL JS                        │
└────────────────────────┬────────────────────────────────┘
                         │ REST API
┌────────────────────────▼────────────────────────────────┐
│                  FastAPI Backend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │ API      │  │ Models   │  │ Celery Tasks          │  │
│  │ Routes   │  │ (ORM)    │  │ scan / maintenance    │  │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────────┘  │
│       │             │                  │                 │
│  ┌────▼─────────────▼──────────────────▼──────────────┐ │
│  │              Service Layer                          │ │
│  │  ┌────────────────┐  ┌───────────────────────────┐ │ │
│  │  │ Data Collectors │  │    Anomaly Engine         │ │ │
│  │  │ • TileFetcher   │  │ (orchestrates all below)  │ │ │
│  │  │ • OSMCollector  │  └─────────┬─────────────────┘ │ │
│  │  │ • SatFetcher    │            │                    │ │
│  │  │ • WaybackFetch  │  ┌─────────▼─────────────────┐ │ │
│  │  └────────────────┘  │      Analyzers             │ │ │
│  │                       │ • PixelDiffAnalyzer        │ │ │
│  │                       │ • BlurDetector             │ │ │
│  │                       │ • GeospatialAnalyzer       │ │ │
│  │                       │ • TimeSeriesAnalyzer       │ │ │
│  │                       └───────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────┘ │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌───────────┐  ┌───────────┐  ┌───────────┐
   │ PostgreSQL│  │   Redis   │  │   MinIO   │
   │ + PostGIS │  │  (cache)  │  │ (storage) │
   └───────────┘  └───────────┘  └───────────┘
```

## 🔬 Analysis Modules (Phase 3)

### Confidence Score Formula

| Component | Weight | Source |
|---|---|---|
| Provider Disagreement | **0.30** | How many providers disagree with each other |
| Pixel Diff Score | **0.25** | Maximum pixel difference between any two providers |
| Blur/Censorship Score | **0.20** | Intentional blur detection via FFT + Laplacian |
| Geospatial Mismatch | **0.15** | OSM vs satellite building count discrepancy |
| Historical Change | **0.10** | Wayback Machine temporal anomalies |

### Anomaly Categories

| Category | Trigger |
|---|---|
| `CENSORED_AREA` | Blur score > 70 |
| `HIDDEN_STRUCTURE` | Structures in satellite but absent from OSM |
| `GHOST_BUILDING` | Buildings in OSM but not visible in satellite |
| `IMAGE_DISCREPANCY` | High pixel diff, low blur/geospatial scores |

## 🛠 Tech Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0, Celery 5.3
- **Database:** PostgreSQL 16 + PostGIS 3.4
- **Cache/Broker:** Redis 7
- **CV/ML:** OpenCV, scikit-image, NumPy, Pillow, ultralytics (YOLO v8)
- **Frontend:** Next.js 14, MapLibre GL JS, Tailwind CSS
- **Storage:** MinIO (S3-compatible) with local filesystem fallback
- **DevOps:** Docker, Docker Compose, GitHub Actions

## 🚀 Getting Started

### Prerequisites

- Docker & Docker Compose
- Git

### Quick Start

```bash
# 1. Clone
git clone https://github.com/Scryne/GhostBuilding.git
cd GhostBuilding

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys (optional but recommended):
#   GOOGLE_MAPS_API_KEY, BING_MAPS_API_KEY,
#   SENTINEL_HUB_CLIENT_ID, SENTINEL_HUB_CLIENT_SECRET

# 3. Start all services
docker-compose up --build

# Services:
#   Backend API:  http://localhost:8000
#   Frontend:     http://localhost:3000
#   Redis:        localhost:6379
#   PostgreSQL:   localhost:5432
#   MinIO:        http://localhost:9001 (console)
```

### Running Without Docker

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload

# Celery Worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info

# Celery Beat (separate terminal)
celery -A app.tasks.celery_app beat --loglevel=info
```

## 📁 Project Structure

```
ghostbuilding/
├── backend/
│   └── app/
│       ├── config.py                    # Pydantic settings
│       ├── main.py                      # FastAPI app
│       ├── worker.py                    # Celery entrypoint
│       ├── db/
│       │   ├── base_class.py            # SQLAlchemy Base
│       │   └── session.py               # Async session factory
│       ├── models/
│       │   ├── anomaly.py               # Anomaly ORM model
│       │   ├── anomaly_image.py         # Provider image records
│       │   ├── scan_job.py              # Scan job tracking
│       │   ├── user.py                  # User model
│       │   └── verification.py          # Community verification
│       ├── services/
│       │   ├── tile_fetcher.py          # Multi-provider tile download
│       │   ├── osm_collector.py         # Overpass API + building data
│       │   ├── satellite_fetcher.py     # Sentinel Hub + NASA GIBS
│       │   ├── anomaly_engine.py        # Main analysis orchestrator
│       │   └── analyzers/
│       │       ├── pixel_diff.py        # Cross-provider image diff
│       │       ├── blur_detector.py     # Censorship/blur detection
│       │       ├── geospatial_analyzer.py  # OSM vs satellite comparison
│       │       └── time_series.py       # Historical change tracking
│       └── tasks/
│           ├── celery_app.py            # Celery configuration
│           ├── scan_tasks.py            # Coordinate & region scanning
│           └── maintenance_tasks.py     # Periodic cleanup & health
├── frontend/                            # Next.js 14 application
├── docker-compose.yml                   # Development stack
├── docker-compose.prod.yml              # Production stack
└── .env.example                         # Environment template
```

## 📄 License

This project is for educational and research purposes.