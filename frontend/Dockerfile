# ── Étape 1 : build ──────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Installer les dépendances (layer caché si package.json inchangé)
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# Copier les sources et builder
COPY . .
RUN npm run build

# ── Étape 2 : serveur de production (Nginx) ───────────────────────────────────
FROM nginx:1.27-alpine

# Config Nginx (SPA + relais API) : modèle complété au démarrage avec le port HTTPS publié,
# pour que la redirection HTTP → HTTPS mène au bon port (FRONTEND_HTTPS_PORT, 443 par défaut).
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV FRONTEND_HTTPS_PORT=443 \
    NGINX_ENVSUBST_FILTER=^FRONTEND_

EXPOSE 80 443

# Certificat HTTPS monté dans /etc/nginx/certs (frontend.crt, frontend.key), voir nginx.conf.template.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
