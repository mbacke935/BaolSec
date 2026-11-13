# BaolSec — incident-builder (C18)
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Installer pip + uv
RUN pip install --no-cache-dir uv==0.7.3

# Copier et installer baolsec-common
COPY shared/python-common /app/shared/python-common
RUN uv pip install --system --no-cache /app/shared/python-common[nats]

# Copier les contrats de messages (alert/v1, incident_command/v1, …)
COPY shared/contracts /opt/baolsec/contracts

# Copier et installer le service
# NB : copié sous services/incident-builder pour que le chemin relatif
# ../../shared/python-common de pyproject.toml ([tool.uv.sources]) résolve.
COPY services/incident-builder /app/services/incident-builder
RUN uv pip install --system --no-cache /app/services/incident-builder

# Utilisateur non-root
RUN adduser --disabled-password --gecos "" baolsec
USER baolsec

EXPOSE 9104
CMD ["python", "-m", "incidents.main"]