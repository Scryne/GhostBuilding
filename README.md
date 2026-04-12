<p align="center">
  <img src="https://img.shields.io/badge/GhostBuilding-OSINT%20Platform-2E6DA4?style=for-the-badge&logo=satellite&logoColor=white" alt="GhostBuilding" />
</p>

<h1 align="center">👻 GhostBuilding</h1>

<p align="center">
  <strong>OSINT Mapping Intelligence Platform</strong><br/>
  <em>Detect censored areas, ghost buildings, and hidden structures across map providers.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-0.110-009688?style=flat-square&logo=fastapi" />
  <img src="https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=nextdotjs" />
  <img src="https://img.shields.io/badge/PostgreSQL-16+PostGIS-4169E1?style=flat-square&logo=postgresql" />
  <img src="https://img.shields.io/badge/Celery-5.3-37814A?style=flat-square&logo=celery" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker" />
  <img src="https://img.shields.io/badge/License-Educational-F4A261?style=flat-square" />
</p>

---

## 🎯 What It Does

GhostBuilding is an OSINT platform that detects and highlights discrepancies between map providers (Google Maps, OpenStreetMap, Bing Maps, Yandex). It identifies:

- **🏚️ Ghost Buildings** — Structures registered in OSM but invisible in satellite imagery
- **🔒 Hidden Structures** — Buildings visible in satellite imagery but absent from official maps
- **🚫 Censored Areas** — Intentionally blurred or pixelated regions across providers
- **🔍 Image Discrepancies** — Significant pixel-level differences between provider tiles

### Key Capabilities

| Feature | Description |
|---|---|
| **Cross-Provider Comparison** | Downloads tiles from 4+ providers, computes pixel-level diffs (SSIM, histogram, contour) |
| **Blur & Censorship Detection** | Laplacian variance + FFT frequency analysis + regional blur mapping |
| **Geospatial Analysis** | Cross-references OSM building data with YOLO v8 satellite detection |
| **Historical Tracking** | Wayback Machine archives for temporal change detection |
| **Community Verification** | Weighted voting system with trust scores and auto-status updates |
| **Real-Time Scanning** | Celery-powered background scan jobs with progress tracking |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Next.js 14)                 │
│              MapLibre GL JS · Tailwind CSS               │
│         Auth · Explore · Profile · Map Interface         │
└────────────────────────┬────────────────────────────────┘
                         │ REST API (JWT Auth)
┌────────────────────────▼────────────────────────────────┐
│                   FastAPI Backend                        │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────────┐ │
│  │ Routers  │  │ Models   │  │ Celery Tasks           │ │
│  │ • auth   │  │ • User   │  │ • scan_coordinate      │ │
│  │ • anomaly│  │ • Anomaly│  │ • scan_region          │ │
│  │ • verify │  │ • Verify │  │ • maintenance          │ │
│  └────┬─────┘  └────┬─────┘  └────────┬──────────────┘ │
│       │             │                  │                │
│  ┌────▼─────────────▼──────────────────▼──────────────┐ │
│  │              Service Layer                          │ │
│  │  ┌────────────────┐  ┌───────────────────────────┐ │ │
│  │  │ Data Collectors │  │    Anomaly Engine         │ │ │
│  │  │ • TileFetcher   │  │ (orchestrates analysis)   │ │ │
│  │  │ • OSMCollector  │  └─────────┬─────────────────┘ │ │
│  │  │ • SatFetcher    │            │                    │ │
│  │  └────────────────┘  ┌─────────▼─────────────────┐ │ │
│  │                       │      Analyzers             │ │ │
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
   │ + PostGIS │  │  (broker) │  │ (storage) │
   └───────────┘  └───────────┘  └───────────┘
```

---

## 🔬 Analysis Engine

### Confidence Score Formula

| Component | Weight | Source |
|---|---|---|
| Provider Disagreement | **0.30** | Number of providers showing different content |
| Pixel Diff Score | **0.25** | Maximum pixel difference between any two providers |
| Blur/Censorship Score | **0.20** | Intentional blur detection via FFT + Laplacian |
| Geospatial Mismatch | **0.15** | OSM vs satellite building count discrepancy |
| Historical Change | **0.10** | Wayback Machine temporal anomalies |

### Community Verification System

```
Weighted Voting:
  • Trusted verifier (trust_score > 4.0) → 2× vote weight
  • Normal user → 1× vote weight

Auto-Status Changes:
  • 10+ votes AND confirm_ratio > 75% → VERIFIED
  • 5+ votes AND confirm_ratio < 25%  → REJECTED

Trust Score Updates:
  • Correct prediction → +0.5 trust
  • Wrong prediction  → -0.1 trust (soft penalty)
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2.0, Celery 5.3 |
| **Database** | PostgreSQL 16 + PostGIS 3.4 |
| **Cache/Broker** | Redis 7 |
| **CV/ML** | OpenCV, scikit-image, NumPy, Pillow, Ultralytics (YOLO v8) |
| **Auth** | JWT (python-jose), bcrypt, role-based access |
| **Frontend** | Next.js 14, React 18, MapLibre GL JS, Tailwind CSS |
| **Storage** | MinIO (S3-compatible) with local filesystem fallback |
| **DevOps** | Docker, Docker Compose, GitHub Actions CI/CD |

