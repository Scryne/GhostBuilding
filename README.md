# GhostBuilding

GhostBuilding is an OSINT platform designed to identify and highlight discrepancies between various map providers (Google Maps, OpenStreetMap, Bing Maps, Yandex).

## Tech Stack
- **Backend:** FastAPI, PostgreSQL + PostGIS, Redis, Celery
- **Frontend:** Next.js 14, MapLibre GL JS, Tailwind CSS
- **DevOps:** Docker, Docker Compose, GitHub Actions

## Running Locally

1. Copy the example environment variables file:
```bash
cp .env.example .env
```

2. Start the development environment:
```bash
docker-compose up --build
```
    