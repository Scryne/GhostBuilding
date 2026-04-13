# Production Deployment Guide

We recommend a split architecture using **Railway** for the Postgres/Redis/FastAPI backend, and **Vercel** for the Next.js frontend.

## Pre-requisites
- GitHub Repository linked to both services
- Cloudflare managed DNS

## 1. Deploying the Backend (Railway)
1. In Railway, provision **PostgreSQL** and **Redis**.
2. Connect your repo and set the root directory to `backend`.
3. Set the variables: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `CORS_ORIGINS`.
4. Railway will auto-run the `railway.toml` build commands including `alembic upgrade head`.
5. Create additional services in the same environment for `worker` and `beat` using custom start commands.

## 2. Deploying the Frontend (Vercel)
1. Add new Vercel project, link repository, point to `frontend`.
2. Add your environment variations:
   - `NEXT_PUBLIC_API_URL`
   - `NEXT_PUBLIC_MAPLIBRE_TOKEN`
3. Hit Deploy. Vercel automatically applies static routing and Edge functions.