---

## 🚀 Getting Started

### Prerequisites

- **Docker & Docker Compose** (recommended)
- Or: Python 3.12+, Node.js 20+, PostgreSQL 16, Redis 7

### Quick Start with Docker

```bash
# 1. Clone the repository
git clone https://github.com/Scryne/GhostBuilding.git
cd GhostBuilding

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys (optional but recommended)

# 3. Start all services
docker compose up --build

# Services:
#   Frontend:     http://localhost:3000
#   Backend API:  http://localhost:8000
#   API Docs:     http://localhost:8000/docs
#   Redis:        localhost:6379
#   PostgreSQL:   localhost:5432
```

### Running Without Docker

```bash
# ── Backend ────────────────────────────────────────────────
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
uvicorn app.main:app --reload

# ── Celery Worker (separate terminal) ──────────────────────
celery -A app.worker.celery_app worker --loglevel=info -Q default,scan

# ── Celery Beat (separate terminal) ────────────────────────
celery -A app.worker.celery_app beat --loglevel=info

# ── Frontend ───────────────────────────────────────────────
cd frontend
npm install
npm run dev
```

---

## 📁 Project Structure

```
ghostbuilding/
├── backend/
│   ├── app/
│   │   ├── config.py                    # Pydantic settings
│   │   ├── main.py                      # FastAPI application
│   │   ├── worker.py                    # Celery entrypoint
│   │   ├── db/
│   │   │   ├── base_class.py            # SQLAlchemy declarative base
│   │   │   └── session.py               # Async session factory
│   │   ├── models/
│   │   │   ├── anomaly.py               # Anomaly ORM (PostGIS geometry)
│   │   │   ├── anomaly_image.py         # Provider image records
│   │   │   ├── scan_job.py              # Scan job tracking
│   │   │   ├── user.py                  # User with trust scoring
│   │   │   ├── verification.py          # Community verification votes
│   │   │   └── enums.py                 # Shared enum definitions
│   │   ├── routers/
│   │   │   ├── auth.py                  # Register, login, profile, JWT
│   │   │   ├── anomalies.py             # CRUD, scan, stats, tile compare
│   │   │   ├── verifications.py         # Voting, weighted scoring
│   │   │   └── map_routes.py            # Map data endpoints
│   │   ├── services/
│   │   │   ├── auth_service.py          # JWT + bcrypt + brute-force protection
│   │   │   ├── tile_fetcher.py          # Multi-provider tile download
│   │   │   ├── osm_collector.py         # Overpass API + building data
│   │   │   ├── satellite_fetcher.py     # Sentinel Hub + NASA GIBS
│   │   │   ├── anomaly_engine.py        # Main analysis orchestrator
│   │   │   └── analyzers/
│   │   │       ├── pixel_diff.py        # Cross-provider image diff
│   │   │       ├── blur_detector.py     # Censorship/blur detection
│   │   │       ├── geospatial_analyzer.py  # OSM vs satellite comparison
│   │   │       └── time_series.py       # Historical change tracking
│   │   └── tasks/
│   │       ├── celery_app.py            # Celery configuration + schedules
│   │       ├── scan_tasks.py            # Coordinate & region scanning
│   │       └── maintenance_tasks.py     # Periodic cleanup & health checks
│   ├── tests/                           # Pytest suite (SQLite in-memory)
│   ├── alembic/                         # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx                 # Map interface (home)
│       │   ├── explore/                 # Browse anomalies with filters
│       │   ├── auth/                    # Login & register forms
│       │   └── profile/                 # User profile with gamification
│       ├── components/
│       │   ├── map/                     # GhostMap, layers, controls
│       │   ├── anomaly/                 # Detail panel, timeline, verification
│       │   ├── explore/                 # Search, filters, cards, featured
│       │   └── ui/                      # Button, Modal, Toast, Spinner, Badge
│       ├── hooks/                       # useAuth, useAnomaly
│       ├── lib/                         # API client, types, utils
│       └── middleware.ts                # JWT route protection
├── .github/workflows/                   # CI/CD pipelines
├── docker-compose.yml                   # Development stack
├── docker-compose.prod.yml              # Production stack
└── .env.example                         # Environment template
```

---

## 🔒 Security

- **JWT Authentication** with access (1h) + refresh (30d) tokens
- **Bcrypt password hashing** (passlib)
- **Brute-force protection** — 5 failed attempts → 15 min lockout
- **Token blacklist** via Redis (logout invalidation)
- **Role-based access** — USER / MODERATOR / ADMIN
- **Security headers** — X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- **CORS** configurable via environment variables

---

## 🧪 Testing

```bash
cd backend
pytest -v
```

The test suite uses SQLite in-memory with mock models (no PostGIS dependency), mock Redis, and mock Celery for CI-ready execution.

---

## 📄 License

This project is for **educational and research purposes**.

<p align="center">
  <sub>Built with ☕ and curiosity</sub>
</p>