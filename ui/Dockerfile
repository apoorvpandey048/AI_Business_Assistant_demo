# ── UI (Next.js inspector frontend) ──────────────────────────────────────────
FROM node:20-alpine

WORKDIR /ui

COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

COPY . .

# Baked at build time (NEXT_PUBLIC_* are inlined). For docker-compose the browser
# runs on the host, so it reaches the API at localhost:8000.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
