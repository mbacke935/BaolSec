# ── Étape 1 : build ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Installer les dépendances (layer caché si package.json inchangé)
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# Copier les sources et builder
COPY . .
RUN npm run build

# ── Étape 2 : serveur de production (Nginx) ───────────────────────────────────
FROM nginx:1.27-alpine

# Config Nginx custom (SPA + proxy API)
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
