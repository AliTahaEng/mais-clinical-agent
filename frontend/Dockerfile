# ─────────────────────────────────────────────────────────────
# Stage 1: install dependencies
# ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps

WORKDIR /app

# Install dependencies based on the preferred package manager
COPY package.json package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install

# ─────────────────────────────────────────────────────────────
# Stage 2: build the Next.js app
# ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# BACKEND_URL is used in next.config.ts rewrites at BUILD time
# It can also be passed at runtime via the env section in docker-compose
ENV BACKEND_URL=http://backend:8000
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ─────────────────────────────────────────────────────────────
# Stage 3: lean production runner
# next.config.ts uses output: "standalone" so .next/standalone
# contains a self-contained server.js
# ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Non-root user
RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

# Copy the standalone build output
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static   ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:3000 || exit 1

CMD ["node", "server.js"]
