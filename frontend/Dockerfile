# ═══════════════════════════════════════════════════════════════════════════
# GhostBuilding — Frontend Dockerfile (Next.js 16)
# Multi-stage build for optimized production image.
# ═══════════════════════════════════════════════════════════════════════════

# ── Stage 1: Dependencies ──────────────────────────────────────────────────
FROM node:22-alpine AS deps
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# ── Stage 2: Build ─────────────────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time env (override at runtime via docker-compose)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# MapTiler uydu altlığı (tanımlı değilse altlık seçicide görünmez)
ARG NEXT_PUBLIC_MAPLIBRE_TOKEN=
ENV NEXT_PUBLIC_MAPLIBRE_TOKEN=$NEXT_PUBLIC_MAPLIBRE_TOKEN
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ── Stage 3: Runner ────────────────────────────────────────────────────────
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Non-root user. Çalışma zamanı yalnız `node server.js`: taban imajın npm/npx/corepack'i
# kullanılmıyor, içindeki paketler (brace-expansion) Trivy'yi kırıyordu.
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs && \
    rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack \
           /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
